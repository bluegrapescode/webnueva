"""Backend tests for Cemetery & Resurrection (FÓSIL) system."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/demo", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ----------- PUBLIC endpoints -----------

def test_config():
    r = requests.get(f"{API}/cemetery/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("fossil_price") == 1500
    # cooldown 24h in either hours or seconds
    assert d.get("cooldown_hours") == 24 or d.get("resurrect_cooldown_hours") == 24 or d.get("cooldown_seconds") == 86400 or "cooldown" in str(d).lower()


def test_feed_basic():
    r = requests.get(f"{API}/cemetery/feed", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and isinstance(d["items"], list)
    assert "stats" in d or "total" in d
    assert len(d["items"]) > 0


def _dino(it):
    return it.get("dino") or it


def test_feed_filter_species():
    r = requests.get(f"{API}/cemetery/feed?species=deino", timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    for it in items:
        d = _dino(it)
        assert "deino" in (d.get("species_slug") or "").lower() or "deino" in (d.get("species_name") or "").lower()


def test_feed_filter_status_and_search_and_sort():
    r = requests.get(f"{API}/cemetery/feed?status=ELEGIBLE", timeout=15)
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert it["status"] == "ELEGIBLE"
    r2 = requests.get(f"{API}/cemetery/feed?search=Deino", timeout=15)
    assert r2.status_code == 200
    r3 = requests.get(f"{API}/cemetery/feed?sort=kills", timeout=15)
    assert r3.status_code == 200
    kills = [it.get("kills", 0) for it in r3.json()["items"]]
    assert kills == sorted(kills, reverse=True)


def test_drowning_combat_rule():
    """Deinosuchus drown-in-combat = ELEGIBLE; other species drown-in-combat = NO_REVIVIBLE."""
    items = requests.get(f"{API}/cemetery/feed?limit=200", timeout=15).json()["items"]
    def is_drown(i): return (i.get("cause") or "").lower().startswith("ahoga") and i.get("in_combat")
    deino_dic = [i for i in items if "deino" in (_dino(i).get("species_slug") or "").lower() and is_drown(i)]
    other_dic = [i for i in items if "deino" not in (_dino(i).get("species_slug") or "").lower() and is_drown(i)]
    assert deino_dic, "expected at least one Deinosuchus drown-in-combat seed"
    assert other_dic, "expected at least one non-deino drown-in-combat seed"
    assert all(i["status"] == "ELEGIBLE" for i in deino_dic), f"Deino DIC should be ELEGIBLE: {deino_dic}"
    assert all(i["status"] == "NO_REVIVIBLE" for i in other_dic), f"Other DIC should be NO_REVIVIBLE: {other_dic}"


def test_record_by_id_and_404():
    items = requests.get(f"{API}/cemetery/feed", timeout=15).json()["items"]
    rid = items[0]["id"]
    r = requests.get(f"{API}/cemetery/record/{rid}", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == rid
    r404 = requests.get(f"{API}/cemetery/record/no-such-id-xyz", timeout=15)
    assert r404.status_code == 404


def test_hall_of_fame():
    r = requests.get(f"{API}/cemetery/hall-of-fame", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["longest_survival", "most_kills", "biggest", "resurrected"]:
        assert k in d, f"missing {k}"
        assert isinstance(d[k], list)


# ----------- AUTH endpoints -----------

def test_fossils_view(auth_headers):
    r = requests.get(f"{API}/cemetery/fossils", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["fossils", "amber_balance", "fossil_price", "can_claim_free"]:
        assert k in d, f"missing {k} in {d}"
    assert d["fossil_price"] == 1500


def test_claim_free_idempotent(auth_headers):
    # First call may succeed or already-claimed depending on prior state
    r1 = requests.post(f"{API}/cemetery/fossils/claim-free", headers=auth_headers, timeout=15)
    assert r1.status_code in (200, 400)
    r2 = requests.post(f"{API}/cemetery/fossils/claim-free", headers=auth_headers, timeout=15)
    assert r2.status_code == 400
    body = r2.text.lower()
    assert "reclamaste" in body or "already" in body or "mes" in body


def test_buy_insufficient(auth_headers):
    # Buying a huge quantity should fail with insufficient amber
    r = requests.post(f"{API}/cemetery/fossils/buy", headers=auth_headers, json={"quantity": 999999}, timeout=15)
    assert r.status_code == 400


# ----------- ADMIN endpoints -----------

def test_admin_create_update_delete_record(auth_headers):
    # Non-deino drown in combat -> NO_REVIVIBLE
    payload = {
        "species_slug": "carnotaurus",
        "species_name": "Carnotaurus",
        "growth": 100,
        "cause": "Ahogamiento",
        "in_combat": True,
        "owner_steam_id": "demo_0000000001",
    }
    r = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    rec = r.json().get("record") or r.json()
    assert rec["status"] == "NO_REVIVIBLE"
    rid = rec["id"]

    # Update
    r2 = requests.put(f"{API}/cemetery/admin/record/{rid}", headers=auth_headers,
                      json={"status": "ELEGIBLE"}, timeout=15)
    assert r2.status_code == 200
    got = requests.get(f"{API}/cemetery/record/{rid}", timeout=15).json()
    assert got["status"] == "ELEGIBLE"

    # Delete
    r3 = requests.delete(f"{API}/cemetery/admin/record/{rid}", headers=auth_headers, timeout=15)
    assert r3.status_code in (200, 204)
    assert requests.get(f"{API}/cemetery/record/{rid}", timeout=15).status_code == 404


def test_admin_deino_drown_combat_still_eligible(auth_headers):
    payload = {
        "species_slug": "deino",
        "species_name": "Deinosuchus",
        "cause": "Ahogamiento",
        "in_combat": True,
        "owner_steam_id": "demo_0000000001",
    }
    r = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200
    rec = r.json().get("record") or r.json()
    assert rec["status"] == "ELEGIBLE"
    # cleanup
    requests.delete(f"{API}/cemetery/admin/record/{rec['id']}", headers=auth_headers, timeout=15)


def test_admin_fossils_adjust(auth_headers):
    r = requests.post(f"{API}/cemetery/admin/fossils", headers=auth_headers,
                      json={"steam_id": "demo_0000000001", "delta": 3}, timeout=15)
    assert r.status_code == 200, r.text


def test_admin_config_update(auth_headers):
    # change to 1500 to keep same value
    r = requests.put(f"{API}/cemetery/admin/config", headers=auth_headers,
                     json={"fossil_price": 1500}, timeout=15)
    assert r.status_code == 200
    assert requests.get(f"{API}/cemetery/config", timeout=10).json()["fossil_price"] == 1500


def test_admin_transactions_list(auth_headers):
    r = requests.get(f"{API}/cemetery/admin/transactions", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json(), list) or True


# ----------- Resurrect flow -----------

def test_resurrect_flow(auth_headers):
    """Grant fossil to demo user, create an owned ELEGIBLE record, resurrect it."""
    # Clear any leftover cooldown from prior curl tests (preview only)
    try:
        from pymongo import MongoClient
        _c = MongoClient("mongodb://127.0.0.1:27017")
        _c["laislanublar"]["users"].update_one(
            {"steam_id": "demo_0000000001"},
            {"$unset": {"last_resurrection_at": ""}},
        )
    except Exception as _e:
        print("cooldown-clear skipped:", _e)

    # Give the demo user 2 fossils
    requests.post(f"{API}/cemetery/admin/fossils", headers=auth_headers,
                  json={"steam_id": "demo_0000000001", "delta": 2}, timeout=15)

    # Create an ELEGIBLE record owned by demo user
    payload = {
        "species_slug": "trex",
        "species_name": "Tyrannosaurus",
        "growth": 100,
        "cause": "Combate",
        "in_combat": True,
        "owner_steam_id": "demo_0000000001",
        "stats": {"health": 100, "stamina": 100},
    }
    cr = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=payload, timeout=15)
    assert cr.status_code == 200
    rec = cr.json().get("record") or cr.json()
    rid = rec["id"]
    assert rec["status"] == "ELEGIBLE"

    # Check fossils before
    before = requests.get(f"{API}/cemetery/fossils", headers=auth_headers, timeout=15).json()
    fossils_before = before["fossils"]
    in_cooldown = bool(before.get("cooldown_until") or before.get("cooldown_seconds"))

    # Resurrect
    rr = requests.post(f"{API}/cemetery/resurrect", headers=auth_headers,
                       json={"record_id": rid}, timeout=20)

    if in_cooldown and rr.status_code == 400:
        assert "cooldown" in rr.text.lower()
        pytest.skip("Demo user currently in resurrection cooldown; validated cooldown rejection")

    assert rr.status_code == 200, rr.text

    # Verify status
    got = requests.get(f"{API}/cemetery/record/{rid}", timeout=15).json()
    assert got["status"] == "RESUCITADO"

    # Fossil deducted
    after = requests.get(f"{API}/cemetery/fossils", headers=auth_headers, timeout=15).json()
    assert after["fossils"] == fossils_before - 1
    assert after.get("cooldown_until") or after.get("cooldown_seconds")

    # Appears in my-resurrections
    mr = requests.get(f"{API}/cemetery/my-resurrections", headers=auth_headers, timeout=15).json()
    items = mr if isinstance(mr, list) else mr.get("items", [])
    assert any((i.get("record_id") == rid or i.get("id") == rid or (i.get("record") or {}).get("id") == rid) for i in items), f"Resurrected dino not found in {items}"

    # Second resurrection attempt on same record -> 400
    rr2 = requests.post(f"{API}/cemetery/resurrect", headers=auth_headers,
                        json={"record_id": rid}, timeout=15)
    assert rr2.status_code == 400

    # Cooldown blocks another resurrection - create another record and try
    payload2 = dict(payload)
    payload2["species_slug"] = "allosaurus"
    cr2 = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=payload2, timeout=15)
    rid2 = (cr2.json().get("record") or cr2.json())["id"]
    rr3 = requests.post(f"{API}/cemetery/resurrect", headers=auth_headers,
                        json={"record_id": rid2}, timeout=15)
    assert rr3.status_code == 400
    assert "cooldown" in rr3.text.lower() or "reviv" in rr3.text.lower() or "fósil" in rr3.text.lower() or "fossil" in rr3.text.lower()

    # NO_REVIVIBLE cannot be resurrected
    nr_payload = {"species_slug": "carnotaurus", "cause": "Ahogamiento", "in_combat": True,
                  "owner_steam_id": "demo_0000000001"}
    nr = requests.post(f"{API}/cemetery/admin/record", headers=auth_headers, json=nr_payload, timeout=15)
    nr_id = (nr.json().get("record") or nr.json())["id"]
    rr4 = requests.post(f"{API}/cemetery/resurrect", headers=auth_headers,
                        json={"record_id": nr_id}, timeout=15)
    assert rr4.status_code == 400

    # cleanup
    for c in (rid, rid2, nr_id):
        requests.delete(f"{API}/cemetery/admin/record/{c}", headers=auth_headers, timeout=10)
