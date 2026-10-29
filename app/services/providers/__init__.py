from app.services.providers.base import VoiceProvider
from app.services.providers.factory import get_voice_provider, register_voice_provider

def __getattr__(name: str):
    if name in ("ElevenLabsProvider", "default_elevenlabs_provider"):
        from app.services.elevenlabs import ElevenLabsService, elevenlabs_service
        if name == "ElevenLabsProvider":
            return ElevenLabsService
        return elevenlabs_service
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "VoiceProvider",
    "ElevenLabsProvider",
    "default_elevenlabs_provider",
    "get_voice_provider",
    "register_voice_provider",
]
