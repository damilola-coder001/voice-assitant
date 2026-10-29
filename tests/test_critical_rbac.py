import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.user import RoleEnum, User
from app.models.conversation import ConversationSession

@pytest.mark.asyncio
async def test_1_owner_creates_admin_success(client: AsyncClient, owner_token: str):
    """Test 1: Owner creates Admin. Expected: SUCCESS"""
    res = await client.post(
        "/api/owner/admins",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "critical_admin_1@nore.ai",
            "password": "SecureAdminPassword2026!#",
            "full_name": "Critical Test Admin",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "admin"
    assert data["email"] == "critical_admin_1@nore.ai"

@pytest.mark.asyncio
async def test_2_admin_manages_user_success(client: AsyncClient, admin_token: str, test_user: User):
    """Test 2: Admin manages User. Expected: SUCCESS"""
    res = await client.patch(
        f"/api/users/{test_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"full_name": "Updated By Admin", "daily_character_quota": 80000},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "Updated By Admin"
    assert data["daily_character_quota"] == 80000

@pytest.mark.asyncio
async def test_3_admin_attempts_to_delete_owner_denied(client: AsyncClient, admin_token: str, test_owner: User):
    """Test 3: Admin attempts to delete Owner. Expected: DENIED (403)"""
    # 1. Attempt via standard admin user endpoint
    res1 = await client.delete(
        f"/api/admin/users/{test_owner.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res1.status_code == 403

    # 2. Attempt via Owner admin endpoint
    res2 = await client.delete(
        f"/api/owner/admins/{test_owner.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res2.status_code == 403

@pytest.mark.asyncio
async def test_4_admin_attempts_to_suspend_owner_denied(client: AsyncClient, admin_token: str, test_owner: User):
    """Test 4: Admin attempts to suspend Owner. Expected: DENIED (403)"""
    res = await client.patch(
        f"/api/users/{test_owner.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_active": False},
    )
    assert res.status_code == 403
    assert "Not authorized" in res.json()["detail"]

@pytest.mark.asyncio
async def test_5_admin_attempts_to_demote_owner_denied(client: AsyncClient, admin_token: str, test_owner: User):
    """Test 5: Admin attempts to demote Owner. Expected: DENIED (403)"""
    res = await client.put(
        f"/api/admin/users/{test_owner.id}/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "user"},
    )
    assert res.status_code == 403
    assert "Not authorized" in res.json()["detail"]

@pytest.mark.asyncio
async def test_6_admin_attempts_to_modify_owner_password_denied(client: AsyncClient, admin_token: str, test_owner: User):
    """Test 6: Admin attempts to modify Owner password. Expected: DENIED (403)"""
    res = await client.patch(
        f"/api/users/{test_owner.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"full_name": "Attacked Owner", "password": "NewHackedPassword123!"},
    )
    assert res.status_code == 403
    assert "Not authorized" in res.json()["detail"]

@pytest.mark.asyncio
async def test_7_admin_attempts_to_create_owner_denied(client: AsyncClient, admin_token: str, test_user: User):
    """Test 7: Admin attempts to create Owner. Expected: DENIED (403)"""
    res = await client.put(
        f"/api/admin/users/{test_user.id}/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "owner"},
    )
    assert res.status_code == 403
    assert "Owner" in res.json()["detail"] or "Not authorized" in res.json()["detail"]

@pytest.mark.asyncio
async def test_8_admin_attempts_to_promote_themselves_to_owner_denied(client: AsyncClient, admin_token: str, test_admin: User):
    """Test 8: Admin attempts to promote themselves to Owner. Expected: DENIED (403)"""
    res = await client.put(
        f"/api/admin/users/{test_admin.id}/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "owner"},
    )
    assert res.status_code == 403
    assert "administrator" in res.json()["detail"].lower() or "not authorized" in res.json()["detail"].lower()

@pytest.mark.asyncio
async def test_9_user_attempts_to_access_admin_dashboard_denied(client: AsyncClient, user_token: str):
    """Test 9: User attempts to access admin dashboard. Expected: DENIED (403)"""
    res = await client.get(
        "/api/admin/stats",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

@pytest.mark.asyncio
async def test_10_user_attempts_to_modify_another_user_denied(client: AsyncClient, user_token: str, test_admin: User):
    """Test 10: User attempts to modify another User. Expected: DENIED (403)"""
    res = await client.patch(
        f"/api/users/{test_admin.id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"full_name": "Tampered By User"},
    )
    assert res.status_code == 403
    assert "access denied" in res.json()["detail"].lower() or "not authorized" in res.json()["detail"].lower()

@pytest.mark.asyncio
async def test_11_user_accesses_own_profile_success(client: AsyncClient, user_token: str):
    """Test 11: User accesses own profile. Expected: SUCCESS"""
    res = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "user"
    assert "email" in data
    assert "voice_preference" in data

@pytest.mark.asyncio
async def test_12_user_attempts_to_access_another_users_private_conversation_denied(
    client: AsyncClient, user_token: str, owner_token: str
):
    """Test 12: User attempts to access another user's private conversation. Expected: DENIED (404/403)"""
    # 1. Owner creates private session
    create_res = await client.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"title": "Confidential Owner Strategy", "persona_id": "executive"},
    )
    session_id = create_res.json()["id"]

    # 2. Standard user attempts to read it
    res = await client.get(
        f"/api/conversations/{session_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
