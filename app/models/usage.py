from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User

class ElevenLabsUsageLog(Base):
    __tablename__ = "elevenlabs_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    operation: Mapped[str] = mapped_column(String(50), nullable=False)  # tts, stt, sts, voices, user_info
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="usage_logs")
