"""Backend tests for the Live Trade (P2P) feature.

Covers presence via WebSocket, invite/accept/reject, offers, lock reset,
confirm+atomic swap, amber daily cap, cooldown, security (untradeable
categories, insufficient quantities), and cancel.
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta

import jwt
import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synced-animations.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/trade/ws"

A_ID = "3c45966b9bbf4bf59035ebae8237faa4"
B_ID = "96dffc3fe0de4217a969e56f2eec716f"


def _clear_sessions():
    import os
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    db.trade_sessions.delete_many({"$or": [{"a_id": A_ID}, {"b_id": A_ID}, {"a_id": B_ID}, {"b_id": B_ID}]})
    db.users.update_many({"id": {"$in": [A_ID, B_ID]}},
                         {"$unset": {"last_item_trade_at": "", "trade_amber_day": "", "trade_amber_sent": ""}})
    cli.close()


def _reseed():
    _clear_sessions()
    r = subprocess.run(["python3", "/app/backend/_seed_trade_test.py"], capture_output=True, text=True, timeout=60)
    out = r.stdout
    a_tok = b_tok = None
    for line in out.splitlines():
        if line.startswith("A_TOKEN "):
            a_tok = line.split(" ", 1)[1].strip()
        if line.startswith("B_TOKEN "):
            b_tok = line.split(" ", 1)[1].strip()
    return a_tok, b_tok


@pytest.fixture(scope="module")
def tokens():
    a, b = _reseed()
    assert a and b, "seed failed"
    return {"A": a, "B": b}


def H(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ─── WS helper: connect, then hold open in background ─────────────────────
async def _connect_ws(token, hold=8.0):
    """Yields the ws so caller can read invite pushes."""
    url = f"{WS_BASE}?token={token}"
    ws = await websockets.connect(url, open_timeout=10, ping_interval=None)
    return ws


class WSClient:
    """Simple WS client running in a background asyncio task."""
    def __init__(self, token):
        self.token = token
        self.messages = []
        self._ws = None
        self._task = None
        self._loop = None

    def start(self, loop):
        self._loop = loop
        self._task = loop.create_task(self._run())

    async def _run(self):
        url = f"{WS_BASE}?token={self.token}"
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
                self._ws = ws
                async for msg in ws:
                    try:
                        self.messages.append(json.loads(msg))
                    except Exception:
                        self.messages.append({"raw": msg})
        except Exception as e:
            self.messages.append({"error": str(e)})

    async def wait_for(self, mtype, timeout=6.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            for m in self.messages:
                if m.get("type") == mtype:
                    return m
            await asyncio.sleep(0.15)
        return None

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass


# ─── 1. Basic reachability + inventory + amber state ───────────────────────
def test_inventory_excludes_dinosaurs(tokens):
    r = requests.get(f"{API}/trade/inventory", headers=H(tokens["A"]), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data and "amber" in data
    for it in data["items"]:
        assert it["category"] != "Dinosaurs"
    cats = {it["category"] for it in data["items"]}
    # seed adds Eggs+Skins for A
    assert "Eggs" in cats
    assert data["amber"]["daily_cap"] == 1000
    assert data["amber"]["balance"] >= 500


def test_online_endpoint_no_ws(tokens):
    # Without a WS connection, A should not see B online
    r = requests.get(f"{API}/trade/online", headers=H(tokens["A"]), timeout=10)
    assert r.status_code == 200
    ids = [u["user_id"] for u in r.json().get("online", [])]
    # Not asserting emptiness (other agents may connect) — just structural
    assert isinstance(ids, list)


def test_invite_fails_when_target_offline(tokens):
    r = requests.post(f"{API}/trade/invite", headers=H(tokens["A"]),
                      json={"to_user_id": "nonexistent_offline_user_zzz"}, timeout=10)
    assert r.status_code == 400
    assert "línea" in r.json().get("detail", "") or "online" in r.json().get("detail", "").lower()


# ─── 2. Full WS flow: presence, invite, accept, offer, lock, confirm ──────
@pytest.mark.asyncio
async def test_full_trade_flow(tokens):
    a_tok, b_tok = tokens["A"], tokens["B"]
    loop = asyncio.get_event_loop()

    a_ws = WSClient(a_tok); b_ws = WSClient(b_tok)
    a_ws.start(loop); b_ws.start(loop)
    await asyncio.sleep(1.5)  # let presence broadcast

    # Presence: A should see B in online list
    r = requests.get(f"{API}/trade/online", headers=H(a_tok), timeout=10)
    ids = {u["user_id"] for u in r.json().get("online", [])}
    assert B_ID in ids, f"B not visible online for A. online={ids}"

    # Invite A -> B
    r = requests.post(f"{API}/trade/invite", headers=H(a_tok),
                      json={"to_user_id": B_ID}, timeout=10)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    inv = await b_ws.wait_for("trade_invite", timeout=6)
    assert inv is not None, f"B did not receive trade_invite via WS. msgs={b_ws.messages}"
    assert inv["session_id"] == session_id

    # Accept
    r = requests.post(f"{API}/trade/respond", headers=H(b_tok),
                      json={"session_id": session_id, "accept": True}, timeout=10)
    assert r.status_code == 200, r.text

    start_a = await a_ws.wait_for("trade_start", timeout=6)
    start_b = await b_ws.wait_for("trade_start", timeout=6)
    assert start_a and start_b, "both should receive trade_start"

    # Get A's inventory to pick an item
    inv_a = requests.get(f"{API}/trade/inventory", headers=H(a_tok), timeout=10).json()
    egg = next(it for it in inv_a["items"] if it["item_id"] == "egg_common")
    inv_b = requests.get(f"{API}/trade/inventory", headers=H(b_tok), timeout=10).json()
    crate = next(it for it in inv_b["items"] if it["item_id"] == "crate_bronce")

    # A offers 1 egg + 50 amber
    a_ws.messages.clear(); b_ws.messages.clear()
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": session_id,
                            "items": [{"inv_id": egg["inv_id"], "qty": 1}],
                            "amber": 50}, timeout=10)
    assert r.status_code == 200, r.text
    st = await b_ws.wait_for("trade_state", timeout=5)
    assert st is not None, "B should receive trade_state after A's offer"
    assert st["state"]["them"]["offer"]["amber"] == 50
    assert len(st["state"]["them"]["offer"]["items"]) == 1

    # B offers 1 crate + 20 amber
    r = requests.post(f"{API}/trade/offer", headers=H(b_tok),
                      json={"session_id": session_id,
                            "items": [{"inv_id": crate["inv_id"], "qty": 1}],
                            "amber": 20}, timeout=10)
    assert r.status_code == 200, r.text

    # Both lock
    r = requests.post(f"{API}/trade/lock", headers=H(a_tok),
                      json={"session_id": session_id, "locked": True}, timeout=10)
    assert r.status_code == 200
    r = requests.post(f"{API}/trade/lock", headers=H(b_tok),
                      json={"session_id": session_id, "locked": True}, timeout=10)
    assert r.status_code == 200

    # Confirm without both locked should have been prevented; both are locked now
    r = requests.post(f"{API}/trade/confirm", headers=H(a_tok),
                      json={"session_id": session_id}, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] in ("waiting", "completed")

    r = requests.post(f"{API}/trade/confirm", headers=H(b_tok),
                      json={"session_id": session_id}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    # Verify swap: A should now have crate_bronce, B should have egg_common
    inv_a2 = requests.get(f"{API}/trade/inventory", headers=H(a_tok), timeout=10).json()
    inv_b2 = requests.get(f"{API}/trade/inventory", headers=H(b_tok), timeout=10).json()
    a_has_crate = any(it["item_id"] == "crate_bronce" for it in inv_a2["items"])
    b_has_egg = any(it["item_id"] == "egg_common" for it in inv_b2["items"])
    print("DEBUG A inv after:", [(it["item_id"], it["quantity"]) for it in inv_a2["items"]])
    print("DEBUG B inv after:", [(it["item_id"], it["quantity"]) for it in inv_b2["items"]])
    assert a_has_crate, "A should now own crate_bronce"
    assert b_has_egg, "B should now own egg_common"

    # Amber: A sent 50, B sent 20 -> A vip_coins = 500-50+20 = 470, B = 500-20+50 = 530
    assert inv_a2["amber"]["balance"] == 470, inv_a2["amber"]
    assert inv_b2["amber"]["balance"] == 530, inv_b2["amber"]
    assert inv_a2["amber"]["sent_today"] == 50
    assert inv_b2["amber"]["sent_today"] == 20

    # Cooldown: had items -> both should have >0 cooldown_left
    assert inv_a2["cooldown_left"] > 0
    assert inv_b2["cooldown_left"] > 0

    await a_ws.close(); await b_ws.close()


# ─── 3. Security: cannot confirm without both locked; bad items ───────────
@pytest.mark.asyncio
async def test_security_rules(tokens):
    # reseed to reset cooldown
    a_tok, b_tok = _reseed()
    loop = asyncio.get_event_loop()
    a_ws = WSClient(a_tok); b_ws = WSClient(b_tok)
    a_ws.start(loop); b_ws.start(loop)
    await asyncio.sleep(1.5)

    r = requests.post(f"{API}/trade/invite", headers=H(a_tok),
                      json={"to_user_id": B_ID}, timeout=10)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r = requests.post(f"{API}/trade/respond", headers=H(b_tok),
                      json={"session_id": sid, "accept": True}, timeout=10)
    assert r.status_code == 200

    # confirm without lock -> 400
    r = requests.post(f"{API}/trade/confirm", headers=H(a_tok),
                      json={"session_id": sid}, timeout=10)
    assert r.status_code == 400

    # bogus inv_id -> 400
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": sid,
                            "items": [{"inv_id": "not_owned_xxx", "qty": 1}], "amber": 0}, timeout=10)
    assert r.status_code == 400

    # over-qty
    inv_a = requests.get(f"{API}/trade/inventory", headers=H(a_tok), timeout=10).json()
    egg = next(it for it in inv_a["items"] if it["item_id"] == "egg_common")
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": sid,
                            "items": [{"inv_id": egg["inv_id"], "qty": 999}], "amber": 0}, timeout=10)
    assert r.status_code == 400

    # amber over daily cap
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": sid, "items": [], "amber": 1001}, timeout=10)
    assert r.status_code == 400

    # lock reset when editing: lock both, edit A's offer, both locks should reset
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": sid, "items": [{"inv_id": egg["inv_id"], "qty": 1}], "amber": 0}, timeout=10)
    assert r.status_code == 200
    requests.post(f"{API}/trade/lock", headers=H(a_tok), json={"session_id": sid, "locked": True}, timeout=10)
    requests.post(f"{API}/trade/lock", headers=H(b_tok), json={"session_id": sid, "locked": True}, timeout=10)
    # edit A -> should reset both
    r = requests.post(f"{API}/trade/offer", headers=H(a_tok),
                      json={"session_id": sid, "items": [{"inv_id": egg["inv_id"], "qty": 2}], "amber": 0}, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/trade/active", headers=H(a_tok), timeout=10).json()
    assert r["session"]["me"]["locked"] is False
    assert r["session"]["them"]["locked"] is False

    # confirm now should still 400 since locks reset
    r = requests.post(f"{API}/trade/confirm", headers=H(a_tok),
                      json={"session_id": sid}, timeout=10)
    assert r.status_code == 400

    # cancel closes for both
    r = requests.post(f"{API}/trade/cancel", headers=H(a_tok),
                      json={"session_id": sid}, timeout=10)
    assert r.status_code == 200
    canc = await b_ws.wait_for("trade_cancelled", timeout=5)
    assert canc is not None

    await a_ws.close(); await b_ws.close()


# ─── 4. Reject flow ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reject_flow(tokens):
    a_tok, b_tok = _reseed()
    loop = asyncio.get_event_loop()
    a_ws = WSClient(a_tok); b_ws = WSClient(b_tok)
    a_ws.start(loop); b_ws.start(loop)
    await asyncio.sleep(1.5)

    r = requests.post(f"{API}/trade/invite", headers=H(a_tok),
                      json={"to_user_id": B_ID}, timeout=10)
    assert r.status_code == 200
    sid = r.json()["session_id"]

    r = requests.post(f"{API}/trade/respond", headers=H(b_tok),
                      json={"session_id": sid, "accept": False}, timeout=10)
    assert r.status_code == 200
    msg = await a_ws.wait_for("trade_declined", timeout=5)
    assert msg is not None and msg["session_id"] == sid

    # A can now invite again (no dangling session)
    r = requests.post(f"{API}/trade/invite", headers=H(a_tok),
                      json={"to_user_id": B_ID}, timeout=10)
    assert r.status_code == 200

    await a_ws.close(); await b_ws.close()
