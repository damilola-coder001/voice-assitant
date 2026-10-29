from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

class AdminDashboardStats(BaseModel):
    total_users: int
    active_users: int
    total_conversations: int
    total_messages: int
    total_characters_consumed: int
    total_audio_seconds: float
    estimated_total_cost_usd: float
    elevenlabs_subscription_tier: Optional[str] = None
    elevenlabs_characters_remaining: Optional[int] = None
    elevenlabs_characters_limit: Optional[int] = None
    elevenlabs_key_status: str  # "active", "scoped_restricted", "missing", "error"
    system_uptime_seconds: float

class SystemHealthResponse(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    app_version: str
    environment: str
    database: str
    redis: str
    elevenlabs_status: str
    elevenlabs_permission_detail: Optional[str] = None
    timestamp: datetime

class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    user_id: Optional[int]
    email: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    severity: str
    details: Optional[str]
    created_at: datetime

class SecretScanResponse(BaseModel):
    scanned_files_count: int
    findings_count: int
    status: str
    findings: List[Dict[str, Any]]
