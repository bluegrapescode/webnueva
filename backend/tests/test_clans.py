"""Clan system backend tests (Phase 1)."""
import os, uuid, pytest, requests, time

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/demo")
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def _cleanup(H):
    # if user has clan, disband
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    if me.get("clan"):
        requests.post(f"{BASE}/api/clans/disband", headers=H)


# ── Config / directory / me ──
def test_config(H):
    r = requests.get(f"{BASE}/api/clans/config", headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d["founding_currency"] in ("amberium", "primemeat")
    assert d["founding_cost"] >= 0
    assert d["min_members"] >= 1


def test_me_no_clan_initial(H):
    _cleanup(H)
    r = requests.get(f"{BASE}/api/clans/me", headers=H)
    assert r.status_code == 200
    assert r.json().get("clan") is None


def test_directory(H):
    r = requests.get(f"{BASE}/api/clans/directory", headers=H)
    assert r.status_code == 200
    assert isinstance(r.json().get("clans"), list)


# ── Found / one-clan-per-player / chat / rank / disband ──
def test_found_flow_and_persistence(H):
    _cleanup(H)
    tag = "T" + uuid.uuid4().hex[:3].upper()
    name = f"TEST_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{BASE}/api/clans/found", headers=H, json={"name": name, "tag": tag, "color": "#22c55e"})
    assert r.status_code == 200, r.text

    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    assert me["clan"]["name"] == name
    assert me["clan"]["tag"] == tag
    assert me["clan"]["member_count"] == 1
    assert me["is_leader"] is True
    assert me["clan"]["active"] is False  # <20 members

    # one clan per player
    r2 = requests.post(f"{BASE}/api/clans/found", headers=H, json={"name": name + "x", "tag": "AA", "color": "#fff"})
    assert r2.status_code == 409

    # edit
    r3 = requests.post(f"{BASE}/api/clans/edit", headers=H, json={"color": "#ff00ff", "description": "test"})
    assert r3.status_code == 200
    me2 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    assert me2["clan"]["color"] == "#ff00ff"
    assert me2["clan"]["description"] == "test"

    # rank create
    r4 = requests.post(f"{BASE}/api/clans/ranks", headers=H, json={"name": "Veterano", "order": 3, "perms": {"invite": True}})
    assert r4.status_code == 200
    me3 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    assert any(rk["name"] == "Veterano" for rk in me3["clan"]["ranks"])

    # chat send + persistence
    r5 = requests.post(f"{BASE}/api/clans/chat", headers=H, json={"text": "hola manada"})
    assert r5.status_code == 200
    time.sleep(0.3)
    hist = requests.get(f"{BASE}/api/clans/chat?limit=50", headers=H).json()
    assert any(m.get("text") == "hola manada" for m in hist["messages"])

    # invite (unknown target -> 404)
    r6 = requests.post(f"{BASE}/api/clans/invite", headers=H, json={"name": "Survivor_9945"})
    assert r6.status_code in (200, 404)

    # disband
    r7 = requests.post(f"{BASE}/api/clans/disband", headers=H)
    assert r7.status_code == 200
    me4 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    assert me4.get("clan") is None


# ── Insufficient funds ──
def test_insufficient_funds(H):
    # temporarily bump cost via admin
    _cleanup(H)
    s = requests.get(f"{BASE}/api/clans/admin/settings", headers=H).json()
    orig_cost = s["founding_cost"]
    try:
        requests.put(f"{BASE}/api/clans/admin/settings", headers=H, json={"founding_cost": 999999999})
        r = requests.post(f"{BASE}/api/clans/found", headers=H, json={"name": f"TEST_{uuid.uuid4().hex[:6]}", "tag": "ZZ99", "color": "#000"})
        assert r.status_code == 402
    finally:
        requests.put(f"{BASE}/api/clans/admin/settings", headers=H, json={"founding_cost": orig_cost})


# ── Admin settings ──
def test_admin_settings_update(H):
    r = requests.get(f"{BASE}/api/clans/admin/settings", headers=H)
    assert r.status_code == 200
    orig = r.json()
    try:
        r2 = requests.put(f"{BASE}/api/clans/admin/settings", headers=H,
                          json={"founding_currency": "primemeat", "founding_cost": 5000, "min_members": 15, "creation_enabled": True})
        assert r2.status_code == 200
        data = r2.json()["settings"]
        assert data["founding_currency"] == "primemeat"
        assert data["founding_cost"] == 5000
        assert data["min_members"] == 15
    finally:
        requests.put(f"{BASE}/api/clans/admin/settings", headers=H,
                     json={"founding_currency": orig["founding_currency"], "founding_cost": orig["founding_cost"],
                           "min_members": orig["min_members"], "creation_enabled": orig["creation_enabled"]})


def test_admin_list(H):
    r = requests.get(f"{BASE}/api/clans/admin/list", headers=H)
    assert r.status_code == 200
    assert isinstance(r.json().get("clans"), list)
