import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit import SecurityAuditLog
from app.models.user import RoleEnum, User, UserVoicePreference
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserBriefResponse,
)
from app.schemas.user import UserRead
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password, verify_password
from app.security.rate_limiter import check_rate_limit
from app.security.tokens import create_access_token, create_refresh_token, decode_token
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _is_future(dt: Optional[datetime]) -> bool:
    if not dt:
        return False
    if dt.tzinfo is not None:
        return dt > datetime.now(timezone.utc)
    return dt > datetime.now(timezone.utc).replace(tzinfo=None)

def _is_past(dt: Optional[datetime]) -> bool:
    if not dt:
        return True
    if dt.tzinfo is not None:
        return dt < datetime.now(timezone.utc)
    return dt < datetime.now(timezone.utc).replace(tzinfo=None)

def _remaining_minutes(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    now = datetime.now(timezone.utc) if dt.tzinfo is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    secs = (dt - now).total_seconds()
    return max(1, int(secs // 60))

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account with default voice preferences."""
    await check_rate_limit(request, max_requests=10, window=60)

    # Check if user already exists
    existing = await db.execute(select(User).where(User.email == data.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # Hash password with Argon2
    hashed_pwd = hash_password(data.password)
    user = User(
        email=data.email.lower(),
        hashed_password=hashed_pwd,
        full_name=data.full_name,
        role=RoleEnum.USER,
        status="active",
        daily_character_quota=settings.DEFAULT_DAILY_CHARACTER_QUOTA,
        token_version=1,
    )
    db.add(user)
    await db.flush()

    # Create default voice preferences
    voice_pref = UserVoicePreference(
        user_id=user.id,
        preferred_voice_id=settings.ELEVENLABS_DEFAULT_VOICE_ID,
        preferred_model_id=settings.ELEVENLABS_DEFAULT_MODEL_ID,
        preferred_voice_name="Roger",
    )
    db.add(voice_pref)

    # Audit log
    client_ip = request.client.host if request.client else None
    audit = SecurityAuditLog(
        event_type="register",
        user_id=user.id,
        email=user.email,
        ip_address=client_ip,
        details="New user registered",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(user)

    # Issue tokens
    access_token = create_access_token(user.id, user.email, user.role.value, token_version=user.token_version)
    refresh_token = create_refresh_token(user.id, user.email, user.role.value, token_version=user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserBriefResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        ),
    )

@router.post("/guest", response_model=TokenResponse)
async def guest_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Instant guest session for testing and demo modes.
    Bypasses login forms and issues a ready-to-use testing token.
    """
    guest_email = "guest@nore.ai"
    user = None
    try:
        result = await db.execute(
            select(User).where(User.email == guest_email).options(selectinload(User.voice_preference))
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                email=guest_email,
                hashed_password=hash_password("GuestTestingSecret2026!#"),
                full_name="Guest Tester",
                role=RoleEnum.USER,
                status="active",
                is_active=True,
                daily_character_quota=5000000,
                token_version=1,
            )
            db.add(user)
            await db.flush()

            pref = UserVoicePreference(
                user_id=user.id,
                preferred_voice_id=settings.ELEVENLABS_DEFAULT_VOICE_ID,
                preferred_model_id=settings.ELEVENLABS_DEFAULT_MODEL_ID,
                preferred_voice_name="Roger",
            )
            db.add(pref)
            await db.commit()
            await db.refresh(user)
    except Exception as e:
        logger.debug(f"Guest DB user creation note: {e}")

    user_id = user.id if user else 1
    access_token = create_access_token(
        user_id=user_id,
        email=guest_email,
        role="user",
        token_version=1,
    )
    refresh_token = create_refresh_token(
        user_id=user_id,
        email=guest_email,
        role="user",
        token_version=1,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserBriefResponse(
            id=user_id,
            email=guest_email,
            full_name="Guest Tester",
            role="user",
            is_active=True,
        ),
    )

@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with email and password, progressive lockout, and issue JWT tokens."""
    await check_rate_limit(request, max_requests=15, window=60)

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    now = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    # Account Lockout Check
    if user and _is_future(user.locked_until):
        remaining_mins = _remaining_minutes(user.locked_until)
        logger.warning(f"Blocked login attempt for locked account: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked due to excessive failed attempts. Please try again in {remaining_mins} minutes or reset your password.",
        )

    if not user or not verify_password(data.password, user.hashed_password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                logger.warning(f"Account locked: {user.email} exceeded 5 failed login attempts.")
            db.add(user)

        audit = SecurityAuditLog(
            event_type="login_failed",
            email=data.email.lower(),
            ip_address=client_ip,
            user_agent=user_agent,
            severity="WARNING",
            details="Invalid email or password attempt",
        )
        db.add(audit)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not user.is_active or user.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account has been disabled or suspended.",
        )

    # Clear failed login attempts and update activity on success
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.token_version += 1  # Invalidate any prior active sessions on new login
    db.add(user)

    audit = SecurityAuditLog(
        event_type="login_success",
        user_id=user.id,
        email=user.email,
        ip_address=client_ip,
        user_agent=user_agent,
        details="User logged in successfully",
    )
    db.add(audit)
    await db.commit()

    access_token = create_access_token(user.id, user.email, user.role.value, token_version=user.token_version)
    refresh_token = create_refresh_token(user.id, user.email, user.role.value, token_version=user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserBriefResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        ),
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rotate and refresh access token using valid refresh token."""
    payload = decode_token(data.refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = int(payload.sub)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active or user.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account inactive",
        )

    if payload.token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked. Please log in again.",
        )

    access_token = create_access_token(user.id, user.email, user.role.value, token_version=user.token_version)
    refresh_token = create_refresh_token(user.id, user.email, user.role.value, token_version=user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserBriefResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        ),
    )

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all active sessions and tokens for the authenticated user."""
    current_user.token_version += 1
    db.add(current_user)

    audit = SecurityAuditLog(
        event_type="logout",
        user_id=current_user.id,
        email=current_user.email,
        details="User logged out; active token versions invalidated",
    )
    db.add(audit)
    await db.commit()
    return {"message": "Successfully logged out and invalidated all active sessions."}

@router.post("/password-reset/request")
async def request_password_reset(
    data: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate a secure, rate-limited password recovery flow."""
    await check_rate_limit(request, max_requests=5, window=60)
    now = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    reset_token = None
    if user:
        reset_token = secrets.token_urlsafe(32)
        user.password_reset_token = reset_token
        user.password_reset_expires_at = now + timedelta(minutes=15)
        db.add(user)

        audit = SecurityAuditLog(
            event_type="password_reset_requested",
            user_id=user.id,
            email=user.email,
            details="Password reset token generated",
        )
        db.add(audit)
        await db.commit()

    # Generic return message to prevent user enumeration
    response_payload = {
        "message": "If an account with that email exists, reset instructions have been generated."
    }
    if (settings.DEBUG or settings.APP_ENV in ("development", "test")) and reset_token:
        response_payload["debug_reset_token"] = reset_token

    return response_payload

@router.post("/password-reset/confirm")
async def confirm_password_reset(
    data: PasswordResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Validate reset token, update password, and revoke prior sessions."""
    await check_rate_limit(request, max_requests=5, window=60)
    now = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.password_reset_token == data.token))
    user = result.scalar_one_or_none()

    if not user or not user.password_reset_expires_at or _is_past(user.password_reset_expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    user.hashed_password = hash_password(data.new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.token_version += 1  # Invalidate all active sessions
    db.add(user)

    audit = SecurityAuditLog(
        event_type="password_reset_success",
        user_id=user.id,
        email=user.email,
        details="Password reset completed successfully; sessions revoked",
    )
    db.add(audit)
    await db.commit()

    return {"message": "Password successfully reset. Please log in with your new credentials."}

@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full profile and preferences of the authenticated user."""
    query = select(User).where(User.id == current_user.id).options(selectinload(User.voice_preference))
    result = await db.execute(query)
    user = result.scalar_one()
    return user
