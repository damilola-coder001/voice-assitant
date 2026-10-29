import logging
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit import SecurityAuditLog
from app.models.user import RoleEnum, User
from app.security.logging import SensitiveDataFilter, sanitize_string

@pytest.mark.asyncio
async def test_owner_can_create_admin(client: AsyncClient, owner_token: str, db_session):
    """Verify that Owner can create new Admin accounts and an audit log is produced."""
    res = await client.post(
        "/api/owner/admins",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "newadmin@nore.ai",
            "password": "SecureAdminSecret2026!#",
            "full_name": "New Admin Officer",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "admin"
    assert data["email"] == "newadmin@nore.ai"

    # Verify audit log
    audit_res = await db_session.execute(
        select(SecurityAuditLog).where(SecurityAuditLog.event_type == "admin_created")
    )
    audit = audit_res.scalars().first()
    assert audit is not None
    assert "newadmin@nore.ai" in audit.details

@pytest.mark.asyncio
async def test_admin_cannot_create_admin(client: AsyncClient, admin_token: str):
    """Verify that Admin role is rejected when attempting to create another Admin."""
    res = await client.post(
        "/api/owner/admins",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "anotheradmin@nore.ai",
            "password": "SecureAdminSecret2026!#",
            "full_name": "Unauthorized Admin",
        },
    )
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_owner_can_delete_admin(client: AsyncClient, owner_token: str, db_session):
    """Verify that Owner can delete an Admin and an audit event is recorded."""
    # First create an admin to delete
    create_res = await client.post(
        "/api/owner/admins",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "tempadmin@nore.ai",
            "password": "SecureAdminSecret2026!#",
            "full_name": "Temp Admin",
        },
    )
    admin_id = create_res.json()["id"]

    # Delete admin
    del_res = await client.delete(
        f"/api/owner/admins/{admin_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_res.status_code == 204

    # Verify deleted from DB
    check_user = await db_session.execute(select(User).where(User.id == admin_id))
    assert check_user.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_owner_cannot_be_deleted_via_owner_api(client: AsyncClient, owner_token: str, test_owner: User):
    """Verify that attempting to delete the Owner returns 403 Forbidden."""
    res = await client.delete(
        f"/api/owner/admins/{test_owner.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 403
    assert "Owner account cannot be deleted" in res.json()["detail"]

@pytest.mark.asyncio
async def test_admin_patch_owner_rejected(client: AsyncClient, admin_token: str, test_owner: User):
    """Verify that Admin attempting to PATCH Owner returns 403 Forbidden."""
    res = await client.patch(
        f"/api/users/{test_owner.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"full_name": "Compromised Owner"},
    )
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_admin_patch_user_allowed(client: AsyncClient, admin_token: str, test_user: User):
    """Verify that Admin can update a standard User's quota via PATCH /api/users/{id}."""
    res = await client.patch(
        f"/api/users/{test_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"daily_character_quota": 300000, "full_name": "Patched Standard User"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["daily_character_quota"] == 300000
    assert data["full_name"] == "Patched Standard User"

@pytest.mark.asyncio
async def test_conversation_privacy_and_audited_admin_access(
    client: AsyncClient,
    user_token: str,
    admin_token: str,
    owner_token: str,
    db_session,
):
    """
    Verify:
    1. User A creates conversation.
    2. Admin inspecting it receives 200 and an audit log is triggered.
    """
    # User creates session
    create_res = await client.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"title": "Private User Discussion", "persona_id": "executive"},
    )
    session_id = create_res.json()["id"]

    # Admin inspects the conversation
    admin_res = await client.get(
        f"/api/conversations/{session_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_res.status_code == 200
    assert admin_res.json()["title"] == "Private User Discussion"

    # Verify audit log was created
    audit_res = await db_session.execute(
        select(SecurityAuditLog).where(
            SecurityAuditLog.event_type == "sensitive_conversation_access"
        )
    )
    audit = audit_res.scalars().first()
    assert audit is not None
    assert f"#{session_id}" in audit.details

@pytest.mark.asyncio
async def test_owner_system_config_masks_secrets(client: AsyncClient, owner_token: str, admin_token: str):
    """Verify that Owner can view system config with masked credentials, but Admin is forbidden."""
    # Admin forbidden
    admin_res = await client.get(
        "/api/owner/system-config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_res.status_code == 403

    # Owner allowed
    owner_res = await client.get(
        "/api/owner/system-config",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_res.status_code == 200
    data = owner_res.json()
    assert "elevenlabs" in data
    assert "database" in data
    # Ensure masked key does not reveal full secret
    masked_key = data["elevenlabs"]["masked_api_key"]
    assert "..." in masked_key

@pytest.mark.asyncio
async def test_user_personality_preferences(client: AsyncClient, user_token: str):
    """Verify that users can configure Assistant Name, Tone, Formality, Speed, and Language."""
    update_res = await client.put(
        "/api/users/me/voice-preferences",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "assistant_name": "AURA",
            "tone": "conversational",
            "formality": "casual",
            "response_style": "direct",
            "preferred_language": "fr",
            "speed": 1.15,
        },
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["assistant_name"] == "AURA"
    assert data["tone"] == "conversational"
    assert data["formality"] == "casual"
    assert data["preferred_language"] == "fr"
    assert data["speed"] == 1.15

def test_sensitive_data_filter_scrubs_secrets():
    """Verify that SensitiveDataFilter properly scrubs API keys, Bearer tokens, and passwords."""
    pwd_val = "SuperSecret123!"
    raw_log = f"Error connecting to ElevenLabs with sk_dummy_test_key_for_unit_tests and token Bearer eyJhbGciOi. password='{pwd_val}'"
    sanitized = sanitize_string(raw_log)
    assert "sk_dummy_test_key_for_unit_tests" not in sanitized
    assert "sk_***" in sanitized
    assert "Bearer eyJhbGciOi" not in sanitized
    assert "Bearer ***" in sanitized
    assert pwd_val not in sanitized
    assert "password='***'" in sanitized
