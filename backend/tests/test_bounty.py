"""Backend tests for player-placed bounty system (Sistema de Cacería)."""
import os
import json
import time
import pytest
import requests
import websocket  # websocket-client
from urllib.parse import urlparse

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = BASE_URL + "/api"


# ── fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo auth failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(autouse=True)
def _cleanup_between_tests(auth_headers):
    """Cancel any active self/contracts belonging to the demo user before each
    test so state is deterministic."""
    try:
        mine = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
        for c in mine.get("contracts", []) or []:
            requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                          json={"bounty_id": c["bountyId"]}, timeout=10)
    except Exception:
        pass
    yield


# ── config ───────────────────────────────────────────────────────────
def test_bounty_config_defaults():
    r = requests.get(f"{API}/bounty/config", timeout=10)
    assert r.status_code == 200
    cfg = r.json()
    expected = {
        "min_contract_prime": 20000,
        "self_prime_per_min": 5000,
        "self_max_seconds": 900,
        "self_killer_amber": 300,
        "self_cooldown": 600,
        "max_contracts_per_user": 1,
    }
    for k, v in expected.items():
        assert cfg.get(k) == v, f"config[{k}] expected {v}, got {cfg.get(k)}"


# ── targets: auth-gated ──────────────────────────────────────────────
def test_targets_requires_auth():
    r = requests.get(f"{API}/bounty/targets", timeout=10)
    assert r.status_code in (401, 403), r.status_code


def test_targets_shape(auth_headers):
    r = requests.get(f"{API}/bounty/targets", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j.get("targets"), list)
    assert j.get("simulated") is True  # no real game server in preview
    assert len(j["targets"]) > 0
    t0 = j["targets"][0]
    for k in ("sid", "name", "species", "slug", "alive", "isMe", "bounty"):
        assert k in t0
    for k in ("primeMeat", "amberium", "count"):
        assert k in t0["bounty"]


# ── place / mine / board / cancel ────────────────────────────────────
def _pick_target(auth_headers, exclude_sid=None):
    r = requests.get(f"{API}/bounty/targets", headers=auth_headers, timeout=10).json()
    for t in r["targets"]:
        if t["isMe"]:
            continue
        if exclude_sid and str(t["sid"]) == str(exclude_sid):
            continue
        return t
    return None


def test_place_contract_charges_and_appears_on_board(auth_headers):
    # wallet before
    me_before = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    coins_before = int(me_before.get("coins", 0))
    vip_before = int(me_before.get("vip_coins", 0))
    assert coins_before >= 20000, "demo user must have >=20000 PrimeMeat"

    tgt = _pick_target(auth_headers)
    assert tgt is not None

    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 20000, "amber": 0},
                      timeout=15)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["type"] == "contract"
    assert b["status"] == "active"
    assert str(b["targetId"]) == str(tgt["sid"])
    assert b["reward"]["primeMeat"] == 20000
    bid = b["bountyId"]

    # mine shows it
    mine = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
    ids = [c["bountyId"] for c in mine["contracts"]]
    assert bid in ids

    # board contains the target with primeMeat>=20000
    board = requests.get(f"{API}/bounty/board", timeout=10).json()["board"]
    target_entry = next((c for c in board["contracts"] if str(c["targetId"]) == str(tgt["sid"])), None)
    assert target_entry is not None
    assert target_entry["reward"]["primeMeat"] >= 20000

    # wallet decreased by exactly prime
    me_after = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    assert int(me_after.get("coins", 0)) == coins_before - 20000, \
        f"expected coins {coins_before-20000}, got {me_after.get('coins')}"
    assert int(me_after.get("vip_coins", 0)) == vip_before

    # cleanup: cancel refunds
    rc = requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                       json={"bounty_id": bid}, timeout=10)
    assert rc.status_code == 200
    assert rc.json().get("ok") is True

    me_end = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    assert int(me_end.get("coins", 0)) == coins_before, "cancel must refund fully"

    # board no longer has the entry (or it may exist with lower total if others placed)
    board2 = requests.get(f"{API}/bounty/board", timeout=10).json()["board"]
    still = next((c for c in board2["contracts"] if str(c["targetId"]) == str(tgt["sid"])), None)
    # after cancel it should be gone (assuming no other placer; demo is the only user we control)
    assert (still is None) or (still["reward"]["primeMeat"] == 0)


