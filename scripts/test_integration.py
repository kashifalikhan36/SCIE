"""
Comprehensive SCIE API & WebSocket Integration Test
Tests the full workflow:
  1. Upload interview video
  2. Monitor WebSocket for live telemetry
  3. Poll Redis for status progression
  4. Verify MongoDB data was written
  5. Check all API endpoints
"""

import asyncio
import json
import time
import sys
import os
import websockets
import requests

# Force UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VIDEO_PATH = r"C:\Users\Data\Documents\GitHub\SCIE\tests\video\interview.mp4"
API_BASE   = "http://127.0.0.1:8000"
WS_BASE    = "ws://127.0.0.1:8000"

# ─── ANSI Colors ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def info(msg):  print(f"  {CYAN}→{RESET} {msg}")
def head(msg):  print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}\n{BOLD} {msg}{RESET}\n{BOLD}{CYAN}{'═'*60}{RESET}")

def wait_for_server(timeout=30):
    """Wait up to `timeout` seconds for uvicorn to be ready."""
    print(f"\n  Waiting for server at {API_BASE}...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API_BASE}/api/v1/dashboard/meetings", timeout=2)
            if r.status_code < 500:
                print(f" ready!")
                return True
        except Exception:
            pass
        time.sleep(1)
        print(".", end="", flush=True)
    print(f" TIMEOUT after {timeout}s")
    return False

# ─── STEP 1: Upload ────────────────────────────────────────────────────────────
def test_upload():
    head("STEP 1: Upload Interview Video")
    # New simplified metadata — only what Sherlock needs as identity anchors
    metadata = {
        "candidate": "Alice Smith",
        "candidate_email": "alice.smith@example.com",
        "interviewers": ["Bob Jones", "Carol Lee"]
    }
    # No participants — auto-detected from video
    participants = []

    info(f"Uploading: {VIDEO_PATH}")
    with open(VIDEO_PATH, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/api/v1/interviews/upload",
            files={"video": ("interview.mp4", f, "video/mp4")},
            data={
                "metadata": json.dumps(metadata),
                "participants": json.dumps(participants)
            },
            timeout=60
        )

    if resp.status_code == 200:
        data = resp.json()
        meeting_id = data["meeting_id"]
        ok(f"Upload success! meeting_id = {YELLOW}{meeting_id}{RESET}")
        return meeting_id
    else:
        fail(f"Upload failed: {resp.status_code} — {resp.text}")
        sys.exit(1)

