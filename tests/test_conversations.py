import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_conversation_crud_and_export(client: AsyncClient, user_token: str):
    headers = {"Authorization": f"Bearer {user_token}"}

    # 1. Create Session
    create_res = await client.post(
        "/api/conversations",
        headers=headers,
        json={"title": "Test AI Voice Strategy", "persona_id": "technical"},
    )
    assert create_res.status_code == 201
    session = create_res.json()
    session_id = session["id"]
    assert session["title"] == "Test AI Voice Strategy"

    # 2. Add message to session
    msg_res = await client.post(
        f"/api/conversations/{session_id}/messages",
        headers=headers,
        json={"role": "user", "content": "How do we scale WebSocket connections?"},
    )
    assert msg_res.status_code == 201

    assistant_msg_res = await client.post(
        f"/api/conversations/{session_id}/messages",
        headers=headers,
        json={"role": "assistant", "content": "Use Redis pub/sub and distributed connection brokers."},
    )
    assert assistant_msg_res.status_code == 201

    # 3. Retrieve Session
    get_res = await client.get(f"/api/conversations/{session_id}", headers=headers)
    assert get_res.status_code == 200
    full_session = get_res.json()
    assert len(full_session["messages"]) == 2

    # 4. Export Markdown
    export_md = await client.get(f"/api/conversations/{session_id}/export?format=markdown", headers=headers)
    assert export_md.status_code == 200
    assert "Test AI Voice Strategy" in export_md.json()["content"]

    # 5. Delete Session
    del_res = await client.delete(f"/api/conversations/{session_id}", headers=headers)
    assert del_res.status_code == 204
