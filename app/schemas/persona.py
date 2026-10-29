from typing import List, Optional
from pydantic import BaseModel, Field

class PersonaPreset(BaseModel):
    id: str
    name: str
    tagline: str
    description: str
    avatar_emoji: str
    system_prompt: str
    recommended_voice_name: str
    temperature: float = Field(0.7, ge=0.0, le=1.5)

class PersonaConfig(BaseModel):
    id: str
    name: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 500
    voice_id: Optional[str] = None
