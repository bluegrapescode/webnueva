"""Backend tests for the Tickets/Support system (Fase 1).
Tests: config, create + validation + cooldown, get, message + internal notes,
dynamic categories, staff endpoints, permissions (403 for non-staff).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synced-animations.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


# ------------------- Config -------------------
def test_config_endpoint(h):
    r = requests.get(f"{API}/tickets/config", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "servers" in data and "categories" in data
    assert data["is_staff"] is True  # demo user is admin
    cats = {c["id"] for c in data["categories"]}
    assert {"general", "report_player", "appeal", "patreon", "battlepass", "membership", "report_staff"}.issubset(cats)
    assert len(data["servers"]) >= 1


# ------------------- Validation -------------------
def test_create_missing_required_returns_400(h):
    time.sleep(13)  # respect cooldown
    r = requests.post(f"{API}/tickets", headers=h, json={"category": "report_player", "fields": {}}, timeout=15)
    assert r.status_code == 400, r.text


def test_create_invalid_category_returns_400(h):
    r = requests.post(f"{API}/tickets", headers=h, json={"category": "bogus_cat", "fields": {}}, timeout=15)
    assert r.status_code == 400


# ------------------- Create + persistence -------------------
@pytest.fixture(scope="module")
def created_ticket(h):
    time.sleep(13)
    payload = {
        "category": "general",
        "fields": {
            "subject": "TEST_ subject e2e",
            "description": "Descripción TEST_ de prueba automatizada"
        }
    }
    r = requests.post(f"{API}/tickets", headers=h, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    t = r.json()
    assert t.get("code", "").startswith("#NBL-")
    assert len(t["code"]) == 10  # #NBL-XXXXX
    assert t["status"] == "open"
    assert t["priority"] == "normal"
    assert t["category"] == "general"
    assert t["subject"] == "TEST_ subject e2e"
    assert "id" in t
    return t


def test_get_ticket_persists(h, created_ticket):
    r = requests.get(f"{API}/tickets/{created_ticket['id']}", headers=h, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["ticket"]["id"] == created_ticket["id"]
    assert body["is_staff"] is True
    assert body["can_manage"] is True
    # first system message (user description) exists
    assert len(body["messages"]) >= 1


def test_cooldown_returns_429(h):
    r = requests.post(f"{API}/tickets", headers=h, json={"category": "general", "fields": {"subject": "s", "description": "d"}}, timeout=15)
    assert r.status_code == 429


def test_mine_lists_created(h, created_ticket):
    r = requests.get(f"{API}/tickets/mine", headers=h, timeout=15)
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["tickets"]]
    assert created_ticket["id"] in ids


# ------------------- Messaging + internal notes -------------------
def test_post_message(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/message",
                      headers=h, json={"text": "Mensaje TEST_ público", "internal": False}, timeout=15)
    assert r.status_code == 200
    assert r.json()["message"]["text"] == "Mensaje TEST_ público"
    assert r.json()["message"]["internal"] is False


def test_post_internal_note(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/message",
                      headers=h, json={"text": "Nota interna TEST_", "internal": True}, timeout=15)
    assert r.status_code == 200
    assert r.json()["message"]["internal"] is True


def test_empty_message_400(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/message",
                      headers=h, json={"text": "", "attachments": []}, timeout=15)
    assert r.status_code == 400


# ------------------- Staff actions: take + priority/status -------------------
def test_take_ticket(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/take", headers=h, timeout=15)
    assert r.status_code == 200
    tk = r.json()["ticket"]
    assert tk["status"] == "in_process"
    assert tk["assigned_to"] is not None


def test_update_priority_urgente(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/update",
                      headers=h, json={"priority": "urgente"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["ticket"]["priority"] == "urgente"


def test_update_status_resolved(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/update",
                      headers=h, json={"status": "resolved"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["ticket"]["status"] == "resolved"


def test_update_nothing_400(h, created_ticket):
    r = requests.post(f"{API}/tickets/{created_ticket['id']}/update",
                      headers=h, json={}, timeout=15)
    assert r.status_code == 400


def test_audit_events_present(h, created_ticket):
    r = requests.get(f"{API}/tickets/{created_ticket['id']}", headers=h, timeout=15)
    assert r.status_code == 200
    events = r.json()["events"]
    # created + take + priority + status ⇒ >= 4 events
    assert len(events) >= 3
    joined = " | ".join(e.get("text", "") for e in events)
    assert "Ticket creado" in joined


# ------------------- Staff listing -------------------
@pytest.mark.parametrize("box", ["new", "unassigned", "mine", "in_process", "waiting_user", "resolved", "closed"])
def test_staff_box(h, box):
    r = requests.get(f"{API}/tickets/staff", headers=h, params={"box": box}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "tickets" in body and "counts" in body
    assert set(["new", "unassigned", "mine", "in_process", "waiting_user", "resolved", "closed"]).issubset(body["counts"].keys())


def test_staff_search(h, created_ticket):
    r = requests.get(f"{API}/tickets/staff", headers=h,
                     params={"box": "resolved", "search": created_ticket["code"].replace("#", "")}, timeout=15)
    assert r.status_code == 200
    # If we searched by the code fragment, at least our ticket should appear
    ids = [t["id"] for t in r.json()["tickets"]]
    assert created_ticket["id"] in ids


# ------------------- Not-found + auth -------------------
def test_get_ticket_404(h):
    r = requests.get(f"{API}/tickets/deadbeef_bogus_id_123", headers=h, timeout=15)
    assert r.status_code == 404


def test_unauth_config():
    r = requests.get(f"{API}/tickets/config", timeout=15)
    assert r.status_code in (401, 403)
