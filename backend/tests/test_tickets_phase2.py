"""Phase 2 tests: close/reopen, single-insert on post_message, real file upload+serve, server option."""
import os, time, io, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://synced-animations.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_config_has_isla_nublar_server(h):
    r = requests.get(f"{BASE}/api/tickets/config", headers=h, timeout=15)
    assert r.status_code == 200
    servers = r.json().get("servers", [])
    names = [s["name"] for s in servers]
    assert any("LA ISLA NUBLAR - X3 - SEMI-REALISMO - VC - ESP/LATAM" in n for n in names), names


@pytest.fixture(scope="module")
def ticket_id(h):
    time.sleep(13)  # cooldown
    payload = {"category": "general", "fields": {"subject": "TEST_phase2 subject", "description": "TEST_phase2 description"}}
    r = requests.post(f"{BASE}/api/tickets", headers=h, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_post_message_creates_exactly_one(h, ticket_id):
    """Bug fix 1: sending one message inserts exactly one message row."""
    # count before
    r0 = requests.get(f"{BASE}/api/tickets/{ticket_id}", headers=h, timeout=15)
    before = len(r0.json()["messages"])
    body = {"text": "TEST_only_one_message", "attachments": [], "internal": False}
    r = requests.post(f"{BASE}/api/tickets/{ticket_id}/message", headers=h, json=body, timeout=15)
    assert r.status_code == 200
    time.sleep(1)
    r2 = requests.get(f"{BASE}/api/tickets/{ticket_id}", headers=h, timeout=15)
    after_msgs = r2.json()["messages"]
    added = [m for m in after_msgs if m["text"] == "TEST_only_one_message"]
    assert len(added) == 1, f"expected 1, got {len(added)}"
    assert len(after_msgs) == before + 1


def test_close_and_reopen(h, ticket_id):
    """Bug fix 2: close -> status closed + system message; reopen -> status open + system message."""
    r = requests.post(f"{BASE}/api/tickets/{ticket_id}/close", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["status"] == "closed"
    time.sleep(0.5)
    r2 = requests.get(f"{BASE}/api/tickets/{ticket_id}", headers=h, timeout=15).json()
    sys_close = [m for m in r2["messages"] if m.get("role") == "system" and "cerró" in (m.get("text") or "")]
    assert sys_close, "system 'cerró' message missing"

    r = requests.post(f"{BASE}/api/tickets/{ticket_id}/reopen", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["status"] == "open"
    time.sleep(0.5)
    r3 = requests.get(f"{BASE}/api/tickets/{ticket_id}", headers=h, timeout=15).json()
    sys_reopen = [m for m in r3["messages"] if m.get("role") == "system" and "reabrió" in (m.get("text") or "")]
    assert sys_reopen, "system 'reabrió' message missing"


def test_upload_and_serve_image(h, ticket_id):
    """Phase 2: POST /api/tickets/{tid}/upload returns url; GET /api/tickets/files/{fid}.{ext} serves bytes."""
    # 1x1 PNG
    png = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "890000000A49444154789C6300010000000500010D0A2DB40000000049454E44"
        "AE426082"
    )
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = requests.post(f"{BASE}/api/tickets/{ticket_id}/upload", headers=h, files=files, timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    url = j["url"]
    assert url.endswith(".png"), url
    # public GET (no auth)
    g = requests.get(url, timeout=30)
    assert g.status_code == 200, g.text
    assert g.headers.get("content-type", "").startswith("image/"), g.headers
    assert len(g.content) == len(png)


def test_upload_rejects_bad_ext(h, ticket_id):
    files = {"file": ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = requests.post(f"{BASE}/api/tickets/{ticket_id}/upload", headers=h, files=files, timeout=30)
    assert r.status_code == 400
