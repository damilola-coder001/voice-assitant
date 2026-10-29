"""Initial schema with users, preferences, conversations, messages, and audit logs

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-14 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("daily_character_quota", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    # User voice preferences
    op.create_table(
        "user_voice_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("preferred_voice_id", sa.String(length=100), nullable=False, server_default="21m00Tcm4TlvDq8ikWAM"),
        sa.Column("preferred_voice_name", sa.String(length=100), nullable=False, server_default="Rachel"),
        sa.Column("preferred_model_id", sa.String(length=100), nullable=False, server_default="eleven_turbo_v2_5"),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("similarity_boost", sa.Float(), nullable=False, server_default="0.75"),
        sa.Column("style", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("use_speaker_boost", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("speed", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("auto_speak", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("active_persona_id", sa.String(length=50), nullable=False, server_default="executive"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_voice_preferences_user_id", "user_voice_preferences", ["user_id"], unique=True)

    # Conversation sessions
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("persona_id", sa.String(length=50), nullable=False, server_default="executive"),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_sessions_user_id", "conversation_sessions", ["user_id"], unique=False)

    # Messages
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("audio_duration_ms", sa.Integer(), nullable=True),
        sa.Column("characters_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("voice_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"], unique=False)

    # Usage logs
    op.create_table(
        "elevenlabs_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voice_id", sa.String(length=100), nullable=True),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_elevenlabs_usage_logs_created_at", "elevenlabs_usage_logs", ["created_at"], unique=False)
    op.create_index("ix_elevenlabs_usage_logs_user_id", "elevenlabs_usage_logs", ["user_id"], unique=False)

    # Audit logs
    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="INFO"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_logs_created_at", "security_audit_logs", ["created_at"], unique=False)
    op.create_index("ix_security_audit_logs_event_type", "security_audit_logs", ["event_type"], unique=False)

def downgrade() -> None:
    op.drop_table("security_audit_logs")
    op.drop_table("elevenlabs_usage_logs")
    op.drop_table("messages")
    op.drop_table("conversation_sessions")
    op.drop_table("user_voice_preferences")
    op.drop_table("users")
