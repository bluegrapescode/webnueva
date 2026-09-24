"""Turf Wars — Phase 2 backend tests.

Covers:
  - GET /api/turf/state shape (zones, leaderboard, my_clan_id/my_rally, config)
  - simulation progresses (state changes over time)
  - POST /api/turf/rally requires clan / 429 on double / posts system message
  - capture announcements land in clan chat
  - admin endpoints (settings PUT, capture, reset)
  - clan tag rule (must be exactly 4 chars) + uniqueness
"""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


# ─── fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/demo")
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def _disband(H):
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    if me.get("clan"):
        requests.post(f"{BASE}/api/clans/disband", headers=H)


def _found(H, name=None, tag=None, color="#38BDF8"):
    _disband(H)
    name = name or f"TEST_{uuid.uuid4().hex[:8]}"
    tag = tag or uuid.uuid4().hex[:4].upper()
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": name, "tag": tag, "color": color, "description": "test"},
    )
    return r, name, tag


# ─── /api/turf/state shape ───────────────────────────────────────────────
def test_state_shape(H):
    r = requests.get(f"{BASE}/api/turf/state", headers=H)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get("zones"), list) and len(d["zones"]) == 10
    for z in d["zones"]:
        assert {"id", "name", "x", "y"}.issubset(z.keys())
        assert "owner" in z and "contest" in z
        if z["owner"]:
            assert {"id", "name", "tag", "color"}.issubset(z["owner"].keys())
        if z["contest"]:
            assert {"tag", "color", "progress"}.issubset(z["contest"].keys())
    assert isinstance(d.get("leaderboard"), list)
    assert "my_clan_id" in d and "my_rally" in d
    assert "capture_seconds" in d.get("config", {})


def test_state_config_endpoint(H):
    r = requests.get(f"{BASE}/api/turf/config", headers=H)
    assert r.status_code == 200
    for k in ("capture_seconds", "rally_seconds", "min_presence"):
        assert k in r.json()


# ─── simulation progresses ───────────────────────────────────────────────
def test_simulation_progresses(H):
    """Two /state calls with a gap should show at least SOME change
    (owner change, contest progress, or leaderboard notoriety diff)."""
    a = requests.get(f"{BASE}/api/turf/state", headers=H).json()
    time.sleep(35)
    b = requests.get(f"{BASE}/api/turf/state", headers=H).json()
    # Compare zone owner+contest signatures.
    sig = lambda st: [(z["id"], (z["owner"] or {}).get("id"), (z["contest"] or {}).get("progress")) for z in st["zones"]]
    changed = sig(a) != sig(b)
    # Or leaderboard notoriety changed.
    noto_a = {c["id"]: c["notoriety"] for c in a["leaderboard"]}
    noto_b = {c["id"]: c["notoriety"] for c in b["leaderboard"]}
    if not changed:
        changed = noto_a != noto_b
    assert changed, "Turf simulation appears frozen (no state change over 35s)."


# ─── rally: 404 without clan, 200 with clan, 429 on duplicate ────────────
def test_rally_requires_clan(H):
    _disband(H)
    r = requests.post(f"{BASE}/api/turf/rally", headers=H, json={"zone_id": "north_plains"})
    assert r.status_code == 404


def test_rally_success_and_429_and_chat(H):
    fr, _, _ = _found(H)
    if fr.status_code == 402:
        pytest.skip("Not enough currency to found a clan for rally test")
    assert fr.status_code == 200, fr.text

    z = "highland"
    r1 = requests.post(f"{BASE}/api/turf/rally", headers=H, json={"zone_id": z})
    assert r1.status_code == 200, r1.text
    assert r1.json().get("success") is True
    assert isinstance(r1.json().get("seconds"), int)

    r2 = requests.post(f"{BASE}/api/turf/rally", headers=H, json={"zone_id": z})
    assert r2.status_code == 429, r2.text

    # verify my_rally shows in state
    st = requests.get(f"{BASE}/api/turf/state", headers=H).json()
    assert st.get("my_rally") and st["my_rally"]["zone_id"] == z

    # verify system chat message posted
    time.sleep(1)
    ch = requests.get(f"{BASE}/api/clans/chat", headers=H)
    assert ch.status_code == 200
    msgs = ch.json().get("messages") or ch.json()
    if isinstance(msgs, dict) and "messages" in msgs:
        msgs = msgs["messages"]
    txts = " ".join((m.get("text") or "") for m in msgs)
    assert "Rally" in txts or "rally" in txts.lower(), f"No rally system msg found: {txts[:400]}"


