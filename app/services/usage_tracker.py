from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import ElevenLabsUsageLog
from app.models.user import User

# Standard ElevenLabs cost estimate benchmark ($0.30 per 1,000 characters for turbo models)
COST_PER_1K_CHARS = 0.30

class UsageTracker:
    """Tracks and enforces ElevenLabs character quotas and API usage."""

    @staticmethod
    def calculate_cost(character_count: int) -> float:
        return round((character_count / 1000.0) * COST_PER_1K_CHARS, 6)

    @classmethod
    async def log_usage(
        cls,
        db: AsyncSession,
        user_id: Optional[int],
        operation: str,
        character_count: int,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        audio_duration_seconds: Optional[float] = None,
        latency_ms: int = 0,
        status_code: int = 200,
    ) -> ElevenLabsUsageLog:
        """Persist a usage record in the database."""
        cost = cls.calculate_cost(character_count)
        log_entry = ElevenLabsUsageLog(
            user_id=user_id,
            operation=operation,
            character_count=character_count,
            voice_id=voice_id,
            model_id=model_id,
            audio_duration_seconds=audio_duration_seconds,
            latency_ms=latency_ms,
            status_code=status_code,
            estimated_cost_usd=cost,
        )
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        return log_entry

    @classmethod
    async def get_user_today_usage(cls, db: AsyncSession, user_id: int) -> int:
        """Sum characters used by user in the current UTC day."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = (
            select(func.coalesce(func.sum(ElevenLabsUsageLog.character_count), 0))
            .where(
                ElevenLabsUsageLog.user_id == user_id,
                ElevenLabsUsageLog.created_at >= today_start,
                ElevenLabsUsageLog.status_code == 200,
            )
        )
        result = await db.execute(query)
        return int(result.scalar() or 0)

    @classmethod
    async def check_quota(cls, db: AsyncSession, user: User, requested_characters: int = 0) -> bool:
        """Returns True if user has sufficient quota for today's requests."""
        if user.role.value == "admin":
            return True  # Admins have unlimited quota

        used_today = await cls.get_user_today_usage(db, user.id)
        return (used_today + requested_characters) <= user.daily_character_quota

usage_tracker = UsageTracker()
