import time
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit import SecurityAuditLog
from app.models.conversation import ConversationSession, Message
from app.models.usage import ElevenLabsUsageLog
from app.models.user import RoleEnum, User
from app.schemas.admin import (
    AdminDashboardStats,
    AuditLogItem,
    SystemHealthResponse,
)
from app.schemas.user import UserRead, UserRoleUpdate
from app.security.authorization import AuthorizationPolicy
from app.security.dependencies import require_admin_or_owner, require_owner
from app.services.elevenlabs import elevenlabs_service
from app.config import settings

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])

# Global application start timestamp for uptime tracking
START_TIME = time.time()

@router.get("/stats", response_model=AdminDashboardStats)
async def get_admin_dashboard_stats(
    admin: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve comprehensive system telemetry, usage metrics, and ElevenLabs status."""
    user_count = await db.scalar(select(func.count(User.id)))
    active_user_count = await db.scalar(select(func.count(User.id)).where(User.is_active == True))
    session_count = await db.scalar(select(func.count(ConversationSession.id)))
    message_count = await db.scalar(select(func.count(Message.id)))

    total_chars = await db.scalar(select(func.coalesce(func.sum(ElevenLabsUsageLog.character_count), 0)))
    total_duration = await db.scalar(select(func.coalesce(func.sum(ElevenLabsUsageLog.audio_duration_seconds), 0.0)))
    total_cost = await db.scalar(select(func.coalesce(func.sum(ElevenLabsUsageLog.estimated_cost_usd), 0.0)))

    el_status = await elevenlabs_service.check_connectivity()

    return AdminDashboardStats(
        total_users=user_count or 0,
        active_users=active_user_count or 0,
        total_conversations=session_count or 0,
        total_messages=message_count or 0,
        total_characters_consumed=int(total_chars or 0),
        total_audio_seconds=float(total_duration or 0.0),
        estimated_total_cost_usd=round(float(total_cost or 0.0), 4),
        elevenlabs_subscription_tier=el_status.get("tier"),
        elevenlabs_characters_remaining=el_status.get("character_limit", 0) - el_status.get("character_count", 0) if "character_limit" in el_status else None,
        elevenlabs_characters_limit=el_status.get("character_limit"),
        elevenlabs_key_status=el_status.get("status", "unknown"),
        system_uptime_seconds=round(time.time() - START_TIME, 1),
    )

@router.get("/users", response_model=List[UserRead])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    admin: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """List all registered users with pagination and search."""
    query = select(User).options(selectinload(User.voice_preference)).order_by(User.id.asc()).offset(skip).limit(limit)
    if search:
        query = query.where(User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%"))

    result = await db.execute(query)
    return result.scalars().all()

@router.put("/users/{user_id}/role", response_model=UserRead)
async def update_user_role_or_status(
    user_id: int,
    data: UserRoleUpdate,
    admin: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign or modify user roles (ADMIN, USER), quota, and status.
    Strictly protected by AuthorizationPolicy:
    - Admins cannot modify or demote the Owner (Section 10).
    - Admins cannot modify peer Admins (Section 13).
    - Nobody can promote any user to Owner.
    - Only Owner can promote or demote Admins.
    """
    query = select(User).where(User.id == user_id).options(selectinload(User.voice_preference))
    result = await db.execute(query)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # 1. Enforce target management authorization
    AuthorizationPolicy.can_manage_target(admin, target_user, operation="change_role")

    # 2. Handle role transition if requested
    if data.role:
        try:
            new_role = RoleEnum(data.role.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{data.role}'. Permitted roles: {[r.value for r in RoleEnum if r != RoleEnum.OWNER]}",
            )
        AuthorizationPolicy.can_assign_role(admin, target_user, new_role)
        target_user.role = new_role

    if data.status:
        target_user.status = data.status
        if data.status == "suspended":
            target_user.is_active = False

    if data.is_active is not None:
        target_user.is_active = data.is_active
        if not data.is_active and target_user.status == "active":
            target_user.status = "suspended"
        elif data.is_active and target_user.status == "suspended":
            target_user.status = "active"

    if data.daily_character_quota is not None:
        target_user.daily_character_quota = data.daily_character_quota

    # Audit log
    audit = SecurityAuditLog(
        event_type="role_change",
        user_id=admin.id,
        email=admin.email,
        details=f"Principal {admin.email} ({admin.role.value}) modified user {target_user.email} (Role: {target_user.role.value}, Status: {target_user.status})",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(target_user)
    return target_user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete a user account.
    Owner account cannot be deleted by anyone.
    Admins can only delete normal users.
    """
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    AuthorizationPolicy.can_manage_target(admin, target_user, operation="delete")

    audit = SecurityAuditLog(
        event_type="user_deleted",
        user_id=admin.id,
        email=admin.email,
        details=f"Deleted user account: {target_user.email} (Role: {target_user.role.value})",
    )
    db.add(audit)
    await db.delete(target_user)
    await db.commit()
    return None

@router.get("/audit-logs", response_model=List[AuditLogItem])
async def list_audit_logs(
    limit: int = 100,
    event_type: Optional[str] = None,
    admin: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """View security and access audit logs."""
    query = select(SecurityAuditLog).order_by(SecurityAuditLog.created_at.desc()).limit(limit)
    if event_type:
        query = query.where(SecurityAuditLog.event_type == event_type)

    result = await db.execute(query)
    return result.scalars().all()

@router.get("/health", response_model=SystemHealthResponse)
async def system_health_check(db: AsyncSession = Depends(get_db)):
    """Public or internal health probe verifying DB and external service connectivity."""
    db_status = "healthy"
    try:
        await db.execute(select(1))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    el_status = await elevenlabs_service.check_connectivity()
    overall = "healthy" if db_status == "healthy" and el_status.get("status") in ["connected", "scoped_restricted"] else "degraded"

    return SystemHealthResponse(
        status=overall,
        app_version="1.0.0",
        environment=settings.APP_ENV,
        database=db_status,
        redis="not_configured" if not settings.REDIS_URL else "configured",
        elevenlabs_status=el_status.get("status", "unknown"),
        elevenlabs_permission_detail=el_status.get("message"),
        timestamp=datetime.now(timezone.utc),
    )

@router.get("/tech-telemetry")
async def get_admin_tech_telemetry(
    admin: User = Depends(require_admin_or_owner),
):
    """Retrieve technology search volume and performance metrics (strictly zero secrets)."""
    from app.services.tech_intelligence.search.search_engine import tech_search_engine
    from app.services.tech_intelligence.cache import tech_cache
    return {
        "total_searches": tech_search_engine.telemetry.get("total_searches", 0),
        "successful_searches": tech_search_engine.telemetry.get("successful_searches", 0),
        "failed_searches": tech_search_engine.telemetry.get("failed_searches", 0),
        "cache_hits": tech_cache.stats.get("hits", 0),
        "cache_misses": tech_cache.stats.get("misses", 0),
        "active_search_provider": tech_search_engine.active_provider_name,
    }

