from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    # Event types: login_success, login_failed, register, password_change, role_change, rate_limit_exceeded, secret_scan, websocket_connect, unauthorized_access
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO", nullable=False)  # INFO, WARNING, CRITICAL
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
