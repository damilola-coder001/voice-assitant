import asyncio
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"

def run_audit():
    print("=== Auditing All User Endpoints ===")
    # 1. Login
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"email": "user@nore.ai", "password": "NoreUser#2026!Client"}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    token = data["access_token"]
    refresh_token = data["refresh_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("[+] Login OK")

    endpoints = [
        ("GET", "/api/auth/me", None),
        ("GET", "/api/personas", None),
        ("GET", "/api/voices", None),
        ("GET", "/api/voices/models", None),
        ("GET", "/api/users/me/voice-preferences", None),
        ("PUT", "/api/users/me/voice-preferences", {
            "preferred_voice_id": "FGY2WhTYpPnrIDTdsKH5",
            "preferred_voice_name": "Roger",
            "preferred_model_id": "eleven_turbo_v2_5",
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
            "auto_speak": True,
            "active_persona_id": "executive",
            "assistant_name": "NORE",
            "tone": "balanced",
            "formality": "professional",
            "response_style": "adaptive",
            "preferred_language": "en",
            "tech_interests": "ai_ml,software_dev",
            "tech_explanation_level": "intermediate",
            "tech_briefing_topics": "all",
            "tech_summary_style": "balanced"
        }),
        ("GET", "/api/conversations", None),
        ("POST", "/api/conversations", {"title": "Audit Test Conversation", "persona_id": "executive"}),
    ]

    conv_id = None
    for method, ep, body in endpoints:
        req_data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{BASE}{ep}", data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode())
                print(f"[+] {method} {ep} -> {resp.status} (keys/len: {len(res) if isinstance(res, (list, dict)) else 'ok'})")
                if ep == "/api/conversations" and method == "POST":
                    conv_id = res["id"]
        except urllib.error.HTTPError as e:
            print(f"[-] {method} {ep} -> FAILED: {e.code} {e.read().decode()}")

    if conv_id:
        # Test conversation sub-endpoints
        sub_endpoints = [
            ("GET", f"/api/conversations/{conv_id}"),
            ("POST", f"/api/conversations/{conv_id}/messages", {"role": "user", "content": "Hello audit"}),
            ("GET", f"/api/conversations/{conv_id}/export?format=json"),
            ("GET", f"/api/conversations/{conv_id}/export?format=txt"),
            ("DELETE", f"/api/conversations/{conv_id}"),
        ]
        for item in sub_endpoints:
            method = item[0]
            ep = item[1]
            body = item[2] if len(item) > 2 else None
            req_data = json.dumps(body).encode() if body else None
            req = urllib.request.Request(f"{BASE}{ep}", data=req_data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req) as resp:
                    print(f"[+] {method} {ep} -> {resp.status}")
            except urllib.error.HTTPError as e:
                print(f"[-] {method} {ep} -> FAILED: {e.code} {e.read().decode()}")

    # RBAC check: User trying to access admin and owner endpoints should be blocked 403
    forbidden_endpoints = [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/usage"),
        ("GET", "/api/admin/audit-logs"),
        ("GET", "/api/admin/telemetry/tech"),
        ("GET", "/api/owner/admins"),
        ("GET", "/api/owner/system-config"),
    ]
    print("\n=== Checking RBAC Boundary Protections for User ===")
    for method, ep in forbidden_endpoints:
        req = urllib.request.Request(f"{BASE}{ep}", headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                print(f"[-] SECURITY BREACH: {ep} allowed user access! Status {resp.status}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(f"[+] Protected: {ep} properly returned 403 Forbidden")
            else:
                print(f"[?] {ep} returned {e.code}")

if __name__ == "__main__":
    run_audit()
