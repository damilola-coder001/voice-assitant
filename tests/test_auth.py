import pytest
from httpx import AsyncClient
from app.models.user import User

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "SecurePassword123!", "full_name": "New User"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["role"] == "user"

@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/auth/register",
        json={"email": test_user.email, "password": "AnotherPassword123!"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == test_user.email

@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, test_user: User):
    login_res = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    refresh_token = login_res.json()["refresh_token"]

    refresh_res = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    data = refresh_res.json()
    assert "access_token" in data
    assert "refresh_token" in data

@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, user_token: str, test_user: User):
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert "voice_preference" in data

@pytest.mark.asyncio
async def test_login_account_lockout_after_failed_attempts(client: AsyncClient, test_user: User):
    # 5 failed login attempts
    for _ in range(5):
        res = await client.post(
            "/api/auth/login",
            json={"email": test_user.email, "password": "WrongPassword!"},
        )
        assert res.status_code == 401

    # 6th attempt should be blocked by progressive account lockout
    blocked_res = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    assert blocked_res.status_code == 403
    assert "temporarily locked" in blocked_res.json()["detail"]

@pytest.mark.asyncio
async def test_logout_invalidates_session(client: AsyncClient, test_user: User):
    # 1. Login to obtain access token
    login_res = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    # 2. Token works
    me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200

    # 3. Call logout
    logout_res = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # 4. Old token must now be rejected
    rejected_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert rejected_res.status_code == 401
    assert "Session has been revoked" in rejected_res.json()["detail"]

@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient, test_user: User):
    # 1. Request reset
    req_res = await client.post(
        "/api/auth/password-reset/request",
        json={"email": test_user.email},
    )
    assert req_res.status_code == 200
    reset_token = req_res.json().get("debug_reset_token")
    assert reset_token is not None

    # 2. Confirm reset
    confirm_res = await client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "NewBrandNewPassword2026!"},
    )
    assert confirm_res.status_code == 200

    # 3. Login with new password
    new_login_res = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "NewBrandNewPassword2026!"},
    )
    assert new_login_res.status_code == 200

@pytest.mark.asyncio
async def test_guest_login_instant_access(client: AsyncClient):
    res = await client.post("/api/auth/guest")
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "guest@nore.ai"

