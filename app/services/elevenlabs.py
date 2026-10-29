import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from app.config import settings
from app.services.providers.base import VoiceProvider

logger = logging.getLogger(__name__)

class ElevenLabsError(Exception):
    """Base exception for ElevenLabs operations."""
    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail

class ElevenLabsPermissionError(ElevenLabsError):
    """Raised when the API key lacks necessary permissions."""
    pass

class ElevenLabsQuotaExceededError(ElevenLabsError):
    """Raised when ElevenLabs account characters or credits are exhausted."""
    pass

# Built-in fallback voices verified to work on this account
FALLBACK_VOICES: List[Dict[str, Any]] = [
    {
        "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
        "name": "Roger",
        "category": "premade",
        "description": "Laid-back, casual, resonant American male voice.",
        "labels": {"accent": "american", "gender": "male", "age": "middle aged", "use_case": "conversation"},
        "samples": [],
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Sarah",
        "category": "premade",
        "description": "Mature, reassuring, confident female voice.",
        "labels": {"accent": "american", "gender": "female", "age": "young", "use_case": "narration"},
        "samples": [],
    },
    {
        "voice_id": "FGY2WhTYpPnrIDTdsKH5",
        "name": "Laura",
        "category": "premade",
        "description": "Enthusiastic, quirky attitude female voice.",
        "labels": {"accent": "american", "gender": "female", "age": "young", "use_case": "social media"},
        "samples": [],
    },
    {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie",
        "category": "premade",
        "description": "Deep, confident, energetic Australian male voice.",
        "labels": {"accent": "australian", "gender": "male", "age": "middle aged", "use_case": "conversational"},
        "samples": [],
    },
    {
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George",
        "category": "premade",
        "description": "Warm, captivating British storyteller voice.",
        "labels": {"accent": "british", "gender": "male", "age": "middle aged", "use_case": "storytelling"},
        "samples": [],
    },
    {
        "voice_id": "Xb7hH8MSUJpSbSDYk0k2",
        "name": "Alice",
        "category": "premade",
        "description": "Clear, engaging British educator female voice.",
        "labels": {"accent": "british", "gender": "female", "age": "middle aged", "use_case": "education"},
        "samples": [],
    },
    {
        "voice_id": "cgSgspJ2msm6clMCkdW9",
        "name": "Jessica",
        "category": "premade",
        "description": "Playful, bright, warm American female voice.",
        "labels": {"accent": "american", "gender": "female", "age": "young", "use_case": "conversational"},
        "samples": [],
    },
    {
        "voice_id": "hpp4J3VqNfWAUOO0d1Us",
        "name": "Bella",
        "category": "premade",
        "description": "Professional, bright, warm American female voice.",
        "labels": {"accent": "american", "gender": "female", "age": "young", "use_case": "narration"},
        "samples": [],
    },
    {
        "voice_id": "nPczCjzI2devNBz1zQrb",
        "name": "Brian",
        "category": "premade",
        "description": "Deep, resonant, comforting American male voice.",
        "labels": {"accent": "american", "gender": "male", "age": "middle aged", "use_case": "narration"},
        "samples": [],
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "category": "premade",
        "description": "Dominant, firm American male voice.",
        "labels": {"accent": "american", "gender": "male", "age": "middle aged", "use_case": "narration"},
        "samples": [],
    },
]

# Standard ElevenLabs Models
FALLBACK_MODELS: List[Dict[str, Any]] = [
    {
        "model_id": "eleven_turbo_v2_5",
        "name": "Eleven Turbo v2.5",
        "description": "Fastest multilingual model with lowest latency (ideal for real-time voice).",
        "can_do_text_to_speech": True,
        "can_do_voice_conversion": True,
    },
    {
        "model_id": "eleven_multilingual_v2",
        "name": "Eleven Multilingual v2",
        "description": "State-of-the-art multilingual model with highest emotional range.",
        "can_do_text_to_speech": True,
        "can_do_voice_conversion": True,
    },
    {
        "model_id": "eleven_monolingual_v1",
        "name": "Eleven English v1",
        "description": "Standard high quality English model.",
        "can_do_text_to_speech": True,
        "can_do_voice_conversion": True,
    },
]

