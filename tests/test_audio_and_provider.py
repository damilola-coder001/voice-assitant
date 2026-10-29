import pytest
from httpx import AsyncClient
from app.services.audio_validator import validate_audio_payload, AudioValidationError
from app.services.providers import VoiceProvider, ElevenLabsProvider, get_voice_provider

def test_voice_provider_interface_conformance():
    provider = get_voice_provider("elevenlabs")
    assert isinstance(provider, VoiceProvider)
    assert hasattr(provider, "stream_text_to_speech")
    assert hasattr(provider, "text_to_speech_bytes")
    assert hasattr(provider, "speech_to_speech")
    assert hasattr(provider, "speech_to_text")
    assert hasattr(provider, "get_voices")
    assert hasattr(provider, "get_models")
    assert hasattr(provider, "check_connectivity")

def test_audio_validator_rejects_truncated_input():
    truncated_bytes = b"RIFF" + b"\x00" * 20
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(truncated_bytes, filename="test.wav", content_type="audio/wav")
    assert "too small or truncated" in str(exc.value.detail)

def test_audio_validator_rejects_malicious_pe_file():
    # Simulating Windows executable signature
    malicious_bytes = b"MZ" + b"\x00" * 200
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(malicious_bytes, filename="voice.wav", content_type="audio/wav")
    assert "invalid or malicious content signatures" in str(exc.value.detail)

def test_audio_validator_rejects_invalid_mime():
    valid_header = b"RIFF" + b"\x24\x00\x00\x00WAVEfmt " + b"\x00" * 150
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(valid_header, filename="voice.txt", content_type="text/plain")
    assert "Unsupported audio format" in str(exc.value.detail)

def test_audio_validator_accepts_valid_wav():
    # Minimal 180-byte WAV audio
    valid_wav = b"RIFF" + (180).to_bytes(4, "little") + b"WAVEfmt " + b"\x10\x00\x00\x00" + b"\x00" * 150
    # Should not raise
    validate_audio_payload(valid_wav, filename="audio.wav", content_type="audio/wav")

@pytest.mark.asyncio
async def test_stt_endpoint_rejects_invalid_audio(client: AsyncClient, user_token: str):
    headers = {"Authorization": f"Bearer {user_token}"}
    files = {"audio_file": ("test.exe", b"MZThisIsAnExecutableFile" + b"\x00" * 200, "application/octet-stream")}

    res = await client.post("/api/speech/stt", headers=headers, files=files)
    assert res.status_code == 400
    assert "invalid or malicious" in res.json()["detail"]
