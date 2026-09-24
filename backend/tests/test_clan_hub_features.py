"""Tests for Clan Hub new feature batch (iteration 10):
- /api/clans/me (members with status_text, level, contribution, kills; clan.announcement, territories, wins)
- /api/clans/insights (achievements, missions, leaderboard)
- /api/clans/turf-history
- /api/clans/announcement (leader-only set)
- /api/clans/react (toggle reaction on chat message)
- /api/clans/chat (send message)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synced-animations.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


class TestClanMe:
    def test_me_has_new_fields(self, client):
        r = client.get(f"{BASE_URL}/api/clans/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        clan = d["clan"]
        assert clan.get("tag") == "TEST"
        # New required fields
        assert "announcement" in clan
        assert "wins" in clan
        assert clan.get("territories") == 3 or "territories" in clan
        members = d["members"]
        assert isinstance(members, list) and len(members) >= 1
        # Every member should include status_text, level, contribution, kills
        keys = {"status_text", "level", "contribution", "kills"}
        for m in members:
            missing = keys - set(m.keys())
            assert not missing, f"member missing keys {missing}: {m}"


class TestInsights:
    def test_insights_shape(self, client):
        r = client.get(f"{BASE_URL}/api/clans/insights", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "achievements" in d and isinstance(d["achievements"], list) and len(d["achievements"]) >= 5
        for a in d["achievements"]:
            for k in ("id", "title", "value", "goal"):
                assert k in a
        assert "missions" in d and len(d["missions"]) >= 1
        assert "leaderboard" in d and isinstance(d["leaderboard"], list)
        for lb in d["leaderboard"]:
            for k in ("user_id", "name", "contribution", "kills", "level"):
                assert k in lb


class TestTurfHistory:
    def test_turf_history(self, client):
        r = client.get(f"{BASE_URL}/api/clans/turf-history", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "events" in d and isinstance(d["events"], list)


class TestAnnouncement:
    def test_set_announcement_and_persist(self, client):
        text = f"TEST_ANNOUNCE {int(time.time())}"
        r = client.post(f"{BASE_URL}/api/clans/announcement", json={"text": text}, timeout=15)
        assert r.status_code == 200, r.text
        # Persist check via /me
        r2 = client.get(f"{BASE_URL}/api/clans/me", timeout=15)
        assert r2.json()["clan"]["announcement"] == text

    def test_clear_announcement(self, client):
        r = client.post(f"{BASE_URL}/api/clans/announcement", json={"text": ""}, timeout=15)
        assert r.status_code == 200


class TestReactAndChat:
    def test_send_chat_then_react_toggle(self, client):
        # Send a chat message
        text = f"TEST_CHAT_{int(time.time())}"
        r = client.post(f"{BASE_URL}/api/clans/chat", json={"text": text, "channel": "clan"}, timeout=15)
        assert r.status_code == 200, r.text

        # Read history to get message id
        h = client.get(f"{BASE_URL}/api/clans/chat", timeout=15)
        assert h.status_code == 200, h.text
        msgs = h.json()["messages"]
        mine = [m for m in msgs if m.get("text") == text]
        assert mine, f"just-sent message not in history"
        mid = mine[-1]["id"]

        # React (add)
        r = client.post(f"{BASE_URL}/api/clans/react", json={"message_id": mid, "emoji": "🔥"}, timeout=15)
        assert r.status_code == 200, r.text
        reactions = r.json().get("reactions") or {}
        assert "🔥" in reactions and len(reactions["🔥"]) == 1

        # Toggle off
        r = client.post(f"{BASE_URL}/api/clans/react", json={"message_id": mid, "emoji": "🔥"}, timeout=15)
        assert r.status_code == 200
        reactions = r.json().get("reactions") or {}
        assert "🔥" not in reactions

    def test_react_bad_message_id(self, client):
        r = client.post(f"{BASE_URL}/api/clans/react", json={"message_id": "nonexistent", "emoji": "👍"}, timeout=15)
        assert r.status_code == 404
