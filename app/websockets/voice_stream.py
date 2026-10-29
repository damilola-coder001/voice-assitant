import asyncio
import json
import logging
import re
import time
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.conversation import ConversationSession, Message
from app.models.user import User
from app.security.tokens import decode_token
from app.services.conversational import conversational_engine
from app.services.elevenlabs import ElevenLabsQuotaExceededError, elevenlabs_service
from app.services.tech_intelligence.orchestrator import tech_orchestrator
from app.services.usage_tracker import usage_tracker
from app.websockets.connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TEXT_PAYLOAD_BYTES = 65536      # 64 KB limit
MAX_BINARY_PAYLOAD_BYTES = 5242880  # 5 MB limit
WS_IDLE_TIMEOUT_SECONDS = 180.0     # 3 minutes idle timeout
VALID_MESSAGE_TYPES = {"ping", "interrupt", "start_turn", "message"}

# Short-circuit for exhausted ElevenLabs quota: if a stream recently failed with
# quota_exceeded, skip re-attempting ElevenLabs for a cooldown period and go
# straight to the browser-speech fallback. Prevents every turn from paying for
# a doomed TTS round-trip while the free-tier quota is empty.
_LAST_QUOTA_FAILURE_TS: float = 0.0
QUOTA_FAILURE_COOLDOWN_SECONDS = 300.0

