from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User, UserVoicePreference
from app.schemas.auth import PasswordChangeRequest
from app.schemas.user import (
    UserRead,
    UserUpdate,
    UserVoicePreferenceSchema,
    UserVoicePreferenceUpdate,
)
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["Users"])

@router.put("/me", response_model=UserRead)
async def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update profile attributes such as full name."""
    if data.full_name is not None:
        current_user.full_name = data.full_name
    await db.commit()
    await db.refresh(current_user)

    query = select(User).where(User.id == current_user.id).options(selectinload(User.voice_preference))
    result = await db.execute(query)
    return result.scalar_one()

@router.get("/me/voice-preferences", response_model=UserVoicePreferenceSchema)
async def get_voice_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve current voice synthesis preferences."""
    result = await db.execute(select(UserVoicePreference).where(UserVoicePreference.user_id == current_user.id))
    pref = result.scalar_one_or_none()
    if not pref:
        # Create default preference if absent
        pref = UserVoicePreference(user_id=current_user.id)
        db.add(pref)
        await db.commit()
        await db.refresh(pref)
    return pref

@router.put("/me/voice-preferences", response_model=UserVoicePreferenceSchema)
async def update_voice_preferences(
    data: UserVoicePreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update preferred voice ID, stability, similarity, style, and assistant persona."""
    result = await db.execute(select(UserVoicePreference).where(UserVoicePreference.user_id == current_user.id))
    pref = result.scalar_one_or_none()
    if not pref:
        pref = UserVoicePreference(user_id=current_user.id)
        db.add(pref)

    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(pref, key, value)

    await db.commit()
    await db.refresh(pref)
    return pref

@router.post("/me/change-password")
async def change_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change account password with verification of old password."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed.",
        )

    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password changed successfully."}

from app.models.audit import SecurityAuditLog
from app.models.user import RoleEnum
from app.schemas.user import UserPatchRequest
from app.security.authorization import AuthorizationPolicy

@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: int,
    data: UserPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Patch user attributes (full_name, quota, is_active, status, role).
    Strictly enforced by AuthorizationPolicy:
    - Admins CANNOT modify Owner (Protected Principal Rule -> 403 Forbidden).
    - Admins CANNOT modify peer Admins (403 Forbidden).
    - Standard Users can only update themselves.
    - Only Owner can change user roles.
    """
    res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.voice_preference)))
    target = res.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # 1. Enforce authorization policy
    AuthorizationPolicy.can_manage_target(current_user, target, operation="modify")

    # 2. Check role update authorization
    if data.role is not None:
        try:
            new_role = RoleEnum(data.role.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{data.role}'. Permitted roles: {[r.value for r in RoleEnum if r != RoleEnum.OWNER]}",
            )
        AuthorizationPolicy.can_assign_role(current_user, target, new_role)
        target.role = new_role

    # 3. Apply field updates
    if data.full_name is not None:
        target.full_name = data.full_name

    if data.daily_character_quota is not None:
        # Standard users cannot change their own quota
        if current_user.role == RoleEnum.USER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot alter character quota.")
        target.daily_character_quota = data.daily_character_quota

    if data.is_active is not None:
        if target.role == RoleEnum.OWNER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner account active status cannot be altered.")
        target.is_active = data.is_active
        if not data.is_active and target.status == "active":
            target.status = "suspended"
            target.token_version += 1
        elif data.is_active and target.status == "suspended":
            target.status = "active"

    if data.status is not None:
        if target.role == RoleEnum.OWNER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner account status cannot be altered.")
        target.status = data.status
        if data.status == "suspended":
            target.is_active = False
            target.token_version += 1

    audit = SecurityAuditLog(
        event_type="user_patched",
        user_id=current_user.id,
        email=current_user.email,
        details=f"User {current_user.email} ({current_user.role.value}) patched target {target.email} (ID: {target.id})",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(target)
    return target
