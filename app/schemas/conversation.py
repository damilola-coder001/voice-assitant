from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class MessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    audio_url: Optional[str] = None
    audio_duration_ms: Optional[int] = None
    characters_count: Optional[int] = 0
    latency_ms: Optional[int] = None
    voice_id: Optional[str] = None

class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    audio_url: Optional[str] = None
    audio_duration_ms: Optional[int] = None
    characters_count: int
    latency_ms: Optional[int] = None
    voice_id: Optional[str] = None
    created_at: datetime

class SessionCreate(BaseModel):
    title: Optional[str] = "New Voice Session"
    persona_id: Optional[str] = "executive"
    system_prompt: Optional[str] = None

class SessionUpdate(BaseModel):
    title: Optional[str] = None
    persona_id: Optional[str] = None
    system_prompt: Optional[str] = None

class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    persona_id: str
    system_prompt: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageRead] = Field(default_factory=list)

class SessionBriefRead(BaseModel):
    id: int
    title: str
    persona_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime

class ConversationExport(BaseModel):
    session_id: int
    title: str
    persona_id: str
    created_at: datetime
    messages: List[MessageRead]
    export_format: str
