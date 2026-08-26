"""
BUILD-PACKET item C gate -- marketplace vault (La Boveda) sell/buy escrow.

Imports the REAL backend/vault.py (stdlib + fastapi.HTTPException + game_ipc,
no motor dependency) against a temp SQLite DB whose schema mirrors the bot's
parked_dinos table (vault.py's own _PARKED_COLS list), monkeypatching
game_ipc.BOT_DB_PATH to point at it. This exercises the actual SQLite
persistence layer server.py's _market_create_from_vault / _give_dino /
_vault_delivery_ready orchestrate (which cannot be imported here -- no motor/
.env in this sandbox); the thin Mongo-listing-doc construction those functions
add on top is mirrored inline below, matching server.py's logic exactly:
  1. list  -> snapshot the FULL row (opaque copy), then remove the vault row.
  2. buy   -> insert the snapshot as a new parked row for the buyer (same
              vault.save_parked() helper the park flow uses).
  3. buy against a full vault (cap reached) -> save_parked() returns None,
     i.e. rejected -- exactly the signal _give_dino()/_vault_delivery_ready()
     key off to raise the "boveda llena" 400.

Run: python backend/tests_local/test_marketplace_vault_escrow.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_ipc  # noqa: E402
import vault  # noqa: E402

_PARKED_COLS = [
    "id", "steam_id", "discord_id", "dino_class", "growth",
    "health", "max_health", "stamina", "max_stamina",
    "hunger", "max_hunger", "thirst", "max_thirst",
    "oxygen", "max_oxygen", "x", "y", "z",
    "is_prime", "is_elder", "mutations", "parent_mutations",
    "elder_mutations", "elder_stacks", "skin_code", "skin_data",
    "diet_a", "diet_b", "diet_c",
    "parked_at", "redeem_pending_cmd_id", "redeem_pending_at",
]


def _make_temp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="lin_vault_escrow_", suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    cols_sql = ", ".join(
        "id INTEGER PRIMARY KEY AUTOINCREMENT" if c == "id" else f"{c} TEXT"
        for c in _PARKED_COLS
    )
    conn.execute(f"CREATE TABLE parked_dinos ({cols_sql})")
    conn.commit()
    conn.close()
    return path


def _sample_dino(dino_class="BP_Tyrannosaurus_C", growth=0.87, mutations="Titan|None|Feral|None"):
    return {
        "dino": dino_class, "growth": growth,
        "health": 48.5, "max_health": 50.0, "stamina": 300.0, "max_stamina": 330.0,
        "hunger": 15.0, "max_hunger": 17.0, "thirst": 900.0, "max_thirst": 1000.0,
        "oxygen": 330.0, "max_oxygen": 330.0, "x": -100000.5, "y": 200000.25, "z": 500.0,
        "is_prime": True, "is_elder": False, "mutations": mutations,
        "parent_mutations": "None|None|None|None", "elder_mutations": "", "elder_stacks": 0,
        "skin_code": "abc123", "skin_data": "",
        "diet_a": 4.9, "diet_b": 0.0, "diet_c": 0.0,
    }


def main() -> int:
    failures = []
    db_path = _make_temp_db()
    game_ipc.BOT_DB_PATH = db_path

    seller_sid, buyer_sid = "76561198100000001", "76561198100000002"
    pd = _sample_dino()

    # ---- 1) LIST: snapshot the row (opaque copy), then remove it -----------------
    new_id = vault.save_parked(seller_sid, "", pd, cap=0)  # cap<=0 = unlimited
    if new_id is None:
        failures.append("save_parked() unexpectedly rejected the seller's first park (cap=0=unlimited)")

    row = vault.get_parked_by_id(new_id)
    if not row or str(row.get("steam_id")) != seller_sid:
        failures.append(f"get_parked_by_id() ownership check failed: {row!r}")

    # mirror server.py's _market_create_from_vault: snapshot BEFORE deleting.
    listing_payload = dict(row) if row else {}

    deleted = vault.delete_owned(new_id, seller_sid)
    if deleted != 1:
        failures.append(f"delete_owned() should remove exactly 1 row, got {deleted!r}")
    if vault.get_parked_by_id(new_id) is not None:
        failures.append("row still present in the vault after a successful delete -- would double-list the dino")

    # opaque copy: the listing's payload must carry the ORIGINAL absolute values,
    # not a transformed/re-derived one.
    for k, expect in (("dino_class", pd["dino"]), ("mutations", pd["mutations"])):
        if listing_payload.get(k) != expect:
            failures.append(f"listing payload not opaque: {k}={listing_payload.get(k)!r} (expected {expect!r})")
    if abs(float(listing_payload.get("growth") or 0) - pd["growth"]) > 1e-9:
        failures.append(f"listing payload growth not opaque: {listing_payload.get('growth')!r} (expected {pd['growth']!r})")

    # redeem-pending guard: delete_owned() must refuse a row with a pending redeem
    # (server.py's _market_create_from_vault checks this before even attempting the
    # delete; delete_owned()'s own WHERE clause is the authoritative, race-safe gate).
    pending_id = vault.save_parked(seller_sid, "", _sample_dino(), cap=0)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE parked_dinos SET redeem_pending_cmd_id = ? WHERE id = ?", ("some-cmd-id", pending_id))
    conn.commit()
    conn.close()
    guarded = vault.delete_owned(pending_id, seller_sid)
    if guarded != 0:
        failures.append(f"delete_owned() must refuse a row with a pending redeem, got rowcount={guarded!r}")

    # ---- 2) BUY: insert the snapshot as a new parked row for the buyer -----------
    buyer_cap = 20  # LIN_PARK_CAP default (owner ruling 2026-07-30, was 10)
    buyer_row_id = vault.save_parked(buyer_sid, "", listing_payload, buyer_cap)
    if buyer_row_id is None:
        failures.append("save_parked() unexpectedly rejected the buyer's delivery (fresh vault, well under cap)")
    buyer_row = vault.get_parked_by_id(buyer_row_id)
    if not buyer_row or str(buyer_row.get("steam_id")) != buyer_sid:
        failures.append(f"delivered row ownership mismatch: {buyer_row!r}")
    # identical payload: every ABSOLUTE stat field must match the seller's original
    # row untouched (id/steam_id/discord_id/parked_at legitimately differ).
    compare_fields = ["dino_class", "growth", "health", "max_health", "mutations",
                      "parent_mutations", "is_prime", "diet_a", "skin_code"]
    for k in compare_fields:
        if str(buyer_row.get(k)) != str(row.get(k)):
            failures.append(f"delivered payload field {k!r} mismatch: {buyer_row.get(k)!r} != original {row.get(k)!r}")
    # vault._dino_view()'s derived display fields must also agree (species/growth_pct/mutations_count).
    seller_view = vault._dino_view(row)
    buyer_view = vault._dino_view(buyer_row)
    for k in ("species", "growth_pct", "mutations_count", "is_prime"):
        if seller_view.get(k) != buyer_view.get(k):
            failures.append(f"_dino_view() field {k!r} mismatch after delivery: {buyer_view.get(k)!r} != {seller_view.get(k)!r}")
    if buyer_view.get("mutations_count") != 2:
        failures.append(f"mutations_count mismatch for 'Titan|None|Feral|None': {buyer_view.get('mutations_count')!r} (expected 2)")

    # ---- 3) full vault -> buy rejected --------------------------------------------
    cap_sid = "76561198100000099"
    cap = 2
    r1 = vault.save_parked(cap_sid, "", _sample_dino(), cap)
    r2 = vault.save_parked(cap_sid, "", _sample_dino(), cap)
    if r1 is None or r2 is None:
        failures.append(f"filling the vault to cap unexpectedly failed: r1={r1!r} r2={r2!r}")
    if vault.count_parked(cap_sid) != cap:
        failures.append(f"count_parked() mismatch after filling to cap: {vault.count_parked(cap_sid)!r} (expected {cap})")
    r3 = vault.save_parked(cap_sid, "", _sample_dino(), cap)
    if r3 is not None:
        failures.append(f"save_parked() must reject a delivery once the vault is at cap, got a new row id {r3!r}")
    if vault.count_parked(cap_sid) != cap:
        failures.append("a rejected delivery must not change count_parked()")

    if failures:
        print("FAIL -- marketplace vault escrow gate:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS -- list (row gone + opaque payload snapshot), buy (identical payload delivered), "
          "redeem-pending delete guard, and full-vault rejection all correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
