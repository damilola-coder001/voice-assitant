import pytest
from app.services.elevenlabs import elevenlabs_service, FALLBACK_VOICES, FALLBACK_MODELS

@pytest.mark.asyncio
async def test_fallback_voices_available():
    voices = await elevenlabs_service.get_voices()
    assert len(voices) > 0
    for v in voices:
        assert "voice_id" in v and v["voice_id"]
        assert "name" in v and v["name"]

@pytest.mark.asyncio
async def test_fallback_models_available():
    models = await elevenlabs_service.get_models()
    assert len(models) > 0
    model_ids = [m["model_id"] for m in models]
    assert "eleven_turbo_v2_5" in model_ids

@pytest.mark.asyncio
async def test_elevenlabs_connectivity_check():
    status = await elevenlabs_service.check_connectivity()
    assert "status" in status
    assert status["status"] in ["connected", "scoped_restricted", "not_configured", "error", "unreachable"]
