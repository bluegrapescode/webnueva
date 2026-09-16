"""Backend tests for global bounty system (La Isla Nublar)."""
import os
import time
import json
import pytest
import requests
import websocket  # websocket-client
from urllib.parse import urlparse

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fall back to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = BASE_URL + "/api"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo auth failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ----- config defaults -----
def test_bounty_config_defaults():
    r = requests.get(f"{API}/bounty/config", timeout=10)
    assert r.status_code == 200
    cfg = r.json()
    expected = {
        "prime_meat": 60000,
        "experience": 2500,
        "amberium": 500,
        "next_bounty_delay": 1200,
        "minimum_online_time": 900,
        "recent_target_protection": 3,
        "disconnect_grace": 300,
    }
    for k, v in expected.items():
        assert cfg.get(k) == v, f"expected {k}={v}, got {cfg.get(k)}"


def test_bounty_current_shape():
    r = requests.get(f"{API}/bounty/current", timeout=10)
    assert r.status_code == 200
    j = r.json()
    for k in ("phase", "paused", "bounty", "config"):
        assert k in j, f"missing key {k} in {j}"


# ----- admin auth guard -----
def test_force_new_requires_auth():
    r = requests.post(f"{API}/bounty/admin/force-new", timeout=10)
    assert r.status_code in (401, 403)


# ----- force-new + shape -----
def test_admin_force_new_and_current(auth_headers):
    # cancel anything first for clean state
    requests.post(f"{API}/bounty/admin/cancel", headers=auth_headers, timeout=10)
    r = requests.post(f"{API}/bounty/admin/force-new", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    b = j.get("bounty") or j
    # walk possible shapes
    if "bounty" in j and j["bounty"]:
        b = j["bounty"]
    assert b.get("targetName"), f"missing targetName: {j}"
    assert b.get("dinosaur"), f"missing dinosaur: {j}"
    rewards = b.get("rewards") or {}
    assert "primeMeat" in rewards and "experience" in rewards and "amberium" in rewards
    assert str(b.get("bountyId", "")).startswith("BNT-"), f"bad bountyId {b.get('bountyId')}"

    cur = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur["phase"] == "active"
    assert cur["bounty"] is not None
    assert cur["bounty"].get("status") == "active"


# ----- simulate-kill completion & idempotency -----
def test_simulate_kill_completes_and_idempotent(auth_headers):
    # ensure active
    cur = requests.get(f"{API}/bounty/current", timeout=10).json()
    if cur.get("phase") != "active" or not cur.get("bounty"):
        requests.post(f"{API}/bounty/admin/force-new", headers=auth_headers, timeout=15)
        cur = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur.get("phase") == "active"
    active_id = cur["bounty"].get("bountyId")

    r1 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers, json={}, timeout=15)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("ok") is True

    # second call should be no-op
    r2 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers, json={}, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("ok") is False

    cur2 = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur2["phase"] == "waiting"
    assert cur2["bounty"] is None

    hist = requests.get(f"{API}/bounty/history?limit=5", timeout=10).json()
    items = hist.get("items") or hist.get("history") or hist if isinstance(hist, list) else hist.get("items", [])
    # normalize
    if isinstance(hist, dict) and "items" in hist:
        items = hist["items"]
    elif isinstance(hist, list):
        items = hist
    ids = [i.get("bountyId") for i in items]
    # exactly one occurrence of that bountyId
    assert ids.count(active_id) == 1, f"expected 1 occurrence of {active_id}, got {ids}"
    entry = next(i for i in items if i.get("bountyId") == active_id)
    assert entry.get("status") == "completed"
    assert entry.get("killerName")
    assert entry.get("rewardProcessed") is True


# ----- admin config update -----
def test_admin_config_update(auth_headers):
    r = requests.post(f"{API}/bounty/admin/config", headers=auth_headers,
                      json={"amberium": 750}, timeout=10)
    assert r.status_code == 200, r.text
    cfg = requests.get(f"{API}/bounty/config", timeout=10).json()
    assert cfg["amberium"] == 750
    # revert
    r2 = requests.post(f"{API}/bounty/admin/config", headers=auth_headers,
                      json={"amberium": 500}, timeout=10)
    assert r2.status_code == 200
    cfg2 = requests.get(f"{API}/bounty/config", timeout=10).json()
    assert cfg2["amberium"] == 500


# ----- pause/resume -----
def test_pause_resume(auth_headers):
    r = requests.post(f"{API}/bounty/admin/pause", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    cur = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur["paused"] is True
    r2 = requests.post(f"{API}/bounty/admin/resume", headers=auth_headers, timeout=10)
    assert r2.status_code == 200
    cur2 = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur2["paused"] is False


# ----- force + cancel -----
def test_force_then_cancel(auth_headers):
    requests.post(f"{API}/bounty/admin/force-new", headers=auth_headers, timeout=15)
    r = requests.post(f"{API}/bounty/admin/cancel", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    assert r.json().get("cancelled") is True
    cur = requests.get(f"{API}/bounty/current", timeout=10).json()
    assert cur["bounty"] is None
    assert cur["phase"] == "waiting"


# ----- websocket -----
def test_bounty_ws_state_and_ping():
    parsed = urlparse(BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}/api/bounty/ws"
    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        first = ws.recv()
        data = json.loads(first)
        assert data.get("event") == "bounty:state", f"unexpected first frame: {data}"
        d = data.get("data") or {}
        assert "phase" in d
        assert "config" in d
        ws.send("ping")
        # allow a couple frames; look for "pong"
        pong = None
        for _ in range(5):
            try:
                msg = ws.recv()
            except Exception:
                break
            if msg == "pong" or (isinstance(msg, str) and msg.strip() == "pong"):
                pong = "pong"
                break
            # some servers send json event
            try:
                jj = json.loads(msg)
                if jj.get("event") == "pong":
                    pong = "pong"
                    break
            except Exception:
                pass
        assert pong == "pong", "expected pong reply"
    finally:
        ws.close()
