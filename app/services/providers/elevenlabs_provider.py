from app.services.elevenlabs import ElevenLabsService, elevenlabs_service

# ElevenLabsProvider implementation conforming to VoiceProvider
ElevenLabsProvider = ElevenLabsService
default_elevenlabs_provider = elevenlabs_service

__all__ = ["ElevenLabsProvider", "default_elevenlabs_provider"]
