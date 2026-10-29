import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app

def test_websocket_auth_required():
    client = TestClient(app, raise_server_exceptions=False)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/voice"):
            pass

def test_websocket_valid_connection_and_ping(user_token: str):
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/voice?token={user_token}") as ws:
            # First message should be ready packet
            ready_data = ws.receive_json()
            assert ready_data["type"] == "ready"

            # Send ping
            ws.send_json({"type": "ping"})
            pong_data = ws.receive_json()
            assert pong_data["type"] == "pong"

def test_websocket_interrupt_handling(user_token: str):
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/voice?token={user_token}") as ws:
            ready_data = ws.receive_json()
            assert ready_data["type"] == "ready"

            # Send interrupt
            ws.send_json({"type": "interrupt"})
            resp = ws.receive_json()
            assert resp["type"] == "interrupted"