# ── validation ───────────────────────────────────────────────────────
def test_contract_below_minimum_is_rejected(auth_headers):
    me_before = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    coins_before = int(me_before.get("coins", 0))

    tgt = _pick_target(auth_headers)
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 100, "amber": 0},
                      timeout=10)
    assert r.status_code == 400
    body = r.json()
    msg = body.get("detail") or body.get("message") or ""
    assert "20000" in str(msg) or "mínimo" in str(msg).lower()

    # wallet unchanged
    me_after = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    assert int(me_after.get("coins", 0)) == coins_before


def test_contract_limit_one_active(auth_headers):
    tgt1 = _pick_target(auth_headers)
    r1 = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                       json={"target_sid": tgt1["sid"], "prime": 20000, "amber": 0}, timeout=15)
    assert r1.status_code == 200, r1.text
    bid = r1.json()["bountyId"]
    try:
        tgt2 = _pick_target(auth_headers, exclude_sid=tgt1["sid"])
        r2 = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                           json={"target_sid": tgt2["sid"], "prime": 20000, "amber": 0}, timeout=15)
        assert r2.status_code == 400, f"expected 400, got {r2.status_code} {r2.text}"
    finally:
        requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                      json={"bounty_id": bid}, timeout=10)


def test_contract_insufficient_funds(auth_headers):
    me = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    coins = int(me.get("coins", 0))
    absurd = coins + 10_000_000
    tgt = _pick_target(auth_headers)
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": absurd, "amber": 0}, timeout=15)
    assert r.status_code == 400, r.text
    body = r.json()
    msg = str(body.get("detail") or body.get("message") or "")
    assert "insuficiente" in msg.lower() or "Fondos" in msg
    me_after = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    assert int(me_after.get("coins", 0)) == coins  # not charged


# ── kill / claim: atomic + idempotent ────────────────────────────────
def test_simulate_kill_is_atomic_and_idempotent(auth_headers):
    tgt = _pick_target(auth_headers)
    r1 = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                       json={"target_sid": tgt["sid"], "prime": 20000, "amber": 0}, timeout=15)
    assert r1.status_code == 200, r1.text
    bid = r1.json()["bountyId"]

    # simulate kill
    k1 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                       json={"target_sid": tgt["sid"]}, timeout=15)
    assert k1.status_code == 200, k1.text
    assert k1.json().get("ok") is True

    # board no longer shows this target with a total
    board = requests.get(f"{API}/bounty/board", timeout=10).json()["board"]
    still = next((c for c in board["contracts"] if str(c["targetId"]) == str(tgt["sid"])), None)
    assert (still is None) or (still["reward"]["primeMeat"] == 0)

    # call again -> must NOT create a second completion
    k2 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                       json={"target_sid": tgt["sid"]}, timeout=15)
    assert k2.status_code == 200

    # history contains this bountyId exactly once as completed with a killerName
    hist = requests.get(f"{API}/bounty/history?limit=60", timeout=10).json()
    items = hist.get("items") or []
    matches = [i for i in items if i.get("bountyId") == bid]
    assert len(matches) == 1, f"expected 1 history entry for {bid}, got {len(matches)}"
    entry = matches[0]
    assert entry["status"] == "completed"
    assert entry.get("killerName")


