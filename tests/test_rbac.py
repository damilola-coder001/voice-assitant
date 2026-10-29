import pytest
from httpx import AsyncClient
from app.models.user import RoleEnum, User

@pytest.mark.asyncio
async def test_admin_route_forbidden_for_standard_user(client: AsyncClient, user_token: str):
    response = await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

@pytest.mark.asyncio
async def test_admin_route_allowed_for_admin_and_owner(client: AsyncClient, admin_token: str, owner_token: str):
    # Admin can view stats
    res_admin = await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200

    # Owner can view stats
    res_owner = await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_owner.status_code == 200

@pytest.mark.asyncio
async def test_owner_can_manage_admin_and_user(client: AsyncClient, owner_token: str, test_admin: User, test_user: User):
    headers = {"Authorization": f"Bearer {owner_token}"}

    # OWNER -> ADMIN = ALLOW (Owner can change Admin quota or demote)
    res_admin = await client.put(
        f"/api/admin/users/{test_admin.id}/role",
        headers=headers,
        json={"daily_character_quota": 2000000},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["daily_character_quota"] == 2000000

    # OWNER -> USER = ALLOW (Owner can promote User to Admin)
    res_user = await client.put(
        f"/api/admin/users/{test_user.id}/role",
        headers=headers,
        json={"role": "admin"},
    )
    assert res_user.status_code == 200
    assert res_user.json()["role"] == "admin"

@pytest.mark.asyncio
async def test_admin_cannot_modify_or_delete_owner(client: AsyncClient, admin_token: str, test_owner: User):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # ADMIN -> OWNER = ALWAYS DENY (Section 10 & 13)
    res_update = await client.put(
        f"/api/admin/users/{test_owner.id}/role",
        headers=headers,
        json={"daily_character_quota": 1000},
    )
    assert res_update.status_code == 403
    assert "Not authorized" in res_update.json()["detail"]

    # ADMIN -> OWNER delete = ALWAYS DENY
    res_del = await client.delete(f"/api/admin/users/{test_owner.id}", headers=headers)
    assert res_del.status_code == 403

@pytest.mark.asyncio
async def test_admin_cannot_modify_peer_admin(client: AsyncClient, admin_token: str, db_session):
    # Create peer admin
    peer_admin = User(
        email="peer_admin@example.com",
        hashed_password="hash",
        full_name="Peer Admin",
        role=RoleEnum.ADMIN,
        is_active=True,
    )
    db_session.add(peer_admin)
    await db_session.commit()
    await db_session.refresh(peer_admin)

    headers = {"Authorization": f"Bearer {admin_token}"}

    # ADMIN -> ADMIN = DENY (Section 13)
    res = await client.put(
        f"/api/admin/users/{peer_admin.id}/role",
        headers=headers,
        json={"daily_character_quota": 5000},
    )
    assert res.status_code == 403
    assert "Administrators cannot modify other administrator accounts" in res.json()["detail"]

@pytest.mark.asyncio
async def test_cannot_promote_to_owner(client: AsyncClient, owner_token: str, admin_token: str, test_user: User):
    # Even Owner cannot create a second Owner (Ownership is unique and immutable)
    res_owner = await client.put(
        f"/api/admin/users/{test_user.id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "owner"},
    )
    assert res_owner.status_code == 403

    # Admin cannot promote to Owner
    res_admin = await client.put(
        f"/api/admin/users/{test_user.id}/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "owner"},
    )
    assert res_admin.status_code == 403

@pytest.mark.asyncio
async def test_owner_immortality_cannot_be_deleted(client: AsyncClient, owner_token: str, test_owner: User):
    # Owner cannot self-delete (Section 14: Protected Owner Database Rule)
    res = await client.delete(
        f"/api/admin/users/{test_owner.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 400
    assert "cannot be deleted" in res.json()["detail"]
