import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.conversation import ConversationSession
    from app.models.usage import ElevenLabsUsageLog

class RoleEnum(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(
        Enum(RoleEnum, values_callable=lambda x: [e.value for e in x], native_enum=False, length=20),
        default=RoleEnum.USER,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    daily_character_quota: Mapped[int] = mapped_column(Integer, default=50000, nullable=False)
    
    # Security & Session Controls
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    voice_preference: Mapped[Optional["UserVoicePreference"]] = relationship(
        "UserVoicePreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    conversations: Mapped[List["ConversationSession"]] = relationship(
        "ConversationSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    usage_logs: Mapped[List["ElevenLabsUsageLog"]] = relationship(
        "ElevenLabsUsageLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )

class UserVoicePreference(Base):
    __tablename__ = "user_voice_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    preferred_voice_id: Mapped[str] = mapped_column(String(100), default="CwhRBWXzGAHq8TQ4Fs17", nullable=False)
    preferred_model_id: Mapped[str] = mapped_column(String(100), default="eleven_turbo_v2_5", nullable=False)
    preferred_voice_name: Mapped[str] = mapped_column(String(100), default="Roger", nullable=False)
    stability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    similarity_boost: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    style: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    use_speaker_boost: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    speed: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    auto_speak: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_persona_id: Mapped[str] = mapped_column(String(50), default="executive", nullable=False)
    assistant_name: Mapped[str] = mapped_column(String(50), default="NORE", nullable=False)
    tone: Mapped[str] = mapped_column(String(50), default="balanced", nullable=False)
    formality: Mapped[str] = mapped_column(String(50), default="professional", nullable=False)
    response_style: Mapped[str] = mapped_column(String(50), default="adaptive", nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)

    # Technology Intelligence Preferences
    tech_interests: Mapped[str] = mapped_column(String(255), default="ai_ml,software_dev,cybersecurity", nullable=False)
    tech_explanation_level: Mapped[str] = mapped_column(String(50), default="intermediate", nullable=False)
    tech_briefing_topics: Mapped[str] = mapped_column(String(255), default="all", nullable=False)
    tech_summary_style: Mapped[str] = mapped_column(String(50), default="balanced", nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="voice_preference")
