"""Clan Hub redesign backend tests: level/xp, code, territories, language, clan_type,
online_count, sent_invites, join_requests, player search, invite cancel, request accept/decline."""
import os, uuid, pytest, requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/demo")
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def _ensure_clan(H):
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    if me.get("clan"):
        return me
    tag = "H" + uuid.uuid4().hex[:3].upper()
    name = f"TEST_HUB_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/api/clans/found", headers=H,
                      json={"name": name, "tag": tag, "color": "#22c55e"})
    assert r.status_code == 200, r.text
    return requests.get(f"{BASE}/api/clans/me", headers=H).json()


# ── /me payload shape ─────────────────────────────────────────
def test_me_payload_hub_fields(H):
    me = _ensure_clan(H)
    c = me["clan"]
    for k in ("level", "xp_into", "xp_needed", "code", "territories", "language", "clan_type"):
        assert k in c, f"missing field {k}"
    assert isinstance(c["level"], int) and c["level"] >= 1
    assert isinstance(c["xp_into"], int)
    assert isinstance(c["xp_needed"], int) and c["xp_needed"] > 0
    assert c["code"].startswith("#") and len(c["code"]) == 5
    assert isinstance(c["territories"], int)
    assert "online_count" in me and isinstance(me["online_count"], int)
    # leader-only fields
    assert me.get("is_leader") is True
    assert isinstance(me.get("sent_invites"), list)
    assert isinstance(me.get("join_requests"), list)


# ── players search ────────────────────────────────────────────
def test_players_search_shape(H):
    _ensure_clan(H)
    r = requests.get(f"{BASE}/api/clans/players/search?q=", headers=H)
    assert r.status_code == 200
    players = r.json().get("players", [])
    assert isinstance(players, list)
    if players:
        p = players[0]
        for k in ("id", "name", "level", "status", "in_clan", "invited"):
            assert k in p, f"missing key {k}"


def test_players_search_query(H):
    _ensure_clan(H)
    r = requests.get(f"{BASE}/api/clans/players/search?q=demo", headers=H)
    assert r.status_code == 200


# ── invite via search + cancel invite ─────────────────────────
def test_invite_and_cancel_flow(H):
    me = _ensure_clan(H)
    # Find an eligible player
    r = requests.get(f"{BASE}/api/clans/players/search?q=", headers=H)
    players = [p for p in r.json().get("players", []) if not p["in_clan"] and not p["invited"]]
    if not players:
        pytest.skip("No eligible player to invite")
    target = players[0]
    r2 = requests.post(f"{BASE}/api/clans/invite", headers=H, json={"user_id": target["id"]})
    assert r2.status_code == 200, r2.text
    # sent_invites should contain the target
    me2 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    invited_ids = [i["user_id"] for i in (me2.get("sent_invites") or [])]
    assert target["id"] in invited_ids
    # cancel
    r3 = requests.post(f"{BASE}/api/clans/invite/cancel", headers=H, json={"user_id": target["id"]})
    assert r3.status_code == 200
    me3 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    invited_ids2 = [i["user_id"] for i in (me3.get("sent_invites") or [])]
    assert target["id"] not in invited_ids2


# ── request join (leader trying to self-request) ──────────────
def test_request_join_when_in_clan_returns_409(H):
    _ensure_clan(H)
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    clan_id = me["clan"]["id"]
    r = requests.post(f"{BASE}/api/clans/request", headers=H, json={"clan_id": clan_id})
    assert r.status_code == 409