# ─── STEP 2: REST Status Poll ──────────────────────────────────────────────────
def check_status_rest(meeting_id):
    resp = requests.get(f"{API_BASE}/api/v1/interviews/{meeting_id}/status", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return {}

# ─── STEP 3: WebSocket Monitor ────────────────────────────────────────────────
async def monitor_websocket(meeting_id, max_wait_secs=600):
    head("STEP 2: WebSocket Live Telemetry Monitor")
    url = f"{WS_BASE}/ws/dashboard/{meeting_id}"
    info(f"Connecting to {url}")

    last_status = None
    last_progress = -1
    completed = False
    errored   = False

    try:
        async with websockets.connect(url, ping_interval=20) as ws:
            ok("WebSocket connected!")
            start = time.time()
            while time.time() - start < max_wait_secs:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg.get("type") == "progress":
                        d = msg["data"]
                        s  = d.get("status", "")
                        p  = d.get("progress", 0)
                        eta= d.get("estimated_time_remaining", "?")
                        logs = d.get("logs", [])

                        if s != last_status or abs(p - last_progress) >= 1:
                            last_status   = s
                            last_progress = p
                            bar_fill = int(p / 2)
                            bar = "█" * bar_fill + "░" * (50 - bar_fill)
                            color = GREEN if "Completed" in s else (RED if "Error" in s else CYAN)
                            print(f"\r  {color}{p:5.1f}%{RESET} [{bar}] {YELLOW}{s}{RESET}  ETA: {eta}      ", end="", flush=True)
                            if logs:
                                print(f"\n  {CYAN}Last log:{RESET} {logs[-1]}")

                        if "Completed" in s:
                            print()
                            ok("Processing COMPLETED!")
                            completed = True
                            break
                        if "Error" in s:
                            print()
                            fail(f"Processing ERRORED: {s}")
                            if logs:
                                for l in logs[-5:]:
                                    print(f"    {RED}{l}{RESET}")
                            errored = True
                            break
                except asyncio.TimeoutError:
                    # No message for 5s — server might still be working
                    print(".", end="", flush=True)

    except Exception as e:
        fail(f"WebSocket error: {e}")

    return completed, errored

# ─── STEP 4: Verify REST APIs ─────────────────────────────────────────────────
def test_rest_apis(meeting_id):
    head("STEP 3: REST API Verification")

    endpoints = [
        ("GET", f"/api/v1/dashboard/meetings",                "List all meetings"),
        ("GET", f"/api/v1/dashboard/meetings/{meeting_id}",   "Get meeting summary"),
        ("GET", f"/api/v1/interviews/{meeting_id}/status",    "Processing status"),
        ("GET", f"/api/v1/interviews/{meeting_id}/summary",   "Reasoning report"),
        ("GET", f"/api/v1/dashboard/stats",                   "Dashboard stats"),
    ]

    all_pass = True
    for method, path, label in endpoints:
        try:
            r = requests.request(method, f"{API_BASE}{path}", timeout=10)
            if r.status_code in (200, 201):
                ok(f"{label} ({path}) → {r.status_code}")
                try:
                    body = r.json()
                    # Quick sanity checks
                    if "meetings" in path and "meetings" in path.split("/")[-1]:
                        assert isinstance(body, list), "Expected list"
                    if "status" in path:
                        assert "status" in body or "progress" in body
                except Exception as e:
                    print(f"    {YELLOW}⚠ Body check: {e}{RESET}")
            else:
                fail(f"{label} → {r.status_code}: {r.text[:200]}")
                all_pass = False
        except Exception as e:
            fail(f"{label} → exception: {e}")
            all_pass = False

    return all_pass

# ─── STEP 5: Check MongoDB Data ───────────────────────────────────────────────
async def check_mongodb(meeting_id):
    head("STEP 4: MongoDB Data Verification")
    try:
        # Add the repo root to path so we can import database, core, etc.
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, repo_root)
        orig_dir = os.getcwd()
        os.chdir(repo_root)

        from database.mongodb import MongoClientManager, get_mongo_db

        mgr = MongoClientManager.get_instance()
        mgr.initialize()
        await mgr.check_connection()
        db = get_mongo_db()

        meeting = await db.meetings.find_one({"meeting_id": meeting_id})
        if meeting:
            ok(f"Meeting in MongoDB: status={meeting.get('status','?')}, source={meeting.get('source','?')}")
            meta = meeting.get("extra_data", {})
            if meta.get("candidate"):
                ok(f"Candidate metadata saved: {meta['candidate']}")
            else:
                info("Candidate not in extra_data (check metadata shape)")
            parts = meeting.get("participants_data", [])
            ok(f"Participants saved: {len(parts)}")
        else:
            fail("Meeting NOT found in MongoDB!")
            return False

        for coll_name in ["transcript_segments", "voice_evidence", "reasoning_reports", "fusion_ranking_snapshots", "identity_matches"]:
            count = await db[coll_name].count_documents({"meeting_id": meeting_id})
            color = GREEN if count > 0 else YELLOW
            print(f"  {color}{'✓' if count > 0 else '→'}{RESET} {coll_name}: {count} docs")

        # Check identity result stored in meeting doc
        identity = (meeting or {}).get("identity_result")
        if identity:
            ok(f"Sherlock ID: '{identity.get('identified_display_name')}' as '{identity.get('candidate_name')}' "
               f"(score={identity.get('score', 0):.2f}, conf={identity.get('confidence', 0):.2f})")
        else:
            info("No identity_result yet (identity pipeline may still be running)")

        os.chdir(orig_dir)
        return True
    except Exception as e:
        fail(f"MongoDB check exception: {e}")
        import traceback; traceback.print_exc()
        return False
    except Exception as e:
        fail(f"MongoDB check exception: {e}")
        import traceback; traceback.print_exc()
        return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║      SCIE Full Integration Test Suite                    ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}\n")

    if not wait_for_server():
        sys.exit(1)

    # Upload
    meeting_id = test_upload()

    # Monitor via WebSocket until done
    completed, errored = await monitor_websocket(meeting_id, max_wait_secs=900)

    # REST API checks
    api_ok = test_rest_apis(meeting_id)

    # MongoDB checks
    db_ok = await check_mongodb(meeting_id)

    # Final Summary
    head("TEST SUMMARY")
    print(f"  Meeting ID : {YELLOW}{meeting_id}{RESET}")
    print(f"  Processing : {'COMPLETED ✓' if completed else 'ERRORED ✗' if errored else 'TIMED OUT'}")
    print(f"  REST APIs  : {'PASS ✓' if api_ok else 'FAIL ✗'}")
    print(f"  MongoDB    : {'PASS ✓' if db_ok else 'FAIL ✗'}")
    print()

if __name__ == "__main__":
    asyncio.run(main())
