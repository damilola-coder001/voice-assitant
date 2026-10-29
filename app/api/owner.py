import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db, engine
from app.models.audit import SecurityAuditLog
from app.models.user import RoleEnum, User, UserVoicePreference
from app.schemas.user import AdminCreateRequest, UserRead, UserRoleUpdate
from app.security.dependencies import require_owner
from app.security.passwords import hash_password
from app.services.elevenlabs import elevenlabs_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/owner", tags=["Owner Operations"])

PREDICTABLE_PASSWORDS = {
    "admin", "password", "owner", "123456", "admin123", "owner123",
    "password123", "changeme", "secret", "root", "default"
}

@router.post("/admins", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_admin(
    data: AdminCreateRequest,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Owner creates a new Admin account.
    Validates secure password, assigns ADMIN role, and records audit log.
    """
    pwd_clean = data.password.strip()
    if len(pwd_clean) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin password must be at least 12 characters long.",
        )
    if pwd_clean.lower() in PREDICTABLE_PASSWORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Predictable passwords are strictly prohibited for administrative accounts.",
        )

    # Check email duplicate
    email_clean = data.email.strip().lower()
    existing_res = await db.execute(select(User).where(User.email == email_clean))
    if existing_res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{email_clean}' is already registered.",
        )

    # Create Admin user
    new_admin = User(
        email=email_clean,
        hashed_password=hash_password(pwd_clean),
        full_name=data.full_name or "Platform Admin",
        role=RoleEnum.ADMIN,
        status="active",
        is_active=True,
        daily_character_quota=1000000,
        token_version=1,
    )
    db.add(new_admin)
    await db.flush()

    # Create default voice preferences
    pref = UserVoicePreference(
        user_id=new_admin.id,
        preferred_voice_id=settings.ELEVENLABS_DEFAULT_VOICE_ID,
        preferred_model_id=settings.ELEVENLABS_DEFAULT_MODEL_ID,
        preferred_voice_name="Roger",
    )
    db.add(pref)

    # Audit event
    audit = SecurityAuditLog(
        event_type="admin_created",
        user_id=owner.id,
        email=owner.email,
        details=f"Owner {owner.email} created Admin account {new_admin.email} (ID: {new_admin.id})",
    )
    db.add(audit)
    await db.commit()

    # Re-fetch with preferences
    result = await db.execute(
        select(User).where(User.id == new_admin.id).options(selectinload(User.voice_preference))
    )
    return result.scalar_one()

@router.delete("/admins/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_id: int,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Owner removes/deletes an Admin account.
    Enforces Protected Principal: Owner cannot be deleted.
    Revokes active sessions before deletion.
    """
    res = await db.execute(select(User).where(User.id == admin_id))
    target = res.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")

    if target.role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Protected Principal Rule: The Owner account cannot be deleted.",
        )

    if target.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target account is not an Admin (Role: {target.role.value}). Use user deletion endpoints instead.",
        )

    # Invalidate sessions before deletion
    target.token_version += 1

    # Record audit log
    audit = SecurityAuditLog(
        event_type="admin_deleted",
        user_id=owner.id,
        email=owner.email,
        details=f"Owner {owner.email} deleted Admin account {target.email} (ID: {target.id})",
    )
    db.add(audit)
    await db.delete(target)
    await db.commit()
    return None

