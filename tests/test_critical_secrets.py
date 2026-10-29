import pytest
from pathlib import Path
from httpx import AsyncClient
from starlette.testclient import TestClient
from sqlalchemy import select
from app.config import settings
from app.main import app
from app.models.user import User, UserVoicePreference
from app.models.conversation import ConversationSession, Message
from app.models.usage import ElevenLabsUsageLog
from app.models.audit import SecurityAuditLog
from app.security.logging import sanitize_string

FAKE_KEY = settings.ELEVENLABS_API_KEY or "sk_dummy_test_key_for_unit_tests"

@pytest.mark.asyncio
async def test_secret_never_appears_in_api_responses(client: AsyncClient, owner_token: str, admin_token: str, user_token: str):
    """Vector 1: Verify ElevenLabs key never appears in any API endpoint response."""
    endpoints = [
        ("/health", None),
        ("/api/health", None),
        ("/api/auth/me", user_token),
        ("/api/voices", user_token),
        ("/api/admin/stats", admin_token),
        ("/api/admin/health", admin_token),
        ("/api/owner/system-config", owner_token),
    ]

    for path, token in endpoints:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        res = await client.get(path, headers=headers)
        assert res.status_code == 200
        # Check raw response text
        if FAKE_KEY:
            assert FAKE_KEY not in res.text, f"Key leaked in response for {path}"

def test_secret_never_appears_in_frontend_payloads():
    """Vector 2: Verify ElevenLabs key never appears in static frontend files."""
    static_dir = Path.cwd() / "app" / "static"
    for file in static_dir.rglob("*"):
        if file.is_file() and file.suffix in [".html", ".js", ".css"]:
            content = file.read_text(encoding="utf-8")
            if FAKE_KEY:
                assert FAKE_KEY not in content, f"Key leaked in static file {file}"
            assert "ELEVENLABS_API_KEY" not in content, f"Env var leaked in {file}"

def test_secret_never_appears_in_logs():
    """Vector 3: Verify SensitiveDataFilter scrubs API key from all log strings."""
    sample_key = "sk_dummy_test_key_for_unit_tests"
    raw_log = f"Failed to reach ElevenLabs API using secret {sample_key} with Bearer eyJhbGciOi"
    scrubbed = sanitize_string(raw_log)
    assert sample_key not in scrubbed
    assert "sk_***" in scrubbed
    assert "Bearer ***" in scrubbed

@pytest.mark.asyncio
async def test_secret_never_appears_in_errors(client: AsyncClient, user_token: str):
    """Vector 4: Verify error responses sanitize internal provider details and keys."""
    # Attempt invalid audio upload to STT
    res = await client.post(
        "/api/speech/stt",
        headers={"Authorization": f"Bearer {user_token}"},
        files={"file": ("fake.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-dosexec")},
    )
    assert res.status_code in [400, 415, 422]
    if FAKE_KEY:
        assert FAKE_KEY not in res.text
    # Ensure no internal stack trace leaked
    assert "Traceback" not in res.text

def test_secret_never_appears_in_websocket_messages(user_token: str):
    """Vector 5: Verify WebSocket handshakes and message streams never transmit the API key."""
    client = TestClient(app)
    with client.websocket_connect(f"/ws/voice?token={user_token}") as ws:
        ready_msg = ws.receive_json()
        assert ready_msg["type"] == "ready"
        if FAKE_KEY:
            assert FAKE_KEY not in str(ready_msg)
        ws.send_json({"type": "ping"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "pong"
        if FAKE_KEY:
            assert FAKE_KEY not in str(pong_msg)

@pytest.mark.asyncio
async def test_secret_never_stored_in_database_records(db_session):
    """Vector 6: Verify no raw ElevenLabs key is persisted in any database table."""
    tables_to_check = [
        select(User),
        select(UserVoicePreference),
        select(ConversationSession),
        select(Message),
        select(SecurityAuditLog),
        select(ElevenLabsUsageLog),
    ]

    for stmt in tables_to_check:
        result = await db_session.execute(stmt)
        records = result.scalars().all()
        for r in records:
            repr_str = repr(r)
            if FAKE_KEY:
                assert FAKE_KEY not in repr_str, f"Secret key found stored in DB record: {r}"

@pytest.mark.asyncio
async def test_secret_never_appears_in_generated_documentation(client: AsyncClient):
    """Vector 7: Verify OpenAPI schema does not expose any real or fake API keys."""
    res = await client.get("/openapi.json")
    if res.status_code == 200:
        doc_text = res.text
        if FAKE_KEY:
            assert FAKE_KEY not in doc_text, "Secret key exposed in OpenAPI documentation schema"
