import logging
from typing import Optional
from fastapi import HTTPException, status

from app.models.user import RoleEnum, User

logger = logging.getLogger(__name__)

class AuthorizationError(HTTPException):
    """Generic authorization error preventing privilege disclosure."""
    def __init__(self, detail: str = "Not authorized to perform this operation on target account."):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class AuthorizationPolicy:
    """
    Enforces RBAC Architecture, Authorization Matrix, and Protected Principal Rules
    as specified in Sections 8, 9, 10, 11, 12, 13, 14 of the Security PDR.
    """

    @classmethod
    def can_manage_target(cls, actor: User, target: User, operation: str = "modify") -> bool:
        """
        Validate whether `actor` is authorized to perform `operation` on `target`.
        Operations include: "view", "modify", "change_role", "suspend", "reactivate", "delete", "reset_password".
        """
        # --- RULE 1: TARGET IS OWNER (Protected Principal Safeguard - Section 10 & 14) ---
        if target.role == RoleEnum.OWNER:
            if actor.role != RoleEnum.OWNER or actor.id != target.id:
                # ADMIN -> OWNER = ALWAYS DENY
                # USER -> OWNER = DENY
                logger.warning(
                    f"SECURITY ALERT: Unauthorized attempt by actor {actor.email} (Role: {actor.role.value}) "
                    f"to execute '{operation}' on Owner account {target.email}."
                )
                raise AuthorizationError("Not authorized to perform this operation on target account.")

            # OWNER -> OWNER (Self Management):
            # The Owner cannot delete, suspend, deactivate, or demote themselves (Owner Immortality)
            if operation in ("delete", "suspend", "deactivate", "demote", "change_role"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The Owner account cannot be deleted, suspended, or demoted.",
                )
            return True

        # --- RULE 2: ACTOR IS OWNER (Highest Privilege - Section 9) ---
        if actor.role == RoleEnum.OWNER:
            # OWNER -> ADMIN = ALLOW
            # OWNER -> USER = ALLOW
            return True

        # --- RULE 3: ACTOR IS ADMIN (Section 11 & 13) ---
        if actor.role == RoleEnum.ADMIN:
            # ADMIN -> ADMIN = DENY by default (Section 13: ADMIN -> ADMIN = DENY by default)
            if target.role == RoleEnum.ADMIN:
                if actor.id == target.id and operation in ("view", "modify_profile"):
                    return True
                logger.warning(
                    f"Admin {actor.email} attempted '{operation}' on peer Admin {target.email}. Denied by policy."
                )
                raise AuthorizationError("Administrators cannot modify other administrator accounts.")

            # ADMIN -> USER = ALLOW
            if target.role == RoleEnum.USER:
                # Admins can manage users, suspend, reactivate, or delete normal users
                return True

        # --- RULE 4: ACTOR IS USER (Standard User - Section 12 & 13) ---
        if actor.role == RoleEnum.USER:
            # USER -> SELF = ALLOW (Only safe self operations)
            if actor.id == target.id:
                if operation in ("change_role", "change_quota", "suspend", "delete"):
                    raise AuthorizationError("Standard users cannot modify administrative attributes.")
                return True

            # USER -> OTHER USER / ADMIN / OWNER = DENY
            raise AuthorizationError("Access denied.")

        raise AuthorizationError("Access denied.")

    @classmethod
    def can_assign_role(cls, actor: User, target: User, target_new_role: RoleEnum) -> bool:
        """
        Validate whether `actor` can transition `target` to `target_new_role`.
        """
        # Rule: Nobody can create or promote to OWNER via API (Section 10: Admins cannot create another Owner or promote themselves)
        if target_new_role == RoleEnum.OWNER:
            logger.critical(
                f"SECURITY VIOLATION: Actor {actor.email} attempted to promote target {target.email} to OWNER. Denied."
            )
            raise AuthorizationError("Cannot assign the Owner role. Ownership is unique and immutable.")

        # Rule: Target is Owner - cannot change Owner role under any circumstances
        if target.role == RoleEnum.OWNER:
            raise AuthorizationError("The Owner role cannot be changed or demoted.")

        # Rule: Only Owner can create or demote Admins (Section 9 & 11)
        if target_new_role == RoleEnum.ADMIN or target.role == RoleEnum.ADMIN:
            if actor.role != RoleEnum.OWNER:
                logger.warning(
                    f"Non-owner {actor.email} attempted to modify Admin status for {target.email}. Denied."
                )
                raise AuthorizationError("Only the platform Owner can grant or revoke Administrator privileges.")

        # Admins can only change status/quota of standard users
        return cls.can_manage_target(actor, target, operation="change_role")