# ── request accept/decline via DB seeded request ──────────────
def test_request_accept_flow(H):
    """Seed a clan_requests doc via a second demo-style user, then accept."""
    _ensure_clan(H)
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    clan_id = me["clan"]["id"]

    # Find a non-clan user to be the requester
    r = requests.get(f"{BASE}/api/clans/players/search?q=", headers=H)
    players = [p for p in r.json().get("players", []) if not p["in_clan"]]
    if not players:
        pytest.skip("No non-clan player available")
    requester = players[0]

    # Insert request directly via mongo (test-only) using pymongo
    from pymongo import MongoClient
    mc = MongoClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    db.clan_requests.delete_many({"user_id": requester["id"]})
    db.clan_requests.insert_one({
        "id": uuid.uuid4().hex, "clan_id": clan_id, "user_id": requester["id"],
        "name": requester["name"], "avatar": requester.get("avatar"),
        "created_at": "2026-01-01T00:00:00+00:00",
    })

    # Verify shows up in /me
    me2 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    req_ids = [x["user_id"] for x in (me2.get("join_requests") or [])]
    assert requester["id"] in req_ids

    # Accept
    r2 = requests.post(f"{BASE}/api/clans/request/accept", headers=H,
                      json={"user_id": requester["id"]})
    assert r2.status_code == 200, r2.text

    # Requester should now be a member
    me3 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    mem_ids = [m["user_id"] for m in me3.get("members", [])]
    assert requester["id"] in mem_ids
    req_ids2 = [x["user_id"] for x in (me3.get("join_requests") or [])]
    assert requester["id"] not in req_ids2

    # Cleanup: kick to restore state
    requests.post(f"{BASE}/api/clans/kick", headers=H, json={"user_id": requester["id"]})


def test_request_decline_flow(H):
    _ensure_clan(H)
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    clan_id = me["clan"]["id"]
    r = requests.get(f"{BASE}/api/clans/players/search?q=", headers=H)
    players = [p for p in r.json().get("players", []) if not p["in_clan"]]
    if not players:
        pytest.skip("No non-clan player available")
    requester = players[0]

    from pymongo import MongoClient
    mc = MongoClient(os.environ["MONGO_URL"])
    db = mc[os.environ["DB_NAME"]]
    db.clan_requests.delete_many({"user_id": requester["id"]})
    db.clan_requests.insert_one({
        "id": uuid.uuid4().hex, "clan_id": clan_id, "user_id": requester["id"],
        "name": requester["name"], "avatar": requester.get("avatar"),
        "created_at": "2026-01-01T00:00:00+00:00",
    })

    r2 = requests.post(f"{BASE}/api/clans/request/decline", headers=H,
                     json={"user_id": requester["id"]})
    assert r2.status_code == 200

    me3 = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    req_ids = [x["user_id"] for x in (me3.get("join_requests") or [])]
    assert requester["id"] not in req_ids


def test_request_accept_not_found(H):
    _ensure_clan(H)
    r = requests.post(f"{BASE}/api/clans/request/accept", headers=H,
                    json={"user_id": "nonexistent_user_id_xyz"})
    assert r.status_code == 404


# ── edit language / clan_type ─────────────────────────────────
def test_edit_language_and_type(H):
    _ensure_clan(H)
    r = requests.post(f"{BASE}/api/clans/edit", headers=H,
                    json={"language": "Portugués", "clan_type": "PvE / Cooperativo"})
    assert r.status_code == 200
    me = requests.get(f"{BASE}/api/clans/me", headers=H).json()
    assert me["clan"]["language"] == "Portugués"
    assert me["clan"]["clan_type"] == "PvE / Cooperativo"


def test_edit_bad_tag_length(H):
    _ensure_clan(H)
    r = requests.post(f"{BASE}/api/clans/edit", headers=H, json={"tag": "AB"})
    assert r.status_code == 400


# ── chat global channel ───────────────────────────────────────
def test_chat_global_channel(H):
    _ensure_clan(H)
    r = requests.post(f"{BASE}/api/clans/chat", headers=H,
                    json={"text": "hola global", "channel": "global"})
    assert r.status_code == 200
    hist = requests.get(f"{BASE}/api/clans/chat?channel=global&limit=20", headers=H).json()
    assert any(m.get("text") == "hola global" for m in hist["messages"])