def test_rally_bad_zone(H):
    # clan still exists from previous test
    r = requests.post(f"{BASE}/api/turf/rally", headers=H, json={"zone_id": "does_not_exist"})
    # 429 if rally is still active from previous test, else 404
    assert r.status_code in (404, 429)


# ─── admin endpoints ──────────────────────────────────────────────────────
def test_admin_settings_get_put(H):
    r = requests.get(f"{BASE}/api/turf/admin/settings", headers=H)
    assert r.status_code == 200, r.text
    cur = r.json()
    new_val = int(cur.get("min_presence", 1))
    r2 = requests.put(
        f"{BASE}/api/turf/admin/settings",
        headers=H,
        json={"min_presence": new_val},
    )
    assert r2.status_code == 200
    assert r2.json()["success"] is True


def test_admin_capture_and_reset(H):
    # ensure demo has a clan
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    if not me.get("clan"):
        fr, _, _ = _found(H)
        if fr.status_code != 200:
            pytest.skip("Cannot found clan for admin capture test")
        me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    my_clan_id = me["clan"]["id"]

    # Force-capture a zone
    r = requests.post(
        f"{BASE}/api/turf/admin/capture",
        headers=H,
        json={"zone_id": "the_pit", "clan_id": my_clan_id},
    )
    assert r.status_code == 200, r.text

    # Verify zone owner
    st = requests.get(f"{BASE}/api/turf/state", headers=H).json()
    the_pit = next(z for z in st["zones"] if z["id"] == "the_pit")
    assert the_pit["owner"] and the_pit["owner"]["id"] == my_clan_id

    # Verify capture chat message
    time.sleep(1)
    ch = requests.get(f"{BASE}/api/clans/chat", headers=H).json()
    msgs = ch.get("messages") or ch
    if isinstance(msgs, dict) and "messages" in msgs:
        msgs = msgs["messages"]
    txts = " ".join((m.get("text") or "") for m in msgs)
    assert "Capturamos" in txts or "captur" in txts.lower(), f"No capture msg: {txts[:400]}"

    # Reset
    r2 = requests.post(f"{BASE}/api/turf/admin/reset", headers=H)
    assert r2.status_code == 200
    st2 = requests.get(f"{BASE}/api/turf/state", headers=H).json()
    for z in st2["zones"]:
        assert z["owner"] is None
        assert z["contest"] is None


def test_admin_capture_bad_zone(H):
    r = requests.post(
        f"{BASE}/api/turf/admin/capture",
        headers=H,
        json={"zone_id": "nope", "clan_id": "nope"},
    )
    assert r.status_code == 404


# ─── clan tag rule (Phase 2 change: exactly 4 chars) ────────────────────
def test_tag_length_3_rejected(H):
    _disband(H)
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": f"TEST_{uuid.uuid4().hex[:6]}", "tag": "ABC", "color": "#22C55E"},
    )
    assert r.status_code == 400
    assert "4" in (r.json().get("detail") or "")


def test_tag_length_5_rejected(H):
    _disband(H)
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": f"TEST_{uuid.uuid4().hex[:6]}", "tag": "ABCDE", "color": "#22C55E"},
    )
    assert r.status_code == 400


def test_tag_length_4_success(H):
    _disband(H)
    tag = uuid.uuid4().hex[:4].upper()
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": f"TEST_{uuid.uuid4().hex[:6]}", "tag": tag, "color": "#22C55E"},
    )
    if r.status_code == 402:
        pytest.skip("Insufficient currency")
    assert r.status_code == 200, r.text


def test_tag_uniqueness_conflict(H):
    """Founding a clan with the SAME tag as an existing one → 409."""
    _disband(H)
    # Use a rival seeded tag which is guaranteed to exist.
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": f"TEST_{uuid.uuid4().hex[:6]}", "tag": "ALBA", "color": "#22C55E"},
    )
    assert r.status_code == 409, r.text


def test_name_too_short(H):
    _disband(H)
    r = requests.post(
        f"{BASE}/api/clans/found",
        headers=H,
        json={"name": "AB", "tag": "ZZZZ", "color": "#22C55E"},
    )
    assert r.status_code == 400


# ─── final cleanup ───────────────────────────────────────────────────────
def test_zzz_cleanup(H):
    _disband(H)
