import asyncio
import json
import urllib.request
import websockets

BASE_HTTP = "http://127.0.0.1:8000"
BASE_WS = "ws://127.0.0.1:8000"

async def test_full_user_experience():
    print("=== Step 1: User Login ===")
    req = urllib.request.Request(
        f"{BASE_HTTP}/api/auth/login",
        data=json.dumps({"email": "user@nore.ai", "password": "NoreUser#2026!Client"}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        login_data = json.loads(resp.read().decode())
    
    token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]
    print(f"[OK] Logged in as: {login_data['user']['email']}, User ID: {login_data['user']['id']}")
    
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("\n=== Step 2: Fetch Current User Profile (/api/auth/me) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/auth/me", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        me = json.loads(resp.read().decode())
    print(f"[OK] Profile: {me['email']}, Preferred voice: {me.get('voice_preference', {}).get('preferred_voice_id')}")

    print("\n=== Step 3: Fetch Personas (/api/personas) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/personas", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        personas = json.loads(resp.read().decode())
    print(f"[OK] Personas loaded: {len(personas)} personas -> {[p['id'] for p in personas]}")

    print("\n=== Step 4: Fetch Voices (/api/voices) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/voices", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        voices = json.loads(resp.read().decode())
    print(f"[OK] Voices loaded: {len(voices)} voices")

    print("\n=== Step 5: Fetch Voice Preferences (/api/users/me/voice-preferences) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/users/me/voice-preferences", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        prefs = json.loads(resp.read().decode())
    print(f"[OK] Voice preferences: {prefs}")

    print("\n=== Step 6: Fetch Conversations (/api/conversations) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/conversations", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        conversations = json.loads(resp.read().decode())
    print(f"[OK] Existing conversations count: {len(conversations)}")

    print("\n=== Step 7: Connect to Real-time WebSocket (/ws/voice) ===")
    ws_url = f"{BASE_WS}/ws/voice?token={token}"
    async with websockets.connect(ws_url) as ws:
        # Wait for ready message
        ready_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        ready_data = json.loads(ready_msg)
        print(f"[OK] WebSocket ready: {ready_data}")

        # Send Ping
        print("\n--- Testing Ping ---")
        await ws.send(json.dumps({"type": "ping"}))
        pong_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        print(f"[OK] Pong received: {pong_msg}")

        # Test Turn 1: Conversational / greeting prompt
        print("\n--- Testing Turn 1: 'Hello NORE, who are you and what can you help me with?' ---")
        await ws.send(json.dumps({
            "type": "start_turn",
            "text": "Hello NORE, who are you and what can you help me with?",
            "session_id": None,
            "persona_id": "executive",
            "voice_id": "CwhRBWXzGAHq8TQ4Fs17"
        }))

        received_types = []
        full_text = ""
        binary_chunks = 0
        session_id = None

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                if isinstance(msg, bytes):
                    binary_chunks += 1
                else:
                    data = json.loads(msg)
                    received_types.append(data.get("type"))
                    if data.get("type") == "turn_start":
                        session_id = data.get("session_id")
                        print(f"  -> Turn started, session ID: {session_id}")
                    elif data.get("type") == "text_response":
                        full_text = data.get("content", "")
                        print(f"  -> Text response: {full_text[:80]}...")
                    elif data.get("type") == "turn_complete":
                        print(f"  -> Turn complete. Latency: {data.get('latency_ms')}ms, Chunks: {binary_chunks}")
                        break
                    elif data.get("type") == "error":
                        print(f"  ! Error: {data}")
                        break
            except asyncio.TimeoutError:
                print("  ! Timeout waiting for turn complete")
                break

        print(f"[OK] Turn 1 received types: {received_types}, Binary audio chunks: {binary_chunks}")

        # Test Turn 2: Tech intelligence query
        print("\n--- Testing Turn 2: 'What is the latest AI news?' ---")
        await ws.send(json.dumps({
            "type": "start_turn",
            "text": "What is the latest AI news?",
            "session_id": session_id,
            "persona_id": "executive",
            "voice_id": "CwhRBWXzGAHq8TQ4Fs17"
        }))

        turn2_types = []
        turn2_text = ""
        turn2_binary = 0
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=35.0)
                if isinstance(msg, bytes):
                    turn2_binary += 1
                else:
                    data = json.loads(msg)
                    turn2_types.append(data.get("type"))
                    if data.get("type") == "tech_intent":
                        print(f"  -> Tech intent detected: {data.get('intent')}, domain: {data.get('domain')}")
                    elif data.get("type") == "tech_sources":
                        print(f"  -> Sources count: {len(data.get('sources', []))}")
                    elif data.get("type") == "briefing_data":
                        print(f"  -> Briefing headlines: {len(data.get('briefing', {}).get('items', []))}")
                    elif data.get("type") == "text_response":
                        turn2_text = data.get("content", "")
                        print(f"  -> Spoken Response: {turn2_text}")
                    elif data.get("type") == "turn_complete":
                        print(f"  -> Turn 2 complete. Audio chunks: {turn2_binary}")
                        break
                    elif data.get("type") == "error":
                        print(f"  ! Turn 2 error: {data}")
                        break
            except asyncio.TimeoutError:
                print("  ! Timeout waiting for Turn 2")
                break

        print(f"[OK] Turn 2 received types: {turn2_types}")

        # Test Interruption
        print("\n--- Testing Turn 3: Interruption ---")
        await ws.send(json.dumps({
            "type": "start_turn",
            "text": "Tell me a long story about quantum computing and the universe.",
            "session_id": session_id,
            "persona_id": "executive",
            "voice_id": "CwhRBWXzGAHq8TQ4Fs17"
        }))
        # Wait for turn start, then immediately send interrupt
        interrupted_confirmed = False
        for _ in range(10):
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            if not isinstance(msg, bytes):
                data = json.loads(msg)
                if data.get("type") in ("turn_start", "text_response"):
                    print("  -> Turn in progress, triggering interrupt!")
                    await ws.send(json.dumps({"type": "interrupt"}))
                elif data.get("type") == "interrupted":
                    print("  [OK] Interrupted message acknowledged by server!")
                    interrupted_confirmed = True
                    break

        print(f"[OK] Interruption test passed: {interrupted_confirmed}")

    print("\n=== Step 8: Verify Conversation History Updated (/api/conversations) ===")
    req = urllib.request.Request(f"{BASE_HTTP}/api/conversations", headers=auth_headers)
    with urllib.request.urlopen(req) as resp:
        updated_convs = json.loads(resp.read().decode())
    print(f"[OK] Updated conversations count: {len(updated_convs)}")
    if updated_convs:
        latest = updated_convs[0]
        print(f"  Latest session: ID={latest['id']}, Title='{latest['title']}', Turns={latest['message_count']}")

        # Fetch detail of latest conversation
        req = urllib.request.Request(f"{BASE_HTTP}/api/conversations/{latest['id']}", headers=auth_headers)
        with urllib.request.urlopen(req) as resp:
            conv_detail = json.loads(resp.read().decode())
        print(f"[OK] Conversation detail retrieved: {len(conv_detail.get('messages', []))} messages")
        for m in conv_detail.get('messages', []):
            print(f"    [{m['role'].upper()}]: {m['content'][:60]}...")

    print("\n=== ALL USER SIMULATION CHECKS COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(test_full_user_experience())
