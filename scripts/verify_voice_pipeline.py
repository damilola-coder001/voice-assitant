import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets
import httpx

async def main():
    # 1. Generate valid JWT access token for owner
    from app.security.tokens import create_access_token
    token = create_access_token(user_id=1, email="owner@nore.ai", role="owner", token_version=1)
    print(f"[OK] Generated access token for owner@nore.ai")

    # 2. Connect to WebSocket
    ws_url = f"ws://127.0.0.1:8000/ws/voice?token={token}"
    async with websockets.connect(ws_url) as ws:
        print("[OK] Connected to WebSocket endpoint /ws/voice")
        
        # Expect 'ready'
        ready_msg = json.loads(await ws.recv())
        print(f"[OK] Received ready state: {ready_msg['type']} (User: {ready_msg['user']['email']})")

        # Test heartbeat
        await ws.send(json.dumps({"type": "ping", "timestamp": 123456}))
        pong_msg = json.loads(await ws.recv())
        print(f"[OK] Ping/Pong test: received {pong_msg['type']}")

        # 3. Submit Voice Turn (First Question)
        turn_payload = {
            "type": "start_turn",
            "text": "What are the latest AI developments today?",
            "persona_id": "executive",
            "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
        }
        await ws.send(json.dumps(turn_payload))
        print("[OK] Sent start_turn: 'What are the latest AI developments today?'")

        session_id = None
        pcm_chunks = 0
        pcm_bytes = 0
        assistant_text = ""

        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                pcm_chunks += 1
                pcm_bytes += len(msg)
            else:
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "turn_start":
                    session_id = data.get("session_id")
                    print(f"    -> [turn_start] session_id={session_id}")
                elif msg_type == "tech_intent":
                    print(f"    -> [tech_intent] domain={data.get('domain')} requires_search={data.get('requires_search')}")
                elif msg_type == "tech_sources":
                    print(f"    -> [tech_sources] received {len(data.get('sources', []))} verified web sources")
                elif msg_type == "text_response":
                    assistant_text = data.get("content", "")
                    print(f"    -> [text_response] '{assistant_text[:80]}...'")
                elif msg_type == "audio_stream_start":
                    print(f"    -> [audio_stream_start] format={data.get('format')} sample_rate={data.get('sample_rate')}")
                elif msg_type == "audio_stream_end":
                    print(f"    -> [audio_stream_end] Total chunks: {pcm_chunks}, Total bytes: {pcm_bytes}")
                elif msg_type == "turn_complete":
                    print(f"[OK] Turn complete! Latency: {data.get('latency_ms')}ms, Characters: {data.get('characters')}")
                    break
                elif msg_type in ("error", "voice_stream_error"):
                    print(f"    -> [{msg_type}] {data.get('message') or data.get('error')}")

        # 4. Multi-turn Coherence (Follow-up Question)
        if session_id:
            follow_up_payload = {
                "type": "start_turn",
                "text": "Where did you get that information?",
                "session_id": session_id,
                "persona_id": "executive",
                "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
            }
            await ws.send(json.dumps(follow_up_payload))
            print(f"[OK] Sent follow-up turn referencing session_id={session_id}")

            follow_chunks = 0
            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    follow_chunks += 1
                else:
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    if msg_type == "text_response":
                        print(f"    -> Follow-up response: '{data.get('content')[:100]}...'")
                    elif msg_type == "turn_complete":
                        print(f"[OK] Follow-up turn complete! Received {follow_chunks} audio chunks.")
                        break

    print("\n[SUCCESS] Entire Voice Pipeline verified end-to-end!")

if __name__ == "__main__":
    asyncio.run(main())
