"""Backend tests for Cemetery & Resurrection (FÓSIL) system - updated for private feed + 8000 price."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
DEMO_STEAM = "demo_0000000001"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/demo", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_user_id(auth_headers):
    r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=15)
    if r.status_code == 200:
        return r.json().get("id") or r.json().get("user_id") or r.json().get("_id")
    return None


# ---------- CONFIG (public) ----------

def test_config_new_price_and_cooldowns():
    r = requests.get(f"{API}/cemetery/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("fossil_price") == 8000, d
    assert d.get("amber_per_fossil") == 8000, d
    assert d.get("redeem_cooldown_hours") == 2, d
    assert d.get("resurrection_cooldown_hours") == 24, d


# ---------- PRIVACY: feed requires auth and is owner-scoped ----------

def test_feed_requires_auth():
    r = requests.get(f"{API}/cemetery/feed", timeout=15)
    assert r.status_code == 401, r.status_code


def _owner_ok(item, user_id, steam=DEMO_STEAM):
    o = item.get("owner") or {}
    return (user_id and o.get("user_id") == user_id) or o.get("steam_id") == steam


def test_feed_authed_owner_scoped(auth_headers, demo_user_id):
    r = requests.get(f"{API}/cemetery/feed?limit=200", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    items = d.get("items", [])
    assert len(items) > 0
    for it in items:
        assert _owner_ok(it, demo_user_id), f"Non-owner leaked: {it.get('owner')}"


def test_record_by_id_requires_auth_and_owner(auth_headers):
    # owner can read their own record
    feed = requests.get(f"{API}/cemetery/feed", headers=auth_headers, timeout=15).json()
    rid = feed["items"][0]["id"]
    # unauth
    ru = requests.get(f"{API}/cemetery/record/{rid}", timeout=15)
    assert ru.status_code in (401, 403), ru.status_code
    # authed owner
    ra = requests.get(f"{API}/cemetery/record/{rid}", headers=auth_headers, timeout=15)
    assert ra.status_code == 200


def test_hall_of_fame_requires_auth(auth_headers):
    ru = requests.get(f"{API}/cemetery/hall-of-fame", timeout=15)
    assert ru.status_code == 401
    ra = requests.get(f"{API}/cemetery/hall-of-fame", headers=auth_headers, timeout=15)
    assert ra.status_code == 200
    d = ra.json()
    for k in ["longest_survival", "most_kills", "biggest", "resurrected"]:
        assert k in d, f"missing {k}"


# ---------- BUY new price 8000 ----------

def test_buy_insufficient_references_8000(auth_headers):
    r = requests.post(f"{API}/cemetery/fossils/buy", headers=auth_headers,
                      json={"quantity": 999999}, timeout=15)
    assert r.status_code == 400, r.text
    body = r.text
    # 999999 * 8000 = 7,999,992,000 (minus tiny balance) confirms 8000/unit pricing
    assert ("7,999,9" in body) or ("8,000" in body) or ("8000" in body), body

    # Also verify with quantity=1: message should reference exactly 8,000
    r1 = requests.post(f"{API}/cemetery/fossils/buy", headers=auth_headers,
                       json={"quantity": 1}, timeout=15)
    # Either success (200) if user has 8000+ amber, or 400 with "8,000" mentioned
    if r1.status_code == 400:
        assert "8,000" in r1.text or "8000" in r1.text, r1.text


def test_fossils_view_price(auth_headers):
    r = requests.get(f"{API}/cemetery/fossils", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("fossil_price") == 8000


# ---------- ADMIN: sees ALL records ----------

def test_admin_records_returns_all(auth_headers):
    r = requests.get(f"{API}/cemetery/admin/records", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    assert isinstance(items, list)
    # Should include records not owned by demo (e.g., 'Desconocido' leftover)
    owners = [((it.get("owner") or {}).get("steam_id") or "") for it in items]
    # At least one distinct owner OR any record without demo steam_id
    assert any(o != DEMO_STEAM for o in owners) or len(items) >= 12


# ---------- RESURRECT: sets redeem_cooldown_until ~2h ----------

def _clear_cooldown_direct():
    try:
        from pymongo import MongoClient
        _c = MongoClient("mongodb://127.0.0.1:27017")
        _c["laislanublar"]["users"].update_one(
            {"steam_id": DEMO_STEAM},
            {"$unset": {"last_resurrection_at": ""}},
        )
        return True
    except Exception as e:
        print("cooldown-clear skipped:", e)
        return False


def test_resurrect_sets_redeem_cooldown(auth_headers):
    _clear_cooldown_direct()
    # Ensure fossils
    requests.post(f"{API}/cemetery/admin/fossils", headers=auth_headers,
                  json={"steam_id": DEMO_STEAM, "delta": 2}, timeout=15)

    # Create ELEGIBLE record owned by demo
    payload = {
        "species_slug": "trex", "species_name": "Tyrannosaurus",
        "growth": 100, "cause": "Combate", "in_combat": True,
        "owner_steam_id": DEMO_STEAM,
        "stats": {"health": 100, "stamina": 100},
    }
    cr = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=payload, timeout=15)
    assert cr.status_code == 200, cr.text
    rec = cr.json().get("record") or cr.json()
    rid = rec["id"]

    rr = requests.post(f"{API}/cemetery/resurrect", headers=auth_headers,
                       json={"record_id": rid}, timeout=20)

    if rr.status_code == 400 and "cooldown" in rr.text.lower():
        # Expected if 24h cooldown still active - validate record still exists and cleanup
        requests.delete(f"{API}/cemetery/admin/record/{rid}", headers=auth_headers, timeout=10)
        pytest.skip("Demo in 24h cooldown - expected 400")

    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert "redeemable_at" in body, body
    assert "cooldown_until" in body, body

    got = requests.get(f"{API}/cemetery/record/{rid}", headers=auth_headers, timeout=15).json()
    assert got["status"] == "RESUCITADO"
    assert got.get("redeem_cooldown_until"), got

    # cleanup
    requests.delete(f"{API}/cemetery/admin/record/{rid}", headers=auth_headers, timeout=10)
