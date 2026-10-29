import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets
from app.security.tokens import create_access_token

CONVERSATION_TURNS = [
    {
        "id": 1,
        "label": "Greeting & Core Subject",
        "text": "Hello! Tell me about Bitcoin and how it works.",
        "persona_id": "executive",
        "interrupt_after_seconds": None,
        "pause_after_audio": 8,
    },
    {
        "id": 2,
        "label": "Technical Deep-Dive",
        "text": "How does proof of work prevent double-spending in that system?",
        "persona_id": "technical",
        "interrupt_after_seconds": None,
        "pause_after_audio": 8,
    },
    {
        "id": 3,
        "label": "Instant Interruption / Barge-In Test",
        "text": "Tell me a very detailed history of cryptographic hash functions from 1970 to present day.",
        "persona_id": "technical",
        "interrupt_after_seconds": 2.5,  # Real-time barge-in after 2.5s
        "pause_after_audio": 3,
    },
    {
        "id": 4,
        "label": "Fast Recovery & Real-Time Intelligence",
        "text": "What are the biggest breakthroughs in artificial intelligence announced this week?",
        "persona_id": "executive",
        "interrupt_after_seconds": None,
        "pause_after_audio": 10,
    },
    {
        "id": 5,
        "label": "Source Verification & Provenance",
        "text": "Where did you get that source information from?",
        "persona_id": "executive",
        "interrupt_after_seconds": None,
        "pause_after_audio": 8,
    },
    {
        "id": 6,
        "label": "Technology Comparison",
        "text": "Compare Python vs Rust for building high throughput backend services.",
        "persona_id": "technical",
        "interrupt_after_seconds": None,
        "pause_after_audio": 8,
    },
    {
        "id": 7,
        "label": "Mathematical Reasoning",
        "text": "What is 450 multiplied by 80?",
        "persona_id": "concise",
        "interrupt_after_seconds": None,
        "pause_after_audio": 5,
    },
    {
        "id": 8,
        "label": "Software Architecture Guidance",
        "text": "What is the best architectural pattern for managing full duplex WebSockets in FastAPI?",
        "persona_id": "technical",
        "interrupt_after_seconds": None,
        "pause_after_audio": 8,
    },
    {
        "id": 9,
        "label": "Time & Closing Wrap-Up",
        "text": "Thank you NORE! What time is it right now, and can you wrap up our session?",
        "persona_id": "executive",
        "interrupt_after_seconds": None,
        "pause_after_audio": 3,
    },
]

