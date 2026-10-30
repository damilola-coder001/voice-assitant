from typing import List, Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.user import RoleEnum, User
from app.security.tokens import decode_token

# Bearer authentication scheme (auto_error=False allows WebSocket query param fallback)
security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer JWT token and return active User instance."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload.sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    query = select(User).where(User.id == user_id).options(selectinload(User.voice_preference))
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
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
