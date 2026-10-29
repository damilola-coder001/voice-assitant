import time
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.voice import TTSRequest
from app.security.dependencies import get_current_user
from app.security.rate_limiter import check_rate_limit
from app.services.elevenlabs import (
    ElevenLabsError,
    ElevenLabsPermissionError,
    ElevenLabsQuotaExceededError,
    elevenlabs_service,
)
from app.services.usage_tracker import usage_tracker

router = APIRouter(prefix="/speech", tags=["Speech"])

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
                except Exception as e:
                    latency_ms = int((time.time() - start_time) * 1000)
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
        await usage_tracker.log_usage(
            db=db,
            user_id=current_user.id,
            operation="stt",
            character_count=len(transcript),
            latency_ms=latency_ms,
            status_code=200,
        )
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
        await usage_tracker.log_usage(
            db=db,
            user_id=current_user.id,
            operation="sts",
            character_count=0,
            voice_id=target_voice,
            latency_ms=latency_ms,
            status_code=200,
        )
        return Response(content=transformed_audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Speech to speech failed: {str(e)}")