@router.websocket("/ws/voice")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Real-time bidirectional streaming voice interaction over WebSocket.
    Supports streaming TTS chunking, token transcription, and instant interruptions.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    payload = decode_token(token, expected_type="access")
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    try:
        user_id = int(payload.sub)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token subject")
        return

    # Fetch user from database
    async with AsyncSessionLocal() as db:
        user_res = await db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.voice_preference))
        )
        user = user_res.scalar_one_or_none()

    if not user or not user.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User inactive or deleted")
        return

    # Enforce connection limits (max per user and server-wide)
    can_connect, limit_reason = manager.can_connect(user.id)
    if not can_connect:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=limit_reason)
        return

    await manager.connect(websocket, user.id)

    active_turn_task: Optional[asyncio.Task] = None
    try:
        # Send initial ready state
        await websocket.send_json({
            "type": "ready",
            "message": "Connected to NORE real-time voice platform.",
            "user": {
                "id": user.id,
                "email": user.email,
                "preferred_voice_id": user.voice_preference.preferred_voice_id if user.voice_preference else settings.ELEVENLABS_DEFAULT_VOICE_ID,
            },
        })

        while True:
            # Idle timeout management: Close inactive sockets after 180s
            try:
                message_data = await asyncio.wait_for(
                    websocket.receive(), timeout=WS_IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.info(f"Closing idle WebSocket for user {user.id} after {WS_IDLE_TIMEOUT_SECONDS}s inactivity.")
                try:
                    await websocket.send_json({
                        "type": "timeout",
                        "message": "WebSocket session closed due to inactivity.",
                    })
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE, reason="Idle timeout")
                except Exception:
                    pass
                break

            if message_data.get("type") == "websocket.disconnect":
                break

            if "text" in message_data:
                text_content = message_data["text"]
                # Enforce message size cap
                if len(text_content.encode("utf-8")) > MAX_TEXT_PAYLOAD_BYTES:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Message size limit exceeded (64KB maximum)",
                    })
                    continue

                # Validate JSON syntax
                try:
                    data = json.loads(text_content)
                except Exception:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Malformed message: JSON object required",
                    })
                    continue

                if not isinstance(data, dict):
                    await websocket.send_json({
                        "type": "error",
                        "error": "Invalid payload: root must be a JSON object",
                    })
                    continue

                msg_type = data.get("type")
                if msg_type not in VALID_MESSAGE_TYPES:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Unsupported message type: '{msg_type}'",
                    })
                    continue

                # Handle instant interruption command from client
                if msg_type == "interrupt":
                    manager.trigger_interrupt(websocket)
                    if active_turn_task and not active_turn_task.done():
                        active_turn_task.cancel()
                    await websocket.send_json({"type": "interrupted", "message": "Voice synthesis cancelled."})
                    continue

                # Handle ping/heartbeat
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
                    continue

                # Handle conversation turn
                if msg_type in ("start_turn", "message"):
                    user_text = data.get("text", "").strip()
                    session_id = data.get("session_id")
                    persona_id = data.get("persona_id", "executive")
                    custom_voice_id = data.get("voice_id")

                    if not user_text or re.match(r"^\[.*?\]$", user_text):
                        continue

                    # Cancel any prior in-flight turn task
                    if active_turn_task and not active_turn_task.done():
                        manager.trigger_interrupt(websocket)
                        active_turn_task.cancel()
                        try:
                            await active_turn_task
                        except (asyncio.CancelledError, Exception):
                            pass

                    # Reset interruption state for new turn
                    manager.reset_interrupt(websocket)

                    active_turn_task = asyncio.create_task(
                        handle_voice_turn(
                            websocket=websocket,
                            user=user,
                            user_text=user_text,
                            session_id=session_id,
                            persona_id=persona_id,
                            voice_id=custom_voice_id,
                        )
                    )

            elif "bytes" in message_data:
                raw_audio = message_data["bytes"]
                if len(raw_audio) > MAX_BINARY_PAYLOAD_BYTES:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Binary audio chunk size exceeds 5MB limit",
                    })
                    continue
                # Validated binary audio packet accepted
                pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected cleanly for user {user.id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
    finally:
        if active_turn_task and not active_turn_task.done():
            active_turn_task.cancel()
        manager.disconnect(websocket, user.id)

async def _finish_turn_with_browser_fallback(
    websocket: WebSocket,
    db,
    session: ConversationSession,
    full_reply_text: str,
    target_voice: str,
    char_count: int,
    start_time: float,
    reason: str,
    message: str,
):
    """Persist the assistant message and have the client speak via browser synthesis.

    Used when ElevenLabs TTS is unavailable (quota exhausted or synthesis error)
    so the turn still completes audibly instead of going silent.
    """
    latency_ms = int((time.time() - start_time) * 1000)
    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=full_reply_text,
        characters_count=char_count,
        latency_ms=latency_ms,
        voice_id=target_voice,
    )
    db.add(assistant_msg)
    await db.commit()

    await websocket.send_json({
        "type": "voice_stream_fallback",
        "reason": reason,
        "message": message,
        "text": full_reply_text,
        "message_id": assistant_msg.id,
        "session_id": session.id,
    })
    await websocket.send_json({
        "type": "turn_complete",
        "session_id": session.id,
        "message_id": assistant_msg.id,
        "latency_ms": latency_ms,
        "chunks_sent": 0,
        "characters": char_count,
        "fallback": "browser_speech",
    })

