from typing import Dict
from app.services.providers.base import VoiceProvider

_PROVIDERS: Dict[str, VoiceProvider] = {}

def get_voice_provider(name: str = "elevenlabs") -> VoiceProvider:
    """
    Factory function returning the configured VoiceProvider instance.
    Uses deferred loading to eliminate circular imports.
    """
    key = name.lower()
    if key not in _PROVIDERS:
        if key == "elevenlabs":
            from app.services.elevenlabs import elevenlabs_service
            _PROVIDERS["elevenlabs"] = elevenlabs_service
        else:
            raise ValueError(f"Unknown voice provider '{name}'. Supported: ['elevenlabs']")
    return _PROVIDERS[key]

def register_voice_provider(name: str, provider: VoiceProvider) -> None:
    """Register an additional voice provider implementation."""
    _PROVIDERS[name.lower()] = provider
