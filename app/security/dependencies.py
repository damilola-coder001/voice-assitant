from typing import List, Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.user import RoleEnum, User, UserVoicePreference
from app.security.tokens import decode_token

# Bearer authentication scheme (auto_error=False allows WebSocket query param fallback)
security = HTTPBearer(auto_error=False)

def get_fallback_guest_user() -> User:
    """Return a resilient in-memory guest user for testing without database or login barriers."""
    pref = UserVoicePreference(
        user_id=1,
        preferred_voice_id=settings.ELEVENLABS_DEFAULT_VOICE_ID,
        preferred_model_id=settings.ELEVENLABS_DEFAULT_MODEL_ID,
        preferred_voice_name="Roger",
        tech_interests="ai_ml,software_dev,cybersecurity",
        tech_explanation_level="intermediate",
        tech_briefing_topics="all",
        tech_summary_style="balanced",
    )
    return User(
        id=1,
        email="guest@nore.ai",
        hashed_password="",
        full_name="Guest Tester",
        role=RoleEnum.USER,
        status="active",
        is_active=True,
        daily_character_quota=5000000,
        token_version=1,
        voice_preference=pref,
    )

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer JWT token and return active User instance."""
    if not credentials:
        if not settings.ENABLE_AUTH:
            return get_fallback_guest_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")
    if not payload:
        if not settings.ENABLE_AUTH:
            return get_fallback_guest_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload.sub)
    except (ValueError, TypeError):
        if not settings.ENABLE_AUTH:
            return get_fallback_guest_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = None
    try:
        query = select(User).where(User.id == user_id).options(selectinload(User.voice_preference))
        result = await db.execute(query)
        user = result.scalar_one_or_none()
    except Exception:
        user = None

    if not user:
        if not settings.ENABLE_AUTH:
            return get_fallback_guest_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check session revocation / token invalidation
    if payload.token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active or user.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is suspended or deactivated",
        )

    return user

def require_role(allowed_roles: List[RoleEnum]):
    """RBAC Route Guard checking if current user has one of allowed roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not settings.ENABLE_RBAC:
            # Dormant RBAC mode: Role-based restrictions bypassed for all authenticated users
            return current_user

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker

# Predefined role dependencies
require_owner = require_role([RoleEnum.OWNER])
require_admin_or_owner = require_role([RoleEnum.OWNER, RoleEnum.ADMIN])
require_admin = require_role([RoleEnum.OWNER, RoleEnum.ADMIN])  # Owner has administrative supervision
require_authenticated = get_current_user
