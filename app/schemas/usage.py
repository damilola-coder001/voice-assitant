from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class UsageSummary(BaseModel):
    user_id: int
    characters_used_today: int
    daily_quota: int
    quota_remaining: int
    percent_quota_used: float
    total_audio_seconds: float
    total_operations: int

class UsageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation: str
    character_count: int
    voice_id: Optional[str]
    model_id: Optional[str]
    audio_duration_seconds: Optional[float]
    latency_ms: int
    status_code: int
    estimated_cost_usd: float
    created_at: datetime
