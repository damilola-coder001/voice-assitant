from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class VoiceSettingsSchema(BaseModel):
    stability: float = Field(0.5, ge=0.0, le=1.0)
    similarity_boost: float = Field(0.75, ge=0.0, le=1.0)
    style: float = Field(0.0, ge=0.0, le=1.0)
    use_speaker_boost: bool = True

class VoiceCatalogItem(BaseModel):
    voice_id: str
    name: str
    category: Optional[str] = "premade"
    description: Optional[str] = None
    preview_url: Optional[str] = None
    labels: Optional[Dict[str, str]] = Field(default_factory=dict)
    samples: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    voice_settings: Optional[VoiceSettingsSchema] = None
    session_id: Optional[int] = None

class STSRequest(BaseModel):
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    voice_settings: Optional[VoiceSettingsSchema] = None

class VoicePreviewRequest(BaseModel):
    voice_id: str
    text: Optional[str] = "Hello! This is a preview of my voice generated with ElevenLabs."