async def handle_voice_turn(
    websocket: WebSocket,
    user: User,
    user_text: str,
    session_id: Optional[int],
    persona_id: str,
    voice_id: Optional[str] = None,
):
    """Process user prompt, generate AI response, stream text tokens and synthesized audio chunks."""
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        # Load or create conversation session
        session = None
        if session_id:
            s_res = await db.execute(
                select(ConversationSession)
                .where(ConversationSession.id == session_id, ConversationSession.user_id == user.id)
                .options(selectinload(ConversationSession.messages))
            )
            session = s_res.scalar_one_or_none()

        if not session:
            session = ConversationSession(
                user_id=user.id,
                title=user_text[:40] if len(user_text) > 40 else user_text,
                persona_id=persona_id,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            # Re-fetch with messages relation
            s_res = await db.execute(
                select(ConversationSession)
                .where(ConversationSession.id == session.id)
                .options(selectinload(ConversationSession.messages))
            )
            session = s_res.scalar_one()

        # Save user message
        user_msg = Message(
            session_id=session.id,
            role="user",
            content=user_text,
            characters_count=len(user_text),
        )
        db.add(user_msg)
        await db.commit()

        # Build history context (last 20 messages for deep conversational memory)
        history = [
            {"role": m.role, "content": m.content}
            for m in (session.messages or [])[-20:]
        ]

        # Notify client we are processing
        await websocket.send_json({
            "type": "turn_start",
            "session_id": session.id,
            "user_message_id": user_msg.id,
        })

        personality = None
        if user.voice_preference:
            personality = {
                "assistant_name": getattr(user.voice_preference, "assistant_name", "NORE"),
                "tone": getattr(user.voice_preference, "tone", "balanced"),
                "formality": getattr(user.voice_preference, "formality", "professional"),
                "response_style": getattr(user.voice_preference, "response_style", "adaptive"),
                "preferred_language": getattr(user.voice_preference, "preferred_language", "en"),
            }

        # Build tech preference context
        user_tech_pref = None
        if user.voice_preference:
            user_tech_pref = {
                "tech_interests": getattr(user.voice_preference, "tech_interests", "ai_ml,software_dev,cybersecurity"),
                "tech_explanation_level": getattr(user.voice_preference, "tech_explanation_level", "intermediate"),
                "tech_briefing_topics": getattr(user.voice_preference, "tech_briefing_topics", "all"),
                "tech_summary_style": getattr(user.voice_preference, "tech_summary_style", "balanced"),
            }

        full_reply_text = ""
        try:
            # Classify intent early to deliver instant visual feedback to client
            from app.services.tech_intelligence.classifier import tech_classifier
            early_classification = tech_classifier.classify(
                user_text,
                user_level_pref=user_tech_pref.get("tech_explanation_level") if user_tech_pref else None,
            )
            await websocket.send_json({
                "type": "tech_intent",
                "intent": early_classification.intent.value,
                "domain": early_classification.primary_domain.value,
                "requires_search": early_classification.requires_search,
                "explanation_level": early_classification.explanation_level.value,
            })

            # Route through Technology Intelligence Orchestrator
            tech_resp = await tech_orchestrator.process_query(
                user_message=user_text,
                session_id=session.id,
                history=history,
                user_tech_pref=user_tech_pref,
            )

            # Send verified sources drawer data
            if tech_resp.sources:
                await websocket.send_json({
                    "type": "tech_sources",
                    "sources": [s.to_dict() for s in tech_resp.sources],
                })

            # Send fact-check card data
            if tech_resp.fact_check:
                await websocket.send_json({
                    "type": "fact_check_result",
                    "fact_check": tech_resp.fact_check.to_dict(),
                })

            # Send structured briefing data
            if tech_resp.briefing:
                await websocket.send_json({
                    "type": "briefing_data",
                    "briefing": tech_resp.briefing.to_dict(),
                })

            full_reply_text = tech_resp.spoken_response
        except Exception as e:
            logger.error(f"Tech orchestrator error: {e}", exc_info=True)

        if not full_reply_text:
            # Fallback to Conversational Engine
            try:
                full_reply_text = await conversational_engine.generate_reply(
                    user_message=user_text,
                    history=history,
                    persona_id=persona_id,
                    personality_settings=personality,
                )
            except Exception as e:
                logger.error(f"Conversational engine error: {e}", exc_info=True)

        # Sanitize reply text before TTS & display so internal status, thoughts, or processing phrases are NEVER vocalized
        full_reply_text = conversational_engine.sanitize_spoken_response(full_reply_text)
        if not full_reply_text:
            full_reply_text = "I couldn't get that information right now. Try again."

        # Stream text response to client
        await websocket.send_json({
            "type": "text_response",
            "content": full_reply_text,
        })

        # Check interruption
        if manager.is_interrupted(websocket):
            return

        # Determine voice parameters
        target_voice = voice_id or (user.voice_preference.preferred_voice_id if user.voice_preference else settings.ELEVENLABS_DEFAULT_VOICE_ID)
        stability = user.voice_preference.stability if user.voice_preference else 0.5
        similarity_boost = user.voice_preference.similarity_boost if user.voice_preference else 0.75

        # Check user quota
        char_count = len(full_reply_text)
        has_quota = await usage_tracker.check_quota(db, user, requested_characters=char_count)
        if not has_quota:
            await websocket.send_json({
                "type": "error",
                "message": "Daily voice quota reached. Response text generated, but audio synthesis skipped.",
            })
            return

        # If ElevenLabs quota recently failed, skip the doomed TTS attempt and
        # go straight to the browser-speech fallback (saves a failed round-trip
        # on every turn while the quota is exhausted).
        global _LAST_QUOTA_FAILURE_TS
        if time.time() - _LAST_QUOTA_FAILURE_TS < QUOTA_FAILURE_COOLDOWN_SECONDS:
            logger.info("Skipping ElevenLabs TTS: quota recently exhausted, using browser fallback.")
            await _finish_turn_with_browser_fallback(
                websocket, db, session, full_reply_text, target_voice,
                char_count, start_time,
                reason="quota_exceeded",
                message="ElevenLabs voice quota is currently exhausted. Using browser voice synthesis.",
            )
            return

        # Stream ElevenLabs TTS audio chunks as raw PCM 24kHz binary frames
        tts_start = time.time()
        audio_stream = elevenlabs_service.stream_text_to_speech(
            text=full_reply_text,
            voice_id=target_voice,
            stability=max(0.45, stability),
            similarity_boost=similarity_boost,
            output_format="pcm_24000",
        )

        # Notify client of PCM stream format to initialize sample-accurate scheduling
        await websocket.send_json({
            "type": "audio_stream_start",
            "format": "pcm_24000",
            "sample_rate": 24000,
            "channels": 1,
        })

        chunks_sent = 0
        remainder = b""
        try:
            async for chunk in audio_stream:
                if manager.is_interrupted(websocket):
                    logger.info("Voice stream interrupted during chunk delivery.")
                    break
                if not chunk:
                    continue

                data = remainder + chunk
                # 16-bit PCM requires even byte length (2 bytes per sample)
                if len(data) % 2 != 0:
                    remainder = data[-1:]
                    data = data[:-1]
                else:
                    remainder = b""

                if data:
                    await websocket.send_bytes(data)
                    chunks_sent += 1

            if remainder:
                # Pad trailing half-sample with 0 byte to maintain strict 16-bit alignment
                await websocket.send_bytes(remainder + b"\x00")
                chunks_sent += 1

            # Notify client that audio stream has completed
            await websocket.send_json({
                "type": "audio_stream_end",
            })

            latency_ms = int((time.time() - start_time) * 1000)

            # Persist assistant message in DB
            assistant_msg = Message(
                session_id=session.id,
                role="assistant",
                content=full_reply_text,
                characters_count=char_count,
                latency_ms=latency_ms,
                voice_id=target_voice,
            )
            db.add(assistant_msg)

            # Log usage
            await usage_tracker.log_usage(
                db=db,
                user_id=user.id,
                operation="ws_voice_stream",
                character_count=char_count,
                voice_id=target_voice,
                latency_ms=latency_ms,
                status_code=200,
            )
            await db.commit()

            # Signal turn completion
            await websocket.send_json({
                "type": "turn_complete",
                "message_id": assistant_msg.id,
                "session_id": session.id,
                "latency_ms": latency_ms,
                "chunks_sent": chunks_sent,
                "characters": char_count,
            })

        except ElevenLabsQuotaExceededError as e:
            logger.warning(f"ElevenLabs voice quota reached during stream: {e}")
            _LAST_QUOTA_FAILURE_TS = time.time()
            await _finish_turn_with_browser_fallback(
                websocket, db, session, full_reply_text, target_voice,
                char_count, start_time,
                reason="quota_exceeded",
                message="ElevenLabs quota reached. Using browser voice synthesis.",
            )

        except Exception as e:
            logger.warning(f"Voice synthesis error during stream: {e}")
            await _finish_turn_with_browser_fallback(
                websocket, db, session, full_reply_text, target_voice,
                char_count, start_time,
                reason="tts_error",
                message=f"Audio synthesis note: {str(e)}",
            )
