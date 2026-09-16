"""Backend tests for player-placed bounty system (Sistema Global de Bounties).

Covers: anti-exploit rules, atomic charging, minimum, self-target block,
system-injected amber bonus, 3-active limit, offline target, cancel/refund,
idempotent kill completion, self-bounty start+limit, WS state+broadcast,
history contents, and admin protection on /bounty/admin/*.
"""
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


def _mine(auth_headers):
    return requests.get(f"{API}/bounty/mine", headers=auth_headers, timeout=10).json()


def _wallet(auth_headers):
    m = _mine(auth_headers)
    w = m.get("wallet") or {}
    return int(w.get("coins", 0)), int(w.get("vip_coins", 0))


def _cancel_all_mine(auth_headers):
    try:
        m = _mine(auth_headers)
        for c in m.get("contracts") or []:
            requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                          json={"bounty_id": c["bountyId"]}, timeout=10)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _cleanup_between_tests(auth_headers):
    _cancel_all_mine(auth_headers)
    yield
    _cancel_all_mine(auth_headers)


def _targets(auth_headers):
    r = requests.get(f"{API}/bounty/targets", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def _pick_targets(auth_headers, n=1, exclude=()):
    excl = set(str(x) for x in exclude)
    out = []
    for t in _targets(auth_headers)["targets"]:
        if t["isMe"]:
            continue
        if str(t["sid"]) in excl:
            continue
        out.append(t)
        if len(out) >= n:
            break
    return out


# ── config ───────────────────────────────────────────────────────────
def test_bounty_config_defaults():
    r = requests.get(f"{API}/bounty/config", timeout=10)
    assert r.status_code == 200
    cfg = r.json()
    expected = {
        "min_contract_prime": 20000,
        "reward_amber_bonus": 100,
        "max_contracts_per_user": 3,
        "self_prime_per_min": 5000,
        "self_killer_amber": 300,
    }
    for k, v in expected.items():
        assert cfg.get(k) == v, f"config[{k}] expected {v}, got {cfg.get(k)}"


# ── targets shape (roster simulated in preview) ──────────────────────
def test_targets_simulated_and_shape(auth_headers):
    j = _targets(auth_headers)
    assert j.get("simulated") is True
    assert isinstance(j["targets"], list) and len(j["targets"]) >= 10
    t0 = j["targets"][0]
    for k in ("sid", "name", "species", "slug", "alive", "isMe", "bounty"):
        assert k in t0


# ── ANTI-EXPLOIT: atomic charge (only PrimeMeat, not vip_coins) ──────
def test_place_contract_charges_only_prime_and_not_vip(auth_headers):
    coins_b, vip_b = _wallet(auth_headers)
    assert coins_b >= 20000, "demo needs >=20000 PrimeMeat"
    tgt = _pick_targets(auth_headers, 1)[0]

    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 25000, "amber": 999_999},
                      timeout=15)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["type"] == "contract" and b["status"] == "active"
    assert str(b["targetId"]) == str(tgt["sid"])
    # ANTI-EXPLOIT amber injected by system: system uses reward_amber_bonus (100), NOT the request's 999_999
    assert b["reward"]["primeMeat"] == 25000
    assert b["reward"]["amberium"] == 100, f"amber must be system-injected 100, got {b['reward']['amberium']}"

    coins_a, vip_a = _wallet(auth_headers)
    assert coins_a == coins_b - 25000, f"coins {coins_b}->{coins_a} expected -25000"
    assert vip_a == vip_b, f"vip_coins must NOT change (was {vip_b}, now {vip_a})"


# ── ANTI-EXPLOIT: insufficient funds ─────────────────────────────────
def test_insufficient_funds_no_charge(auth_headers):
    coins_b, vip_b = _wallet(auth_headers)
    tgt = _pick_targets(auth_headers, 1)[0]
    absurd = coins_b + 10_000_000
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": absurd, "amber": 0}, timeout=15)
    assert r.status_code == 400
    coins_a, vip_a = _wallet(auth_headers)
    assert coins_a == coins_b and vip_a == vip_b


