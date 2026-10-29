import os
from pathlib import Path
import pytest
from httpx import AsyncClient
from app.config import settings
from scripts.scan_secrets import scan_directory

def test_secret_scanner_clean():
    """Verify that scan_directory finds zero secrets in project workspace."""
    exit_code = scan_directory(Path.cwd())
    assert exit_code == 0, "Secret scanner detected potential secrets in repository files!"

def test_no_hardcoded_keys_in_frontend():
    """Verify that frontend static files contain zero API keys or secrets."""
    static_dir = Path.cwd() / "app" / "static"
    for file in static_dir.rglob("*"):
        if file.is_file() and file.suffix in [".html", ".js", ".css"]:
            content = file.read_text(encoding="utf-8")
            assert "sk_" not in content, f"Possible secret key leaked in {file}"
            assert "ELEVENLABS_API_KEY" not in content, f"Env var reference found in frontend {file}"

@pytest.mark.asyncio
async def test_api_responses_never_leak_elevenlabs_key(client: AsyncClient, admin_token: str, user_token: str):
    """Verify that administrative and user endpoints never leak raw API keys."""
    endpoints = [
        ("/api/admin/stats", admin_token),
        ("/api/admin/health", admin_token),
        ("/api/voices", user_token),
        ("/api/auth/me", user_token),
    ]

    for endpoint, token in endpoints:
        res = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        text = res.text
        if settings.ELEVENLABS_API_KEY:
            assert settings.ELEVENLABS_API_KEY not in text, f"ELEVENLABS_API_KEY leaked in response from {endpoint}"