class ElevenLabsService(VoiceProvider):
    """Production service for secure server-side ElevenLabs communication."""

    def __init__(self):
        self.base_url = settings.ELEVENLABS_BASE_URL.rstrip("/")
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def api_key(self) -> str:
        return settings.ELEVENLABS_API_KEY

    def _get_headers(self, accept: str = "application/json") -> Dict[str, str]:
        headers = {
            "Accept": accept,
            "xi-api-key": self.api_key,
        }
        return headers

    async def get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            finally:
                self._http_client = None

    def _handle_error_response(self, response: httpx.Response, operation: str = "ElevenLabs API"):
        """Sanitize error messages to prevent secret leaks and identify permissions."""
        status_code = response.status_code
        try:
            body = response.json()
            detail_info = body.get("detail", {})
            if isinstance(detail_info, dict):
                msg = detail_info.get("message", response.text[:200])
                status_str = detail_info.get("status", "")
            else:
                msg = str(detail_info)
                status_str = ""
        except Exception:
            msg = response.text[:200]
            status_str = ""

        logger.warning(f"ElevenLabs error during {operation} (status {status_code}): {msg}")

        lower_msg = (msg or "").lower()
        status_str_lower = (status_str or "").lower()

        # Check for Quota Exceeded (ElevenLabs returns HTTP 401 or 429 when character quota is exhausted)
        if status_code in (401, 429) and (
            status_str_lower in ("quota_exceeded", "rate_limit_exceeded")
            or any(kw in lower_msg for kw in ("exceeds your quota", "quota_exceeded", "credits remaining", "rate limit", "quota exceeded"))
        ):
            raise ElevenLabsQuotaExceededError(
                f"ElevenLabs voice quota reached: {msg}",
                status_code=429,
                detail=msg,
            )

        if status_code == 401:
            if "missing the permission" in lower_msg or status_str_lower == "missing_permissions":
                raise ElevenLabsPermissionError(
                    f"ElevenLabs API Key is missing permissions for {operation}: {msg}. "
                    f"Please update your API key in the ElevenLabs dashboard settings.",
                    status_code=401,
                    detail=msg,
                )
            raise ElevenLabsError("Invalid ElevenLabs API Key. Please check your configuration.", status_code=401)
        elif status_code == 429:
            raise ElevenLabsQuotaExceededError("ElevenLabs quota or rate limit exceeded.", status_code=429, detail=msg)
        else:
            raise ElevenLabsError(f"ElevenLabs error ({status_code}): {msg}", status_code=status_code, detail=msg)

    async def check_connectivity(self) -> Dict[str, Any]:
        """Check ElevenLabs credentials and return status without leaking secrets."""
        if not self.api_key:
            return {
                "status": "not_configured",
                "message": "ELEVENLABS_API_KEY is not set in environment.",
                "permissions_ok": False,
            }

        client = await self.get_client()
        try:
            res = await client.get(f"{self.base_url}/user", headers=self._get_headers())
            if res.status_code == 200:
                data = res.json()
                sub = data.get("subscription", {})
                return {
                    "status": "connected",
                    "tier": sub.get("tier", "unknown"),
                    "character_count": sub.get("character_count", 0),
                    "character_limit": sub.get("character_limit", 0),
                    "permissions_ok": True,
                }
            elif res.status_code == 401 and "missing the permission" in res.text:
                return {
                    "status": "scoped_restricted",
                    "message": "API key valid but scoped (missing user_read or voice permissions).",
                    "permissions_ok": False,
                    "detail": res.text[:200],
                }
            else:
                return {
                    "status": "error",
                    "status_code": res.status_code,
                    "message": res.text[:200],
                    "permissions_ok": False,
                }
        except Exception as e:
            return {
                "status": "unreachable",
                "message": f"Network error connecting to ElevenLabs: {str(e)}",
                "permissions_ok": False,
            }

    async def get_voices(self) -> List[Dict[str, Any]]:
        """Fetch list of available voices with automatic fallback catalog."""
        if not self.api_key:
            return FALLBACK_VOICES

        client = await self.get_client()
        try:
            res = await client.get(f"{self.base_url}/voices", headers=self._get_headers())
            if res.status_code == 200:
                voices = res.json().get("voices", [])
                formatted = []
                for v in voices:
                    formatted.append({
                        "voice_id": v.get("voice_id"),
                        "name": v.get("name"),
                        "category": v.get("category", "premade"),
                        "description": v.get("description"),
                        "preview_url": v.get("preview_url"),
                        "labels": v.get("labels", {}),
                        "samples": v.get("samples", []),
                    })
                return formatted
            else:
                logger.warning(f"Unable to fetch remote voices ({res.status_code}), using fallback catalog.")
                return FALLBACK_VOICES
        except Exception as e:
            logger.error(f"Error fetching ElevenLabs voices: {e}. Using fallback voices.")
            return FALLBACK_VOICES

    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch list of models with fallback."""
        if not self.api_key:
            return FALLBACK_MODELS

        client = await self.get_client()
        try:
            res = await client.get(f"{self.base_url}/models", headers=self._get_headers())
            if res.status_code == 200:
                return res.json()
            return FALLBACK_MODELS
        except Exception:
            return FALLBACK_MODELS

    async def stream_text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        optimize_streaming_latency: int = 3,
        output_format: str = "pcm_24000",
        **kwargs,
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio chunks for text-to-speech with ultra-low latency and zero frame cracking."""
        voice_id = voice_id or settings.ELEVENLABS_DEFAULT_VOICE_ID
        model_id = model_id or settings.ELEVENLABS_DEFAULT_MODEL_ID

        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.", status_code=500)

        url = f"{self.base_url}/text-to-speech/{voice_id}/stream"
        params = {
            "optimize_streaming_latency": str(optimize_streaming_latency),
            "output_format": output_format,
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": max(0.45, stability),
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": use_speaker_boost,
            },
        }

        client = await self.get_client()
        accept_header = "audio/pcm" if "pcm" in output_format else "audio/mpeg"
        headers = self._get_headers(accept=accept_header)

        async with client.stream("POST", url, params=params, json=payload, headers=headers) as response:
            if response.status_code != 200:
                body = await response.aread()
                # Create synthetic response for error handler
                dummy_res = httpx.Response(response.status_code, content=body)
                self._handle_error_response(dummy_res, operation="Text-to-Speech")

            async for chunk in response.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk

    async def text_to_speech_bytes(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        output_format: str = "mp3_44100_128",
        **kwargs,
    ) -> bytes:
        """Non-streaming text-to-speech returning full audio bytes."""
        audio_chunks = []
        async for chunk in self.stream_text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            stability=stability,
            similarity_boost=similarity_boost,
            output_format=output_format,
            **kwargs,
        ):
            audio_chunks.append(chunk)
        return b"".join(audio_chunks)

    async def speech_to_speech(
        self,
        audio_bytes: bytes,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> bytes:
        """Convert input speech audio to target ElevenLabs voice."""
        voice_id = voice_id or settings.ELEVENLABS_DEFAULT_VOICE_ID
        model_id = model_id or "eleven_english_sts_v2"

        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.", status_code=500)

        url = f"{self.base_url}/speech-to-speech/{voice_id}/stream"
        client = await self.get_client()

        files = {"audio": ("input.mp3", audio_bytes, "audio/mpeg")}
        data = {
            "model_id": model_id,
            "voice_settings": json.dumps({
                "stability": stability,
                "similarity_boost": similarity_boost,
            }),
        }
        headers = {"xi-api-key": self.api_key, "Accept": "audio/mpeg"}

        response = await client.post(url, data=data, files=files, headers=headers)
        if response.status_code != 200:
            self._handle_error_response(response, operation="Speech-to-Speech")

        return response.content

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        model_id: str = "scribe_v1",
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Transcribe audio using ElevenLabs Speech-to-Text API."""
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.", status_code=500)

        url = f"{self.base_url}/speech-to-text"
        client = await self.get_client()

        actual_name = filename or "audio.wav"
        actual_mime = content_type or "audio/wav"

        # Inspect magic bytes to match the exact container format
        if audio_bytes.startswith(b"RIFF"):
            actual_name = "audio.wav"
            actual_mime = "audio/wav"
        elif audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            actual_name = "audio.webm"
            actual_mime = "audio/webm"
        elif audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb") or audio_bytes.startswith(b"\xff\xf3"):
            actual_name = "audio.mp3"
            actual_mime = "audio/mpeg"
        elif audio_bytes.startswith(b"OggS"):
            actual_name = "audio.ogg"
            actual_mime = "audio/ogg"

        files = {"file": (actual_name, audio_bytes, actual_mime)}
        data = {"model_id": model_id}
        headers = {"xi-api-key": self.api_key}

        response = await client.post(url, data=data, files=files, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("text", "")
        else:
            self._handle_error_response(response, operation="Speech-to-Text")
            return ""

elevenlabs_service = ElevenLabsService()
