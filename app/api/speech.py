import base64
import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.conversation import ConversationSession, Message
from app.models.user import User
from app.schemas.voice import TTSRequest
from app.security.dependencies import get_current_user
from app.security.rate_limiter import check_rate_limit
from app.services.conversational import conversational_engine
from app.services.elevenlabs import (
    ElevenLabsError,
    ElevenLabsPermissionError,
    ElevenLabsQuotaExceededError,
    elevenlabs_service,
)
from app.services.tech_intelligence.classifier import tech_classifier
from app.services.tech_intelligence.orchestrator import tech_orchestrator
from app.services.usage_tracker import usage_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["Speech"])


class VoiceTurnRequest(BaseModel):
    text: str
    session_id: Optional[int] = None
    persona_id: Optional[str] = "executive"
    voice_id: Optional[str] = None


@router.post("/tts")
async def text_to_speech(
    data: TTSRequest,
    request: Request,
    stream: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synthesize text to speech using ElevenLabs with streaming audio response.
    Enforces user daily character quota and logs usage.
    """
    await check_rate_limit(request, max_requests=60, window=60)

    char_count = len(data.text)
    # Check user daily quota
    has_quota = await usage_tracker.check_quota(db, current_user, requested_characters=char_count)
    if not has_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily character quota exceeded. Limit is {current_user.daily_character_quota} characters per day.",
        )

    # Use user preferences if voice settings are not explicitly given
    voice_id = data.voice_id
    if not voice_id and current_user.voice_preference:
        voice_id = current_user.voice_preference.preferred_voice_id

    model_id = data.model_id
    if not model_id and current_user.voice_preference:
        model_id = current_user.voice_preference.preferred_model_id

    stability = data.voice_settings.stability if data.voice_settings else 0.5
    similarity_boost = data.voice_settings.similarity_boost if data.voice_settings else 0.75

    start_time = time.time()

    try:
        if stream:
            # Return live streaming audio
            generator = elevenlabs_service.stream_text_to_speech(
                text=data.text,
                voice_id=voice_id,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
                output_format="mp3_44100_128",
            )

            async def tracking_generator():
                try:
                    async for chunk in generator:
                        yield chunk
                    latency_ms = int((time.time() - start_time) * 1000)
                    try:
                        await usage_tracker.log_usage(
                            db=db,
                            user_id=current_user.id,
                            operation="tts_stream",
                            character_count=char_count,
                            voice_id=voice_id,
                            model_id=model_id,
                            latency_ms=latency_ms,
                            status_code=200,
                        )
                    except Exception:
                        pass
                except Exception as e:
                    latency_ms = int((time.time() - start_time) * 1000)
                    try:
                        await usage_tracker.log_usage(
                            db=db,
                            user_id=current_user.id,
                            operation="tts_stream",
                            character_count=char_count,
                            voice_id=voice_id,
                            model_id=model_id,
                            latency_ms=latency_ms,
                            status_code=500,
                        )
                    except Exception:
                        pass
                    raise e

            return StreamingResponse(tracking_generator(), media_type="audio/mpeg")

        else:
            audio_bytes = await elevenlabs_service.text_to_speech_bytes(
                text=data.text,
                voice_id=voice_id,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            try:
                await usage_tracker.log_usage(
                    db=db,
                    user_id=current_user.id,
                    operation="tts",
                    character_count=char_count,
                    voice_id=voice_id,
                    model_id=model_id,
                    latency_ms=latency_ms,
                    status_code=200,
                )
            except Exception:
                pass
            return Response(content=audio_bytes, media_type="audio/mpeg")

    except ElevenLabsPermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ElevenLabs Permission Error: {e.detail or str(e)}. Please grant required permissions to your API key.",
        )
    except ElevenLabsQuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except ElevenLabsError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Voice synthesis error: {str(e)}")

from app.services.audio_validator import validate_audio_upload

@router.post("/stt")
async def speech_to_text(
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transcribe user spoken audio file into text with input validation."""
    audio_bytes = await validate_audio_upload(audio_file)
    start_time = time.time()
    try:
        transcript = await elevenlabs_service.speech_to_text(
            audio_bytes=audio_bytes,
            filename=audio_file.filename,
            content_type=audio_file.content_type,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        try:
            await usage_tracker.log_usage(
                db=db,
                user_id=current_user.id,
                operation="stt",
                character_count=len(transcript),
                latency_ms=latency_ms,
                status_code=200,
            )
        except Exception as log_err:
            logger.debug(f"STT usage log note: {log_err}")
        return {"text": transcript}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Transcription failed: {str(e)}")

@router.post("/sts")
async def speech_to_speech(
    audio_file: UploadFile = File(...),
    voice_id: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Convert input speech audio directly into target voice (Speech-to-Speech) with input validation."""
    audio_bytes = await validate_audio_upload(audio_file)
    start_time = time.time()
    target_voice = voice_id or (current_user.voice_preference.preferred_voice_id if current_user.voice_preference else None)
    try:
        transformed_audio = await elevenlabs_service.speech_to_speech(
            audio_bytes=audio_bytes,
            voice_id=target_voice,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        try:
            await usage_tracker.log_usage(
                db=db,
                user_id=current_user.id,
                operation="sts",
                character_count=0,
                voice_id=target_voice,
                latency_ms=latency_ms,
                status_code=200,
            )
        except Exception as log_err:
            logger.debug(f"STS usage log note: {log_err}")
        return Response(content=transformed_audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Speech to speech failed: {str(e)}")


@router.post("/turn")
async def process_voice_turn_http(
    payload: VoiceTurnRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    HTTPS voice turn endpoint for serverless environments (e.g., Vercel)
    where persistent WebSockets are unavailable. Executes the full NORE
    Technology Intelligence + Conversational + TTS pipeline in a single turn.
    """
    await check_rate_limit(request, max_requests=60, window=60)
    user_text = (payload.text or "").strip()
    if not user_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text is required")

    start_time = time.time()
    persona_id = payload.persona_id or "executive"

    # Load or create conversation session
    session = None
    if payload.session_id:
        try:
            s_res = await db.execute(
                select(ConversationSession)
                .where(ConversationSession.id == payload.session_id, ConversationSession.user_id == current_user.id)
                .options(selectinload(ConversationSession.messages))
            )
            session = s_res.scalar_one_or_none()
        except Exception:
            session = None

    if not session:
        try:
            session = ConversationSession(
                user_id=current_user.id,
                title=user_text[:40] if len(user_text) > 40 else user_text,
                persona_id=persona_id,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            s_res = await db.execute(
                select(ConversationSession)
                .where(ConversationSession.id == session.id)
                .options(selectinload(ConversationSession.messages))
            )
            session = s_res.scalar_one()
        except Exception as e:
            logger.debug(f"Session DB persistence note (stateless mode): {e}")
            session = ConversationSession(id=1, user_id=current_user.id, title=user_text[:40], persona_id=persona_id)

    user_msg_id = 1
    try:
        user_msg = Message(
            session_id=session.id or 1,
            role="user",
            content=user_text,
            characters_count=len(user_text),
        )
        db.add(user_msg)
        await db.commit()
        user_msg_id = user_msg.id
    except Exception:
        pass

    history = [
        {"role": m.role, "content": m.content}
        for m in (getattr(session, "messages", None) or [])[-20:]
    ]

    personality = None
    user_tech_pref = None
    if current_user.voice_preference:
        personality = {
            "assistant_name": getattr(current_user.voice_preference, "assistant_name", "NORE"),
            "tone": getattr(current_user.voice_preference, "tone", "balanced"),
            "formality": getattr(current_user.voice_preference, "formality", "professional"),
            "response_style": getattr(current_user.voice_preference, "response_style", "adaptive"),
            "preferred_language": getattr(current_user.voice_preference, "preferred_language", "en"),
        }
        user_tech_pref = {
            "tech_interests": getattr(current_user.voice_preference, "tech_interests", "ai_ml,software_dev,cybersecurity"),
            "tech_explanation_level": getattr(current_user.voice_preference, "tech_explanation_level", "intermediate"),
            "tech_briefing_topics": getattr(current_user.voice_preference, "tech_briefing_topics", "all"),
            "tech_summary_style": getattr(current_user.voice_preference, "tech_summary_style", "balanced"),
        }

    tech_intent_data = None
    tech_sources_data = None
    fact_check_data = None
    briefing_data = None
    full_reply_text = ""

    try:
        early_classification = tech_classifier.classify(
            user_text,
            user_level_pref=user_tech_pref.get("tech_explanation_level") if user_tech_pref else None,
        )
        tech_intent_data = {
            "type": "tech_intent",
            "intent": early_classification.intent.value,
            "domain": early_classification.primary_domain.value,
            "requires_search": early_classification.requires_search,
            "explanation_level": early_classification.explanation_level.value,
        }

        tech_resp = await tech_orchestrator.process_query(
            user_message=user_text,
            session_id=session.id,
            history=history,
            user_tech_pref=user_tech_pref,
        )
        if tech_resp.sources:
            tech_sources_data = [s.to_dict() for s in tech_resp.sources]
        if tech_resp.fact_check:
            fact_check_data = tech_resp.fact_check.to_dict()
        if tech_resp.briefing:
            briefing_data = tech_resp.briefing.to_dict()
        full_reply_text = tech_resp.spoken_response
    except Exception as e:
        logger.error(f"Tech orchestrator error in HTTP turn: {e}", exc_info=True)

    if not full_reply_text:
        try:
            full_reply_text = await conversational_engine.generate_reply(
                user_message=user_text,
                history=history,
                persona_id=persona_id,
                personality_settings=personality,
            )
        except Exception as e:
            logger.error(f"Conversational engine error in HTTP turn: {e}", exc_info=True)

    full_reply_text = conversational_engine.sanitize_spoken_response(full_reply_text)
    if not full_reply_text:
        full_reply_text = "I couldn't get that information right now. Try again."

    target_voice = payload.voice_id or (
        current_user.voice_preference.preferred_voice_id
        if current_user.voice_preference
        else settings.ELEVENLABS_DEFAULT_VOICE_ID
    )
    stability = current_user.voice_preference.stability if current_user.voice_preference else 0.5
    similarity_boost = current_user.voice_preference.similarity_boost if current_user.voice_preference else 0.75
    char_count = len(full_reply_text)

    audio_b64 = None
    fallback_mode = None
    fallback_reason = None
    fallback_message = None

    has_quota = True
    try:
        has_quota = await usage_tracker.check_quota(db, current_user, requested_characters=char_count)
    except Exception:
        has_quota = True

    if has_quota and settings.ELEVENLABS_API_KEY:
        try:
            pcm_chunks = []
            async for chunk in elevenlabs_service.stream_text_to_speech(
                text=full_reply_text,
                voice_id=target_voice,
                stability=max(0.45, stability),
                similarity_boost=similarity_boost,
                output_format="pcm_24000",
            ):
                if chunk:
                    pcm_chunks.append(chunk)
            raw_pcm = b"".join(pcm_chunks)
            if len(raw_pcm) % 2 != 0:
                raw_pcm += b"\x00"
            if raw_pcm:
                audio_b64 = base64.b64encode(raw_pcm).decode("ascii")
        except Exception as e:
            logger.warning(f"HTTP turn TTS fallback triggered: {e}")
            fallback_mode = "browser_speech"
            fallback_reason = "tts_error"
            fallback_message = "Using browser voice synthesis."
    else:
        fallback_mode = "browser_speech"
        fallback_reason = "no_api_key" if not settings.ELEVENLABS_API_KEY else "quota_exceeded"
        fallback_message = "Using browser voice synthesis."

    latency_ms = int((time.time() - start_time) * 1000)
    assistant_msg_id = 2
    try:
        assistant_msg = Message(
            session_id=session.id or 1,
            role="assistant",
            content=full_reply_text,
            characters_count=char_count,
            latency_ms=latency_ms,
            voice_id=target_voice,
        )
        db.add(assistant_msg)
        await db.commit()
        assistant_msg_id = assistant_msg.id
    except Exception:
        pass

    return {
        "session_id": session.id if session else 1,
        "user_message_id": user_msg_id,
        "message_id": assistant_msg_id,
        "text_response": full_reply_text,
        "tech_intent": tech_intent_data,
        "tech_sources": tech_sources_data,
        "fact_check": fact_check_data,
        "briefing": briefing_data,
        "audio_base64": audio_b64,
        "sample_rate": 24000,
        "channels": 1,
        "fallback": fallback_mode,
        "fallback_reason": fallback_reason,
        "fallback_message": fallback_message,
        "latency_ms": latency_ms,
        "characters": char_count,
    }