@router.patch("/admins/{admin_id}/status", response_model=UserRead)
async def toggle_admin_status(
    admin_id: int,
    data: UserRoleUpdate,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Owner suspends or reactivates an Admin account.
    Revokes sessions immediately if suspended.
    """
    res = await db.execute(select(User).where(User.id == admin_id).options(selectinload(User.voice_preference)))
    target = res.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")

    if target.role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Protected Principal Rule: The Owner account cannot be suspended or modified.",
        )

    if target.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target account is not an Admin (Role: {target.role.value}).",
        )

    action_name = "modified"
    if data.is_active is not None:
        target.is_active = data.is_active
        if not data.is_active:
            target.status = "suspended"
            target.token_version += 1  # Revoke all active sessions
            action_name = "admin_suspended"
        else:
            target.status = "active"
            action_name = "admin_activated"

    if data.daily_character_quota is not None:
        target.daily_character_quota = data.daily_character_quota

    audit = SecurityAuditLog(
        event_type=action_name,
        user_id=owner.id,
        email=owner.email,
        details=f"Owner {owner.email} updated Admin {target.email} status (Active: {target.is_active}, Status: {target.status})",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(target)
    return target

@router.get("/system-config")
async def get_system_config(
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Owner view of system and provider configuration.
    Masks credentials completely (never sends raw API keys or passwords).
    """
    el_status = await elevenlabs_service.check_connectivity()

    return {
        "platform_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "is_production": settings.is_production,
        "elevenlabs": {
            "status": "Configured" if el_status.get("status") in ["connected", "scoped_restricted"] else "Unreachable",
            "masked_api_key": settings.masked_elevenlabs_key(),
            "default_voice_id": settings.ELEVENLABS_DEFAULT_VOICE_ID,
            "default_model_id": settings.ELEVENLABS_DEFAULT_MODEL_ID,
            "subscription_tier": el_status.get("tier", "Server-Side Secret"),
            "permission_details": el_status.get("message"),
        },
        "database": {
            "status": "Connected",
            "dialect": engine.dialect.name,
        },
        "redis": {
            "status": "Configured" if settings.REDIS_URL else "Not Configured (Using in-memory fallback)",
        },
        "cors_origins": settings.allowed_origins_list,
    }

from pydantic import BaseModel, Field

class TechConfigUpdate(BaseModel):
    provider: Optional[str] = None
    max_results: Optional[int] = Field(None, ge=1, le=20)
    cache_ttl_seconds: Optional[int] = Field(None, ge=60, le=86400)

@router.get("/tech-config")
async def get_tech_config(
    owner: User = Depends(require_owner),
):
    """Retrieve technology intelligence and search provider configuration (Owner only)."""
    from app.services.tech_intelligence.search.search_engine import tech_search_engine
    return {
        "provider": settings.TECH_SEARCH_PROVIDER,
        "max_results": settings.TECH_SEARCH_MAX_RESULTS,
        "cache_ttl_seconds": settings.TECH_CACHE_TTL_SECONDS,
        "brave_configured": bool(settings.BRAVE_SEARCH_API_KEY),
        "tavily_configured": bool(settings.TAVILY_API_KEY),
        "masked_brave_key": settings.masked_search_key(settings.BRAVE_SEARCH_API_KEY),
        "masked_tavily_key": settings.masked_search_key(settings.TAVILY_API_KEY),
        "active_search_provider": tech_search_engine.active_provider_name,
        "supported_providers": list(tech_search_engine.providers.keys()),
    }

@router.put("/tech-config")
async def update_tech_config(
    data: TechConfigUpdate,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Update search provider, result count, and cache policies (Owner only)."""
    from app.services.tech_intelligence.search.search_engine import tech_search_engine

    if data.provider is not None:
        clean_p = data.provider.strip().lower()
        if clean_p not in ["auto", "duckduckgo", "tech_feeds", "brave", "tavily"]:
            raise HTTPException(status_code=400, detail=f"Unsupported search provider '{clean_p}'")
        settings.TECH_SEARCH_PROVIDER = clean_p
        tech_search_engine.active_provider_name = clean_p

    if data.max_results is not None:
        settings.TECH_SEARCH_MAX_RESULTS = data.max_results

    if data.cache_ttl_seconds is not None:
        settings.TECH_CACHE_TTL_SECONDS = data.cache_ttl_seconds

    audit = SecurityAuditLog(
        event_type="tech_config_updated",
        user_id=owner.id,
        email=owner.email,
        details=f"Owner updated tech search config: provider={settings.TECH_SEARCH_PROVIDER}, max_results={settings.TECH_SEARCH_MAX_RESULTS}",
    )
    db.add(audit)
    await db.commit()

    return {
        "message": "Technology intelligence configuration updated successfully.",
        "provider": settings.TECH_SEARCH_PROVIDER,
        "max_results": settings.TECH_SEARCH_MAX_RESULTS,
        "cache_ttl_seconds": settings.TECH_CACHE_TTL_SECONDS,
    }

@router.get("/tech-telemetry")
async def get_tech_telemetry(
    owner: User = Depends(require_owner),
):
    """Retrieve search performance, provider success rates, and cache stats (Owner only)."""
    from app.services.tech_intelligence.search.search_engine import tech_search_engine
    from app.services.tech_intelligence.cache import tech_cache
    return {
        "search_telemetry": tech_search_engine.telemetry,
        "cache_stats": tech_cache.stats,
    }

