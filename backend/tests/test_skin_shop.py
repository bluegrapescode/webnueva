"""Backend tests for /api/shop/* and /api/admin/shop/* — Tienda de Skins."""
import os
import time
import uuid
import json
import pytest
import requests
import websocket  # websocket-client
import threading

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"


# ─── fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def created_skin(admin_client):
    payload = {
        "name": f"TEST_Skin_{uuid.uuid4().hex[:6]}",
        "description": "test skin",
        "image_url": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23",
        "rarity": "epic",
        "section": "destacados",
        "dino_species": "Tyrannosaurus",
        "price_usd": 4.99,
        "active": True,
    }
    r = admin_client.post(f"{API}/admin/shop/skins", json=payload, timeout=30)
    assert r.status_code == 200, f"create skin failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("success") is True
    skin = data["skin"]
    assert skin.get("id")
    assert skin["price_usd"] == 4.99
    assert skin["rarity"] == "epic"
    assert skin["section"] == "destacados"
    yield skin
    # teardown
    try:
        admin_client.delete(f"{API}/admin/shop/skins/{skin['id']}", timeout=15)
    except Exception:
        pass


# ─── tests ──────────────────────────────────────────────────────────────────
class TestPublicShop:
    def test_list_skins_sections(self, admin_client, created_skin):
        r = admin_client.get(f"{API}/shop/skins", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "sections" in d and "server_time" in d
        for s in ("destacados", "diario", "temporada"):
            assert s in d["sections"]
        ids = [x["id"] for sec in d["sections"].values() for x in sec]
        assert created_skin["id"] in ids
        # each card has required flags
        card = next(x for sec in d["sections"].values() for x in sec
                    if x["id"] == created_skin["id"])
        for k in ("owned", "live", "equipped", "price_usd", "rarity"):
            assert k in card, f"missing {k}"
        assert card["owned"] is False
        assert card["live"] is True

    def test_list_skins_requires_auth(self):
        r = requests.get(f"{API}/shop/skins", timeout=10)
        assert r.status_code in (401, 403)


class TestAdminShop:
    def test_admin_list_stats(self, admin_client, created_skin):
        r = admin_client.get(f"{API}/admin/shop/skins", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "stats" in d
        for k in ("total_skins", "live_skins", "total_sold", "paid_orders", "revenue_usd"):
            assert k in d["stats"], f"stat missing: {k}"
        ids = [x["id"] for x in d["items"]]
        assert created_skin["id"] in ids

    def test_admin_create_requires_admin(self):
        r = requests.post(f"{API}/admin/shop/skins",
                          json={"name": "x", "image_url": "y", "price_usd": 1.0},
                          timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_update_price_generates_new_price(self, admin_client, created_skin):
        r = admin_client.patch(f"{API}/admin/shop/skins/{created_skin['id']}",
                               json={"price_usd": 7.77}, timeout=30)
        assert r.status_code == 200, r.text
        skin = r.json()["skin"]
        assert skin["price_usd"] == 7.77

    def test_admin_update_active_and_section_and_rarity(self, admin_client, created_skin):
        r = admin_client.patch(f"{API}/admin/shop/skins/{created_skin['id']}",
                               json={"section": "temporada", "rarity": "legendary", "active": True},
                               timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()["skin"]
        assert s["section"] == "temporada"
        assert s["rarity"] == "legendary"

    def test_admin_update_invalid_rarity(self, admin_client, created_skin):
        r = admin_client.patch(f"{API}/admin/shop/skins/{created_skin['id']}",
                               json={"rarity": "BOGUS"}, timeout=15)
        assert r.status_code == 400


class TestCheckout:
    def test_checkout_returns_stripe_url(self, admin_client, created_skin):
        r = admin_client.post(f"{API}/shop/checkout",
                              json={"skin_id": created_skin["id"], "origin_url": BASE_URL},
                              timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("session_id")
        url = d.get("checkout_url") or ""
        assert "checkout.stripe.com" in url, f"unexpected url: {url}"
        # payment_status is pending before paying
        r2 = requests.get(f"{API}/payments/status/{d['session_id']}", timeout=15)
        assert r2.status_code == 200
        js = r2.json()
        assert js["payment_status"] in ("pending", "unpaid")
        assert js.get("granted") is False

    def test_checkout_missing_skin(self, admin_client):
        r = admin_client.post(f"{API}/shop/checkout",
                              json={"skin_id": "does-not-exist", "origin_url": BASE_URL},
                              timeout=15)
        assert r.status_code == 404


class TestEquip:
    def test_equip_denies_when_not_owned(self, admin_client, created_skin):
        r = admin_client.post(f"{API}/shop/equip",
                              json={"skin_id": created_skin["id"]}, timeout=15)
        assert r.status_code == 403


class TestWebsocket:
    def test_ws_shop_hello_and_broadcast(self, admin_token, admin_client):
        ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/shop/ws"
        received = []

        def _on_message(wsapp, msg):
            try:
                received.append(json.loads(msg))
            except Exception:
                pass

        ws = websocket.WebSocketApp(ws_url, on_message=_on_message)
        th = threading.Thread(target=ws.run_forever, daemon=True)
        th.start()
        time.sleep(2.0)
        try:
            assert any(m.get("type") == "shop_hello" for m in received), f"no hello. got={received}"

            # trigger a broadcast by creating a skin
            payload = {
                "name": f"TEST_WS_{uuid.uuid4().hex[:5]}",
                "image_url": "https://x/y.png",
                "rarity": "common", "section": "diario",
                "price_usd": 1.99, "active": True,
            }
            r = admin_client.post(f"{API}/admin/shop/skins", json=payload, timeout=30)
            assert r.status_code == 200
            sid = r.json()["skin"]["id"]
            time.sleep(2.0)
            assert any(m.get("type") == "shop_update" for m in received), f"no shop_update. got={received}"
            # cleanup
            admin_client.delete(f"{API}/admin/shop/skins/{sid}", timeout=15)
        finally:
            try:
                ws.close()
            except Exception:
                pass


class TestDelete:
    def test_admin_delete_skin(self, admin_client):
        # separate skin so we can freely delete
        payload = {"name": f"TEST_del_{uuid.uuid4().hex[:5]}",
                   "image_url": "https://x/y.png", "rarity": "common",
                   "section": "diario", "price_usd": 2.0, "active": True}
        r = admin_client.post(f"{API}/admin/shop/skins", json=payload, timeout=30)
        assert r.status_code == 200
        sid = r.json()["skin"]["id"]
        r = admin_client.delete(f"{API}/admin/shop/skins/{sid}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("success") is True
        # verify gone from admin list
        r = admin_client.get(f"{API}/admin/shop/skins", timeout=15)
        ids = [x["id"] for x in r.json()["items"]]
        assert sid not in ids