async def run_5min_session():
    start_session_wall = time.time()
    print("=" * 75)
    print("  NORE PLATFORM - LIVE MULTI-TURN CONVERSATION SESSION")
    print("  Target: 9 realistic turns across ~5 minutes, testing full pipeline")
    print("=" * 75, flush=True)

    token = create_access_token(user_id=1, email="owner@nore.ai", role="owner", token_version=18)
    ws_url = f"ws://127.0.0.1:8000/ws/voice?token={token}"

    session_metrics = []
    session_id = None

    async with websockets.connect(ws_url) as ws:
        ready_raw = await ws.recv()
        ready_data = json.loads(ready_raw)
        print(f"\n[+] Connected to WebSocket. Ready: {ready_data.get('type')} (User: {ready_data.get('user', {}).get('email')})", flush=True)

        await ws.send(json.dumps({"type": "ping", "timestamp": int(time.time() * 1000)}))
        pong_data = json.loads(await ws.recv())
        print(f"[+] Heartbeat verified: {pong_data.get('type')}", flush=True)

        for turn_idx, turn in enumerate(CONVERSATION_TURNS, 1):
            elapsed_overall = time.time() - start_session_wall
            print("\n" + "-" * 75, flush=True)
            print(f"[Turn {turn_idx}/9 | Elapsed: {elapsed_overall:.1f}s] {turn['label']}", flush=True)
            print(f"  User >> \"{turn['text']}\"", flush=True)
            print(f"  Persona: {turn['persona_id']}", flush=True)

            turn_send_time = time.time()
            turn_payload = {
                "type": "start_turn",
                "text": turn["text"],
                "session_id": session_id,
                "persona_id": turn["persona_id"],
                "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
            }
            await ws.send(json.dumps(turn_payload))

            pcm_chunks = 0
            pcm_bytes = 0
            assistant_text = ""
            intent_info = {}
            sources_count = 0
            interrupted = False
            first_chunk_latency = None
            turn_complete_latency = None
            stream_start_time = None

            interruption_task = None
            if turn["interrupt_after_seconds"]:
                async def trigger_interrupt(delay: float):
                    await asyncio.sleep(delay)
                    print(f"  [!] Simulating user speech barge-in (sending 'interrupt' after {delay}s)...", flush=True)
                    await ws.send(json.dumps({"type": "interrupt"}))
                interruption_task = asyncio.create_task(trigger_interrupt(turn["interrupt_after_seconds"]))

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=25.0)
                except asyncio.TimeoutError:
                    print("  [!] Timeout waiting for WebSocket message!", flush=True)
                    break

                if isinstance(msg, bytes):
                    if stream_start_time is None:
                        stream_start_time = time.time()
                        first_chunk_latency = (stream_start_time - turn_send_time) * 1000

                    pcm_chunks += 1
                    pcm_bytes += len(msg)
                else:
                    data = json.loads(msg)
                    msg_type = data.get("type")

                    if msg_type == "turn_start":
                        session_id = data.get("session_id")
                    elif msg_type == "tech_intent":
                        intent_info = {
                            "domain": data.get("domain"),
                            "intent": data.get("intent"),
                            "requires_search": data.get("requires_search"),
                        }
                    elif msg_type == "tech_sources":
                        sources_count = len(data.get("sources", []))
                    elif msg_type == "text_response":
                        assistant_text = data.get("content", "")
                    elif msg_type == "interrupted":
                        interrupted = True
                        print("  [+] Server acknowledged interruption immediately.", flush=True)
                        # Drain any immediate leftover messages
                        try:
                            while True:
                                extra = await asyncio.wait_for(ws.recv(), timeout=0.3)
                                if isinstance(extra, str):
                                    ex_data = json.loads(extra)
                                    if ex_data.get("type") == "turn_complete":
                                        break
                        except (asyncio.TimeoutError, Exception):
                            pass
                        break
                    elif msg_type == "turn_complete":
                        turn_complete_latency = data.get("latency_ms")
                        break
                    elif msg_type in ("error", "voice_stream_error"):
                        print(f"  [!] Notice: {data.get('message') or data.get('error')}", flush=True)
                        break

            if interruption_task and not interruption_task.done():
                interruption_task.cancel()

            audio_duration_sec = pcm_bytes / 48000.0
            first_chunk_str = f"{first_chunk_latency:.0f}ms" if first_chunk_latency is not None else "N/A"

            preview = assistant_text[:110] + "..." if len(assistant_text) > 110 else assistant_text
            print(f"  Assistant << \"{preview}\"", flush=True)
            print(f"  Stats: First Chunk: {first_chunk_str} | Chunks: {pcm_chunks} ({pcm_bytes} bytes ~ {audio_duration_sec:.1f}s audio) | Intent: {intent_info.get('domain', 'N/A')} | Sources: {sources_count}", flush=True)

            session_metrics.append({
                "turn": turn_idx,
                "label": turn["label"],
                "user_text": turn["text"],
                "assistant_text": assistant_text,
                "first_chunk_ms": first_chunk_latency,
                "total_latency_ms": turn_complete_latency,
                "audio_duration_sec": audio_duration_sec,
                "pcm_bytes": pcm_bytes,
                "pcm_chunks": pcm_chunks,
                "interrupted": interrupted,
                "sources_count": sources_count,
                "intent": intent_info,
            })

            simulated_speech_time = min(audio_duration_sec, 20.0) if not interrupted else turn["interrupt_after_seconds"]
            pause_time = turn["pause_after_audio"]
            total_turn_dwell = simulated_speech_time + pause_time

            print(f"  [Listening: {simulated_speech_time:.1f}s audio + User thinking pause: {pause_time:.1f}s -> advancing {total_turn_dwell:.1f}s]", flush=True)
            await asyncio.sleep(pause_time)

    total_session_time = time.time() - start_session_wall
    print("\n" + "=" * 75, flush=True)
    print(f"  CONVERSATION COMPLETE: Total Elapsed Wall Clock = {total_session_time:.1f}s (~{total_session_time/60.0:.2f} mins)", flush=True)
    print("=" * 75, flush=True)

    report_path = Path("scratch/conversation_5min_report.json")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_wall_time_sec": total_session_time,
            "turns_completed": len(session_metrics),
            "metrics": session_metrics,
        }, f, indent=2)
    print(f"[OK] Complete detailed report saved to {report_path}", flush=True)

if __name__ == "__main__":
    asyncio.run(run_5min_session())
