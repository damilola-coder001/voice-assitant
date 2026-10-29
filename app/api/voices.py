from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.models.user import User
from app.schemas.voice import VoiceCatalogItem, VoicePreviewRequest
from app.security.dependencies import get_current_user
from app.services.elevenlabs import elevenlabs_service

router = APIRouter(prefix="/voices", tags=["Voices"])

@router.get("", response_model=List[VoiceCatalogItem])
async def list_voices(current_user: User = Depends(get_current_user)):
    """Return available ElevenLabs voices with fallback catalog."""
    voices = await elevenlabs_service.get_voices()
    return voices

@router.get("/models")
async def list_models(current_user: User = Depends(get_current_user)):
    """Return available ElevenLabs synthesis models."""
    models = await elevenlabs_service.get_models()
    return models

@router.post("/preview")
async def preview_voice(
    data: VoicePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate a quick voice audio sample for voice selection in UI."""
    try:
        audio_bytes = await elevenlabs_service.text_to_speech_bytes(
            text=data.text or "Hello! I am NORE, ready to be your voice assistant.",
            voice_id=data.voice_id,
        )
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to generate voice preview: {str(e)}",
        )
