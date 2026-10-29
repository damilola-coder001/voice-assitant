"""Tests for tech intelligence RBAC enforcement and zero secret leakage."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_access_tech_telemetry(client: AsyncClient, admin_token: str):
    """Admins should be able to view tech telemetry metrics."""
    resp = await client.get(
        "/api/admin/tech-telemetry",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_searches" in data
    assert "cache_hits" in data
    assert "active_search_provider" in data


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_tech_telemetry(client: AsyncClient, user_token: str):
    """Regular users must be denied admin tech telemetry."""
    resp = await client.get(
        "/api/admin/tech-telemetry",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code in [401, 403]


@pytest.mark.asyncio
async def test_owner_can_access_owner_tech_telemetry(client: AsyncClient, owner_token: str):
    """Owner should access the owner-level telemetry endpoint."""
    resp = await client.get(
        "/api/owner/tech-telemetry",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "search_telemetry" in data
    assert "cache_stats" in data


@pytest.mark.asyncio
async def test_admin_cannot_access_owner_tech_telemetry(client: AsyncClient, admin_token: str):
    """Admins must be denied access to owner-only tech telemetry."""
    resp = await client.get(
        "/api/owner/tech-telemetry",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code in [401, 403]


@pytest.mark.asyncio
async def test_user_cannot_access_owner_tech_config(client: AsyncClient, user_token: str):
    """Regular users must be denied owner tech configuration."""
    resp = await client.get(
        "/api/owner/tech-config",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code in [401, 403, 405]


@pytest.mark.asyncio
async def test_admin_tech_telemetry_no_secrets(client: AsyncClient, admin_token: str):
    """Admin tech telemetry must NEVER contain API keys or secrets."""
    resp = await client.get(
        "/api/admin/tech-telemetry",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if resp.status_code == 200:
        body_text = resp.text.lower()
        # Must not contain any actual API key values
        assert "sk-" not in body_text  # Generic API key prefix
        assert "tvly-" not in body_text  # Tavily key prefix
        assert "bsk-" not in body_text  # Brave key prefix
        # Must not contain key field names that could leak secrets
        assert "api_key" not in body_text or "masked" in body_text or "status" in body_text


@pytest.mark.asyncio
async def test_tech_preferences_saved_correctly(client: AsyncClient, user_token: str):
    """User can save tech preferences via the voice-preferences endpoint."""
    resp = await client.put(
        "/api/users/me/voice-preferences",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "tech_interests": "ai_ml,cybersecurity",
            "tech_explanation_level": "advanced",
            "tech_summary_style": "concise",
        },
    )
    assert resp.status_code == 200

    # Verify preferences are persisted
    get_resp = await client.get(
        "/api/users/me/voice-preferences",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    if get_resp.status_code == 200:
        data = get_resp.json()
        assert data.get("tech_interests") == "ai_ml,cybersecurity"
        assert data.get("tech_explanation_level") == "advanced"