# ── ANTI-EXPLOIT: minimum ────────────────────────────────────────────
def test_minimum_prime_rejected(auth_headers):
    tgt = _pick_targets(auth_headers, 1)[0]
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 100, "amber": 0}, timeout=10)
    assert r.status_code == 400
    msg = str((r.json() or {}).get("detail") or "").lower()
    assert "20000" in msg or "mínimo" in msg or "minimo" in msg


# ── ANTI-EXPLOIT: cannot target self ─────────────────────────────────
def test_cannot_target_self(auth_headers):
    # demo user's steam_id
    me = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=10).json()
    my_sid = str(me.get("steam_id") or "demo_0000000001")
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": my_sid, "prime": 20000, "amber": 0}, timeout=10)
    assert r.status_code == 400, f"expected 400 on self-target, got {r.status_code} {r.text}"


# ── ANTI-EXPLOIT: offline / not-in-roster target ─────────────────────
def test_offline_target_rejected(auth_headers):
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": "99999999999999999", "prime": 20000, "amber": 0},
                      timeout=10)
    assert r.status_code == 400


# ── ANTI-EXPLOIT: 3-active limit, 4th rejected ───────────────────────
def test_three_contracts_allowed_fourth_rejected(auth_headers):
    tgts = _pick_targets(auth_headers, 4)
    assert len(tgts) >= 4, "need 4 sim targets"
    coins_b, _ = _wallet(auth_headers)
    placed = []
    try:
        for t in tgts[:3]:
            r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                              json={"target_sid": t["sid"], "prime": 20000, "amber": 0}, timeout=15)
            assert r.status_code == 200, f"place failed for {t['sid']}: {r.text}"
            placed.append(r.json()["bountyId"])
        # 4th must fail
        r4 = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                           json={"target_sid": tgts[3]["sid"], "prime": 20000, "amber": 0}, timeout=15)
        assert r4.status_code == 400, f"4th expected 400, got {r4.status_code} {r4.text}"
        coins_a, _ = _wallet(auth_headers)
        # exactly 3*20000 debited
        assert coins_a == coins_b - 60000, f"expected -60000 coins, got {coins_b - coins_a}"
        # mine reports 3 active
        mine = _mine(auth_headers)
        assert len(mine.get("contracts") or []) == 3
    finally:
        for bid in placed:
            requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                          json={"bounty_id": bid}, timeout=10)


# ── Cancel refunds; wrong id 404 ─────────────────────────────────────
def test_cancel_refunds_and_wrong_id_404(auth_headers):
    coins_b, _ = _wallet(auth_headers)
    tgt = _pick_targets(auth_headers, 1)[0]
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 30000, "amber": 0}, timeout=15)
    assert r.status_code == 200
    bid = r.json()["bountyId"]

    # invalid id -> 404
    r_bad = requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                          json={"bounty_id": "BNT-DOESNOTEXIST"}, timeout=10)
    assert r_bad.status_code in (400, 404)

    rc = requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                       json={"bounty_id": bid}, timeout=10)
    assert rc.status_code == 200 and rc.json().get("ok") is True
    coins_a, _ = _wallet(auth_headers)
    assert coins_a == coins_b, f"refund must restore coins ({coins_b}) got {coins_a}"


# ── Kill: atomic + idempotent (single history entry, no double state change) ─
def test_simulate_kill_idempotent(auth_headers):
    tgt = _pick_targets(auth_headers, 1)[0]
    r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                      json={"target_sid": tgt["sid"], "prime": 20000, "amber": 0}, timeout=15)
    assert r.status_code == 200
    bid = r.json()["bountyId"]

    k1 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                       json={"target_sid": tgt["sid"]}, timeout=15)
    assert k1.status_code == 200 and k1.json().get("ok") is True

    # call again — must not duplicate rewards or re-change state
    k2 = requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                       json={"target_sid": tgt["sid"]}, timeout=15)
    assert k2.status_code == 200

    hist = requests.get(f"{API}/bounty/history?limit=60", timeout=10).json()
    matches = [i for i in (hist.get("items") or []) if i.get("bountyId") == bid]
    assert len(matches) == 1, f"expected 1 history entry, got {len(matches)}"
    assert matches[0]["status"] == "completed"
    assert matches[0].get("killerName")


