# -*- coding: utf-8 -*-
"""Inventory-wipe staff feed gate - embed builder + fire-and-forget containment.

Imports the REAL backend/staff_feed.py (httpx only, no Mongo/env needed). The
/admin/users/{user_id}/inventory-wipe route lane (delete_many filters, 404,
response shape) is NOT locally importable (motor absent) - it is covered by the
existing prod E2E lane after deploy, same accepted pattern as
test_marketplace_vault_escrow.py's header note.

Run: py -3.12 backend/tests_local/test_inventory_wipe_feed.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import staff_feed  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


# Spanish literals kept as escapes so this source file stays pure ASCII.
BORRO = "borr" + chr(0xF3)       # borro with accented o
BOUNDARY = ("Monedas, La B" + chr(0xF3) + "veda y el Mercado no fueron modificados.")
ELLIPSIS = chr(0x2026)

print("[embed: standard wipe]")
e = staff_feed.build_inventory_wipe_embed("AdminX", "CheaterY", 34, 5, False)
d = e["description"]
check("title", e["title"] == "Inventario borrado", e["title"])
check("color red", e["color"] == 0xE24A4A, hex(e["color"]))
check("footer", e["footer"]["text"] == staff_feed._FOOTER, str(e["footer"]))
check("staff bolded", "**AdminX**" in d, d)
check("verb accent", f"{BORRO} el inventario de **CheaterY**" in d, d)
check("item count 34", "**34** objetos del inventario web" in d, d)
check("skin count 5", "**5** skins glitch" in d, d)
check("boundary sentence", BOUNDARY in d, d)
check("boundary key phrase", "no fueron modificados" in d, d)

print("[embed: self wipe]")
e2 = staff_feed.build_inventory_wipe_embed("AdminX", "AdminX", 2, 0, True)
d2 = e2["description"]
check("self phrasing", "su propio inventario" in d2, d2)
check("no target bold form", "de **" not in d2, d2)
check("self keeps red color", e2["color"] == 0xE24A4A, hex(e2["color"]))

print("[embed: zero counts]")
e3 = staff_feed.build_inventory_wipe_embed("AdminX", "EmptyGuy", 0, 0, False)
d3 = e3["description"]
check("zero items renders 0", "**0** objetos del inventario web" in d3, d3)
check("zero skins renders 0", "**0** skins glitch" in d3, d3)

print("[embed: name fallbacks + clipping]")
e4 = staff_feed.build_inventory_wipe_embed(None, "", 1, 1, False)
d4 = e4["description"]
check("staff fallback", "**Staff**" in d4, d4)
check("target fallback", "**Jugador**" in d4, d4)
long_name = "A" * 200
e5 = staff_feed.build_inventory_wipe_embed("S", long_name, 1, 1, False)
d5 = e5["description"]
clipped = "A" * 79 + ELLIPSIS
check("200-char target clipped to 80", f"**{clipped}**" in d5, d5[:200])
check("raw 200-char name absent", long_name not in d5)

print("[embed: thousands formatting]")
e6 = staff_feed.build_inventory_wipe_embed("S", "T", 1234, 0, False)
check("1234 -> 1.234", "**1.234** objetos" in e6["description"], e6["description"])

print("[containment: fire outside event loop]")
try:
    staff_feed.fire_inventory_wipe("a", "b", 1, 1)
    check("fire_inventory_wipe no-loop does not raise", True)
except Exception as exc:  # noqa: BLE001 - the whole point is that this must not happen
    check("fire_inventory_wipe no-loop does not raise", False, f"{type(exc).__name__}: {exc}")
try:
    staff_feed.fire_inventory_wipe(None, None, 0, 0, self_wipe=True)
    check("fire_inventory_wipe degenerate args do not raise", True)
except Exception as exc:  # noqa: BLE001
    check("fire_inventory_wipe degenerate args do not raise", False, f"{type(exc).__name__}: {exc}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
