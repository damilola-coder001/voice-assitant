from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserVoicePreferenceSchema(BaseModel):
    preferred_voice_id: str = "CwhRBWXzGAHq8TQ4Fs17"
    preferred_voice_name: str = "Roger"
    preferred_model_id: str = "eleven_turbo_v2_5"
    stability: float = Field(0.5, ge=0.0, le=1.0)
    similarity_boost: float = Field(0.75, ge=0.0, le=1.0)
    style: float = Field(0.0, ge=0.0, le=1.0)
    use_speaker_boost: bool = True
    speed: float = Field(1.0, ge=0.5, le=2.0)
    auto_speak: bool = True
    active_persona_id: str = "executive"
    assistant_name: str = "NORE"
    tone: str = "balanced"
    formality: str = "professional"
    response_style: str = "adaptive"
    preferred_language: str = "en"
    tech_interests: str = "ai_ml,software_dev,cybersecurity"
    tech_explanation_level: str = "intermediate"
    tech_briefing_topics: str = "all"
    tech_summary_style: str = "balanced"

class UserVoicePreferenceUpdate(BaseModel):
    preferred_voice_id: Optional[str] = None
    preferred_voice_name: Optional[str] = None
    preferred_model_id: Optional[str] = None
    stability: Optional[float] = Field(None, ge=0.0, le=1.0)
    similarity_boost: Optional[float] = Field(None, ge=0.0, le=1.0)
    style: Optional[float] = Field(None, ge=0.0, le=1.0)
    use_speaker_boost: Optional[bool] = None
    speed: Optional[float] = Field(None, ge=0.5, le=2.0)
    auto_speak: Optional[bool] = None
    active_persona_id: Optional[str] = None
    assistant_name: Optional[str] = None
    tone: Optional[str] = None
    formality: Optional[str] = None
    response_style: Optional[str] = None
    preferred_language: Optional[str] = None
    tech_interests: Optional[str] = None
    tech_explanation_level: Optional[str] = None
    tech_briefing_topics: Optional[str] = None
    tech_summary_style: Optional[str] = None

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: str = "active"
    is_active: bool
    daily_character_quota: int
    created_at: datetime
    last_login_at: Optional[datetime] = None
    voice_preference: Optional[UserVoicePreferenceSchema] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)

class UserRoleUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    daily_character_quota: Optional[int] = None

class AdminCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, description="Password must be at least 12 characters")
    full_name: Optional[str] = "Platform Admin"

class UserPatchRequest(BaseModel):
    full_name: Optional[str] = None
    daily_character_quota: Optional[int] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    role: Optional[str] = None