# ── Self-bounty start + limit ────────────────────────────────────────
def test_self_bounty_start_and_second_rejected(auth_headers):
    # clear any existing self via simulate-kill
    mine = _mine(auth_headers)
    if mine.get("self"):
        requests.post(f"{API}/bounty/admin/simulate-kill", headers=auth_headers,
                      json={"target_sid": mine["self"]["targetId"]}, timeout=15)

    r = requests.post(f"{API}/bounty/self/start", headers=auth_headers, timeout=15)
    # If cooldown from previous test kicks in, accept 400 and skip rest
    if r.status_code == 400 and "esperar" in str(r.text).lower():
        pytest.skip("self cooldown active from prior test")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["type"] == "self" and s["status"] == "active"
    assert s.get("primePerMin") == 5000

    mine2 = _mine(auth_headers)
    assert mine2.get("self") and mine2["self"]["bountyId"] == s["bountyId"]

    r2 = requests.post(f"{API}/bounty/self/start", headers=auth_headers, timeout=10)
    assert r2.status_code == 400


# ── History contents ─────────────────────────────────────────────────
def test_history_shape(auth_headers):
    hist = requests.get(f"{API}/bounty/history?limit=20", timeout=10).json()
    assert isinstance(hist.get("items"), list)
    for it in hist["items"]:
        assert it.get("status") in ("completed", "dead", "expired", "cancelled")


# ── Admin endpoints require admin auth ───────────────────────────────
def test_admin_endpoints_require_auth():
    r = requests.post(f"{API}/bounty/admin/simulate-kill", json={"target_sid": "1"}, timeout=10)
    assert r.status_code in (401, 403), r.status_code
    r2 = requests.post(f"{API}/bounty/admin/config", json={}, timeout=10)
    assert r2.status_code in (401, 403), r2.status_code


def test_admin_config_works_for_admin(auth_headers):
    r = requests.post(f"{API}/bounty/admin/config", headers=auth_headers,
                      json={"reward_amber_bonus": 100}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ── WebSocket ────────────────────────────────────────────────────────
def _ws_url(with_token=None):
    parsed = urlparse(BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    u = f"{scheme}://{parsed.netloc}/api/bounty/ws"
    if with_token:
        u += f"?token={with_token}"
    return u


def test_ws_initial_state_snapshot(admin_token):
    ws = websocket.create_connection(_ws_url(admin_token), timeout=15)
    try:
        first = json.loads(ws.recv())
        assert first.get("event") == "bounty:state"
        d = first.get("data") or {}
        assert "config" in d and "board" in d
    finally:
        ws.close()


def test_ws_broadcast_on_place(auth_headers, admin_token):
    ws = websocket.create_connection(_ws_url(admin_token), timeout=15)
    try:
        ws.recv()  # initial bounty:state
        ws.settimeout(10)
        tgt = _pick_targets(auth_headers, 1)[0]
        r = requests.post(f"{API}/bounty/contract", headers=auth_headers,
                          json={"target_sid": tgt["sid"], "prime": 20000, "amber": 0}, timeout=15)
        assert r.status_code == 200, r.text
        bid = r.json()["bountyId"]
        got = False
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
            if j.get("event") in ("bounty:board", "bounty:contract_new"):
                got = True
                break
        requests.post(f"{API}/bounty/contract/cancel", headers=auth_headers,
                      json={"bounty_id": bid}, timeout=10)
        assert got, "WS did not deliver bounty:contract_new or bounty:board"
    finally:
        try:
            ws.close()
        except Exception:
            pass
