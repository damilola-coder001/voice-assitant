from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt

from app.config import settings
from app.schemas.auth import TokenPayload

def create_access_token(user_id: int, email: str, role: str, token_version: int = 1, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "token_version": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(user_id: int, email: str, role: str, token_version: int = 1, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT refresh token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "refresh",
        "token_version": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str, expected_type: str = "access") -> Optional[TokenPayload]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True},
        )
        if payload.get("type") != expected_type:
            return None
        return TokenPayload(
            sub=str(payload.get("sub")),
            email=str(payload.get("email")),
            role=str(payload.get("role")),
            type=str(payload.get("type")),
            token_version=int(payload.get("token_version", 1)),
            exp=int(payload.get("exp", 0)),
        )
    except jwt.PyJWTError:
        return None
