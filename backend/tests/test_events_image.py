"""Iteration 2: backend tests for the new EventInput.image field."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def test_events_list_ok():
    r = requests.get(f"{BASE_URL}/api/events", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_create_event_with_image_roundtrip(auth_headers):
    payload = {
        "title": "TEST_Evento con foto",
        "description": "Descripción del evento de prueba con imagen.",
        "date_label": "Sat 21:00 UTC",
        "type": "PvP",
        "image": "/dinos/carno.png",
    }
    r = requests.post(f"{BASE_URL}/api/admin/events", json=payload, headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["title"] == payload["title"]
    assert doc["image"] == "/dinos/carno.png"
    assert doc["type"] == "PvP"
    assert "id" in doc
    event_id = doc["id"]

    # Verify GET /api/events returns image
    r2 = requests.get(f"{BASE_URL}/api/events", timeout=15)
    assert r2.status_code == 200
    found = [e for e in r2.json() if e.get("id") == event_id]
    assert len(found) == 1
    assert found[0].get("image") == "/dinos/carno.png"

    # cleanup
    requests.delete(f"{BASE_URL}/api/admin/events/{event_id}", headers=auth_headers, timeout=15)


def test_admin_create_event_no_image_defaults_none(auth_headers):
    payload = {
        "title": "TEST_Evento sin foto",
        "description": "Sin imagen",
        "date_label": "Sun 20:00 UTC",
        "type": "Community",
    }
    r = requests.post(f"{BASE_URL}/api/admin/events", json=payload, headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc.get("image") is None
    requests.delete(f"{BASE_URL}/api/admin/events/{doc['id']}", headers=auth_headers, timeout=15)
