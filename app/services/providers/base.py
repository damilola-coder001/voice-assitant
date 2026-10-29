from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

class VoiceProvider(ABC):
    """
    Abstract Voice Provider interface as specified in Section 20 of the Architecture PDR.
    Allows pluggable voice synthesis and transcription engines (ElevenLabs, OpenAI, Google, Azure).
    """

    @abstractmethod
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
        **kwargs,
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized binary audio chunks with low latency."""
        pass

    @abstractmethod
    async def text_to_speech_bytes(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        **kwargs,
    ) -> bytes:
        """Synthesize text to speech returning complete audio bytes."""
        pass

    @abstractmethod
    async def speech_to_speech(
        self,
        audio_bytes: bytes,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        **kwargs,
    ) -> bytes:
        """Convert input speech audio to target voice."""
        pass

    @abstractmethod
    async def speech_to_text(self, audio_bytes: bytes, model_id: Optional[str] = None) -> str:
        """Transcribe speech audio to text transcript."""
        pass

    @abstractmethod
    async def get_voices(self) -> List[Dict[str, Any]]:
        """Fetch available voice profiles."""
        pass

    @abstractmethod
    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch supported synthesis models."""
        pass

    @abstractmethod
    async def check_connectivity(self) -> Dict[str, Any]:
        """Perform provider health check and quota verification."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Dispose client connections gracefully."""
        pass