# ── self-bounty ──────────────────────────────────────────────────────
def test_self_bounty_start_and_limit(auth_headers):
    # ensure clean
    mine = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
    if mine.get("self"):
        # kill it via admin simulate-kill on holder sid
        holder_sid = mine["self"]["targetId"]
        requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                      json={"target_sid": holder_sid}, timeout=15)

    r = requests.post(f"{API}/bounty/self/start", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["type"] == "self"
    assert s["status"] == "active"
    assert s.get("primePerMin") == 5000
    assert s.get("endsAt") and s["endsAt"] > int(time.time() * 1000)
    holder_sid = s["targetId"]

    # mine reflects it
    mine2 = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
    assert mine2.get("self") is not None
    assert mine2["self"]["bountyId"] == s["bountyId"]

    # board includes self entry
    board = requests.get(f"{API}/bounty/board", timeout=10).json()["board"]
    self_entries = board.get("self", [])
    assert any(x["bountyId"] == s["bountyId"] for x in self_entries)

    # second attempt -> 400
    r2 = requests.post(f"{API}/bounty/self/start", headers=auth_headers, timeout=10)
    assert r2.status_code == 400
    msg = str((r2.json() or {}).get("detail") or "")
    assert "auto-bounty" in msg.lower() or "ya tienes" in msg.lower()


def test_self_bounty_kill_awards_amber_and_appears_in_history(auth_headers):
    # ensure a self bounty is active for demo user
    mine = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
    if not mine.get("self"):
        r = requests.post(f"{API}/bounty/self/start", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        holder_sid = r.json()["targetId"]
        bid = r.json()["bountyId"]
    else:
        holder_sid = mine["self"]["targetId"]
        bid = mine["self"]["bountyId"]

    # simulate kill
    k = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                      json={"target_sid": holder_sid}, timeout=15)
    assert k.status_code == 200, k.text

    # mine.self is None now
    mine2 = requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()
    assert mine2.get("self") is None

    # history contains type=self entry for this bountyId
    hist = requests.get(f"{API}/bounty/history?limit=60", timeout=10).json()
    items = hist.get("items") or []
    match = next((i for i in items if i.get("bountyId") == bid), None)
    assert match is not None, f"self bounty {bid} not in history"
    assert match["type"] == "self"
    assert match["status"] in ("dead", "expired")


# ── websocket ────────────────────────────────────────────────────────
def test_bounty_ws_state_and_ping():
    parsed = urlparse(BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}/api/bounty/ws"
    ws = websocket.create_connection(ws_url, timeout=15)
    try:
        first = ws.recv()
        data = json.loads(first)
        assert data.get("event") == "bounty:state"
        d = data.get("data") or {}
        assert "config" in d and "board" in d and "paused" in d
        ws.send("ping")
        pong = None
        for _ in range(5):
            try:
                msg = ws.recv()
            except Exception:
                break
            if isinstance(msg, str) and msg.strip() == "pong":
                pong = "pong"
                break
        assert pong == "pong"
    finally:
        ws.close()


def test_bounty_ws_broadcast_on_place(auth_headers):
    parsed = urlparse(BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}/api/bounty/ws"
    ws = websocket.create_connection(ws_url, timeout=15)
    try:
        ws.recv()  # initial bounty:state
        ws.settimeout(10)
        # place a contract
        tgt = _pick_target(auth_headers)
        r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                          json={"target_sid": tgt["sid"], "prime": 20000, "amber": 0}, timeout=15)
        assert r.status_code == 200, r.text
        bid = r.json()["bountyId"]
        got_board_or_new = False
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                msg = ws.recv()
            except Exception:
                break
            try:
                j = json.loads(msg)
            except Exception:
                continue
            ev = j.get("event")
            if ev in ("bounty:board", "bounty:contract_new"):
                got_board_or_new = True
                break
        # cleanup
        requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                      json={"bounty_id": bid}, timeout=10)
        assert got_board_or_new, "expected WS to receive bounty:contract_new or bounty:board"
    finally:
        try:
            ws.close()
        except Exception:
            pass
