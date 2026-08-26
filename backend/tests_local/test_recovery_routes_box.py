"""The recovery ROUTES, driven over real HTTP against the real backend.

Runs ON THE BOX (needs motor + a live mongod). Everything is isolated:

  * DB_NAME is a scratch database, dropped at the end.
  * game_ipc.BOT_DB_PATH points at a COPY of the vault, so no real player gains
    a dino.
  * game_ipc.SAVED_DIR points at a scratch death log.

Nothing in prod is read for writing and nothing is left behind. The pure-layer
suite (test_dino_recovery.py) proves the parsing; this one proves the wiring —
auth, request binding, the vault INSERT, and the anti-duplicate claim — which is
where the last recovery bug actually lived.

Run:  set DB_NAME=lin_recovery_test && C:\LaIslaNublar\venv\Scripts\python.exe
      tests_local\test_recovery_routes_box.py
"""
import asyncio
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time


def now_iso_str():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

SID = "76561199009325734"
OTHER_SID = "76561199705883012"
CARNO_TS = 1784920089
TREX_PARK_TS = 1784911534

os.environ.setdefault("DB_NAME", "lin_recovery_test")
if os.environ.get("DB_NAME") in ("laislanublar", "", None):
    print("REFUSING TO RUN against the live database. Set DB_NAME to a scratch name.")
    sys.exit(2)

TMP = tempfile.mkdtemp(prefix="lin_route_test_")
PASS = 0
FAIL = []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {extra}".strip())


# --- scratch game files ------------------------------------------------------
SAVED = os.path.join(TMP, "Saved")
os.makedirs(SAVED, exist_ok=True)
DEATHS = [
    {"ts": 1784895023, "sid": SID, "cause": "unknown", "dino": "BP_Tyrannosaurus_C", "growth": 0.517},
    {"ts": TREX_PARK_TS, "sid": SID, "cause": "unknown", "dino": "BP_Tyrannosaurus_C", "growth": 0.656},
    {"ts": 1784912551, "sid": SID, "cause": "unknown", "dino": "BP_Carnotaurus_C", "growth": 0.388},
    {"ts": 1784918012, "sid": SID, "cause": "unknown", "dino": "BP_Carnotaurus_C", "growth": 0.952},
    {"ts": CARNO_TS, "sid": SID, "cause": "starve", "dino": "BP_Carnotaurus_C", "growth": 0.984},
    {"ts": 1784921000, "sid": OTHER_SID, "cause": "killed", "dino": "BP_Carnotaurus_C", "growth": 0.404},
]
with open(os.path.join(SAVED, "death_causes.log"), "w", encoding="utf-8") as fh:
    for d in DEATHS:
        fh.write(json.dumps(d) + "\n")

# --- scratch vault DB, real LIN schema --------------------------------------
VAULT_DB = os.path.join(TMP, "vault.db")
con = sqlite3.connect(VAULT_DB)
con.execute("""CREATE TABLE parked_dinos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, steam_id TEXT NOT NULL, discord_id TEXT NOT NULL,
    dino_class TEXT, growth REAL, health REAL, max_health REAL, stamina REAL, max_stamina REAL,
    hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL, oxygen REAL, max_oxygen REAL,
    x REAL, y REAL, z REAL, is_prime INTEGER DEFAULT 0, is_elder INTEGER DEFAULT 0,
    mutations TEXT DEFAULT "", parent_mutations TEXT DEFAULT "", elder_mutations TEXT DEFAULT "",
    elder_stacks INTEGER DEFAULT 0, skin_code TEXT DEFAULT "", skin_data TEXT DEFAULT "",
    diet_a REAL DEFAULT 0, diet_b REAL DEFAULT 0, diet_c REAL DEFAULT 0, parked_at TEXT,
    redeem_pending_cmd_id TEXT, redeem_pending_at INTEGER, custom_name TEXT)""")
con.execute("""CREATE TABLE skin_last_applied (
    steam_id TEXT, dino_class TEXT, actor_name TEXT, kind TEXT, payload TEXT,
    active INTEGER, updated_utc TEXT, recipe_digest TEXT)""")
# His T-Rex really is parked — that death must never be offered as lost.
con.execute("INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth, parked_at)"
            " VALUES (?,?,?,?,?)",
            (SID, "", "BP_Tyrannosaurus_C", 0.656, "2026-07-24T16:45:34.974906+00:00"))
con.execute("INSERT INTO skin_last_applied VALUES (?,?,?,?,?,?,?,?)",
            (SID, "BP_Carnotaurus_C", "BP_Carnotaurus_C_2147364519", "regular",
             json.dumps({"class": "BP_Carnotaurus_C", "steamid": SID,
                         "actor_name": "BP_Carnotaurus_C_2147364519", "pattern": 2,
                         "body": [0.67, 0.19, 0.02, 1.0], "preserve_female": True}),
             0, "2026-07-24T19:08:10Z", "sha256:x"))
con.commit()
con.close()

import game_ipc                                                    # noqa: E402
game_ipc.SAVED_DIR = SAVED
game_ipc.BOT_DB_PATH = VAULT_DB
game_ipc.PLAYERS_JSON = os.path.join(SAVED, "players.json")

import server                                                      # noqa: E402
import dino_recovery as dr                                         # noqa: E402
import httpx                                                       # noqa: E402

ADMIN = {"id": "admin-test", "persona_name": "test-admin", "role": "admin",
         "steam_id": "76561199532593593", "staff_rank": "owner"}
NON_ADMIN = {"id": "user-test", "persona_name": "plain", "role": "user", "steam_id": "1"}

server.app.dependency_overrides[server.get_admin_user] = lambda: ADMIN


async def main():
    db = server.db
    if db.name == "laislanublar":
        print("REFUSING: connected to the live database")
        return 2
    # Drop FIRST as well as last. A run that fails (or a mutation run that dies
    # mid-way) would otherwise leave claims and vault marks behind and poison
    # every later run with cascading count mismatches.
    await server.client.drop_database(db.name)
    server._park_mark_high_water = -1
    server._dino_snapshot_sigs.clear()
    await server.ensure_indexes()

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:

        # ---------- lookup ----------
        r = await c.get("/api/admin/recoverable", params={"q": SID})
        check("lookup: 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("lookup: found", bool(data["player"]["steam_id"]), json.dumps(data)[:200])
        check("lookup: steam id echoed", data["player"]["steam_id"] == SID)
        check("lookup: works with NO web account", data["player"]["has_account"] is False)
        lost = data["lost"]
        check("lookup: parked T-Rex excluded",
              all(l["species"] != "Tyrannosaurus" or l["ts"] != TREX_PARK_TS for l in lost))
        check("lookup: 4 lost dinos", len(lost) == 4, f"got {len(lost)}")
        check("lookup: newest first is the starved carno",
              lost[0]["species"] == "Carnotaurus" and lost[0]["cause"] == "starve")
        check("lookup: growth surfaced", lost[0]["growth_pct"] == 98, str(lost[0]["growth_pct"]))
        check("lookup: vault count shown beside it", data["vault_count"] == 1,
              str(data.get("vault_count")))
        check("lookup: nothing pre-marked recovered", all(not l["recovered"] for l in lost))
        check("lookup: at most 15", len(lost) <= 15)
        # No park ledger exists yet in a fresh DB, so nothing can be flagged.
        check("lookup: no ledger yet -> nothing flagged unverified",
              all(l["park_unverified"] is False for l in lost),
              str([l["park_unverified"] for l in lost]))

        r = await c.get("/api/admin/recoverable", params={"q": "   "})
        check("lookup: blank query is a clean 200, not a 500", r.status_code == 200)
        check("lookup: blank query says what to type",
              not r.json()["player"]["steam_id"] and bool(r.json().get("message")))
        r = await c.get("/api/admin/recoverable", params={"q": "76561199999999999"})
        check("lookup: unknown steam id -> found, empty list",
              r.status_code == 200 and r.json()["lost"] == [], r.text[:160])
        r = await c.get("/api/admin/recoverable",
                        params={"q": "https://steamcommunity.com/profiles/%s/" % SID})
        check("lookup: a pasted profile URL resolves", r.json()["player"]["steam_id"] == SID)
        r = await c.get("/api/admin/recoverable", params={"q": "  %s  " % SID})
        check("lookup: surrounding whitespace tolerated", r.json()["player"]["steam_id"] == SID)
        # A SteamID64 is exactly 17 digits; a longer run is not one, and keying a
        # vault row to it would hand the dino to an account that cannot exist.
        r = await c.get("/api/admin/recoverable", params={"q": SID + "999"})
        check("lookup: over-long digit run is NOT taken as a steam id",
              not r.json()["player"]["steam_id"], r.text[:160])
        r = await c.post("/api/admin/recover-dino",
                         json={"steam_id": SID + "999", "species": "Carnotaurus"})
        check("bad: over-long steam id refused by recover too",
              r.status_code == 400, str(r.status_code))

        # ---------- the recovery itself ----------
        key = lost[0]["death_key"]
        r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key})
        check("recover: 200", r.status_code == 200, r.text[:300])
        got = r.json()
        check("recover: species", got.get("dino") == "Carnotaurus", json.dumps(got)[:200])
        check("recover: growth reported", abs(float(got.get("growth", 0)) - 98.4) < 0.2, str(got.get("growth")))
        check("recover: skin restored", got.get("skin_restored") is True)
        check("recover: vault row id returned", isinstance(got.get("vault_row_id"), int))

        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        carnos = [x for x in rows if x["dino_class"] == "BP_Carnotaurus_C"]
        check("recover: the row really is in the vault", len(carnos) == 1, f"got {len(carnos)}")
        row = carnos[0]
        check("recover: growth stored", abs(float(row["growth"]) - 0.984) < 1e-6, str(row["growth"]))
        check("recover: vitals stored as the refill sentinel",
              float(row["health"]) == 0 and float(row["max_hunger"]) == 0)
        check("recover: skin_data stored", bool(str(row["skin_data"] or "").strip()))
        skin = json.loads(row["skin_data"])
        check("recover: skin carries no foreign actor", "actor_name" not in skin)
        check("recover: audit log written",
              await db.logs.count_documents({"action": "recover_dino", "target": SID}) == 1)

        # ---------- it can only happen once ----------
        r2 = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key})
        check("repeat: refused", r2.status_code == 400, str(r2.status_code))
        check("repeat: says already recovered", "ya fue recuperado" in r2.text, r2.text[:160])
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        check("repeat: no second row",
              len([x for x in rows if x["dino_class"] == "BP_Carnotaurus_C"]) == 1)

        r = await c.get("/api/admin/recoverable", params={"q": SID})
        after = r.json()["lost"]
        check("repeat: the list now flags it as returned",
              next(l for l in after if l["death_key"] == key)["recovered"] is True)
        check("repeat: the others stay available",
              sum(1 for l in after if not l["recovered"]) == 3)

        # two admins clicking the same dino at the same instant
        key2 = next(l["death_key"] for l in after if not l["recovered"])
        both = await asyncio.gather(
            c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key2}),
            c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key2}),
            return_exceptions=True)
        codes = sorted(x.status_code for x in both if hasattr(x, "status_code"))
        check("race: exactly one winner", codes == [200, 400], str(codes))
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        check("race: exactly one row was created",
              len([x for x in rows if x["dino_class"] == "BP_Carnotaurus_C"]) == 2,
              str(len(rows)))

        # ---------- bad input ----------
        r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": "nope"})
        check("bad: unknown death key -> 404", r.status_code == 404, str(r.status_code))
        r = await c.post("/api/admin/recover-dino", json={"death_key": "x"})
        check("bad: missing steam id -> 400", r.status_code == 400, str(r.status_code))
        r = await c.post("/api/admin/recover-dino", json={})
        check("bad: empty body -> 400 not 500", r.status_code == 400, str(r.status_code))
        r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "species": "Nope!!"})
        check("bad: junk species -> 400", r.status_code == 400, str(r.status_code))
        check("bad: junk species names itself in the error", "Nope!!" in r.text, r.text[:160])
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        check("bad: no unspawnable class reached the vault",
              all("Nope" not in str(x["dino_class"]) for x in rows))
        r = await c.post("/api/admin/recover-dino",
                         json={"steam_id": SID, "species": "Carnotaurus2"})
        check("bad: near-miss species -> 400", r.status_code == 400, str(r.status_code))
        # An admin typing lowercase must not be punished for it.
        r = await c.post("/api/admin/recover-dino",
                         json={"steam_id": SID, "species": "kentrosaurus", "growth": 40})
        check("manual: lowercase species accepted and canonicalised",
              r.status_code == 200, r.text[:160])
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        check("manual: stored with the canonical class",
              any(x["dino_class"] == "BP_Kentrosaurus_C" for x in rows),
              str([x["dino_class"] for x in rows]))

        # ---------- manual fallback ----------
        r = await c.post("/api/admin/recover-dino", json={
            "steam_id": SID, "species": "Dilophosaurus", "growth": 60,
            "is_prime": True, "mutations": "Osteosclerosis|None|None|None"})
        check("manual: 200", r.status_code == 200, r.text[:200])
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        dilo = [x for x in rows if x["dino_class"] == "BP_Dilophosaurus_C"]
        check("manual: row written", len(dilo) == 1)
        check("manual: growth", abs(float(dilo[0]["growth"]) - 0.6) < 1e-6, str(dilo[0]["growth"]))
        check("manual: prime honoured", int(dilo[0]["is_prime"]) == 1)
        check("manual: mutations honoured",
              dilo[0]["mutations"] == "Osteosclerosis|None|None|None")

        # ---------- a failed recovery must leave NOTHING claimed ----------
        before_claims = await db[dr.RECOVERY_COLLECTION].count_documents({})
        real_save = server.vault.save_parked
        server.vault.save_parked = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
        try:
            key3 = next(l["death_key"] for l in
                        (await c.get("/api/admin/recoverable", params={"q": SID})).json()["lost"]
                        if not l["recovered"])
            r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key3})
            check("rollback: vault failure -> 500", r.status_code == 500, str(r.status_code))
            check("rollback: claim released, not left behind",
                  await db[dr.RECOVERY_COLLECTION].count_documents({}) == before_claims,
                  "claims leaked")
        finally:
            server.vault.save_parked = real_save
        r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": key3})
        check("rollback: the same dino can be recovered after the failure",
              r.status_code == 200, r.text[:200])

        # ---------- at capacity ----------
        server.vault.save_parked = lambda *a, **k: None
        try:
            r = await c.post("/api/admin/recover-dino",
                             json={"steam_id": SID, "species": "Stegosaurus", "growth": 50})
            check("cap: refused with a readable reason", r.status_code == 400, str(r.status_code))
            check("cap: names the limit", "l\u00edmite" in r.text or "limite" in r.text, r.text[:160])
            check("cap: claim released",
                  await db[dr.RECOVERY_COLLECTION].count_documents({"status": "pending"}) == 0)
        finally:
            server.vault.save_parked = real_save

        # ---------- the snapshot loop is what carries mutations ----------
        with open(game_ipc.PLAYERS_JSON, "w", encoding="utf-8") as fh:
            json.dump({SID: {"steamid": SID, "dino": "BP_Allosaurus_C", "growth": 0.77,
                             "is_prime": True, "is_elder": False,
                             "mutations": "Osteosclerosis|None|None|None",
                             "parent_mutations": "None|None|None|None",
                             "elder_mutations": "None|None|None|None|None|None|None|None",
                             "elder_stacks": 0, "skin_code": "Allosaurus01",
                             "actor_name": "BP_Allosaurus_C_1"}}, fh)
        game_ipc._file_cache.clear()
        players = await asyncio.to_thread(game_ipc.read_players_json)
        snap = dr.snapshot_from_player_row(SID, players[SID])
        await db[dr.SNAPSHOT_COLLECTION].update_one({"steam_id": SID}, {"$set": snap}, upsert=True)
        with open(os.path.join(SAVED, "death_causes.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": snap["seen_at"] + 5, "sid": SID, "cause": "killed",
                                 "dino": "BP_Allosaurus_C", "growth": 0.77}) + "\n")
        r = await c.get("/api/admin/recoverable", params={"q": SID})
        allo = next(l for l in r.json()["lost"] if l["species"] == "Allosaurus")
        check("snapshot: mutations reach the list",
              allo["mutations_count"] == 1, str(allo["mutations_count"]))
        check("snapshot: prime reaches the list", allo["is_prime"] is True)
        check("snapshot: marked as a full record", allo["detail"] == "full")
        r = await c.post("/api/admin/recover-dino",
                         json={"steam_id": SID, "death_key": allo["death_key"]})
        check("snapshot: recovered with its mutations", r.status_code == 200, r.text[:200])
        rows = await asyncio.to_thread(server.vault.get_parked, SID)
        a_row = [x for x in rows if x["dino_class"] == "BP_Allosaurus_C"][0]
        check("snapshot: mutations landed in the vault row",
              a_row["mutations"] == "Osteosclerosis|None|None|None", a_row["mutations"])
        check("snapshot: prime landed", int(a_row["is_prime"]) == 1)

        # ---------- a park is never offered as lost --------------------------
        # A park that happened while the backend was DOWN must still be marked
        # on the first tick after it comes back, or the mark is lost forever and
        # the dino is offered as "lost" once the player redeems it.
        await asyncio.to_thread(
            server.vault.save_parked, SID, "", {"dino": "BP_Triceratops_C", "growth": 0.5}, 0)
        server._park_mark_high_water = -1
        await server._record_park_marks()
        check("marks: a park made while the backend was down IS marked on the first tick",
              await db[dr.PARK_MARK_COLLECTION].count_documents(
                  {"dino_class": "BP_Triceratops_C"}) == 1)
        tri = await db[dr.PARK_MARK_COLLECTION].find_one({"dino_class": "BP_Triceratops_C"})
        check("marks: the timestamp is the row's real parked_at, not 'now'",
              bool(tri) and tri.get("parked_at_ts", 0) > 0
              and abs(tri["parked_at_ts"] - int(time.time())) < 300,
              str(tri.get("parked_at_ts") if tri else "no mark written"))
        await asyncio.to_thread(
            server.vault.save_parked, SID, "", {"dino": "BP_Kentrosaurus_C", "growth": 0.5}, 0)
        await server._record_park_marks()
        check("marks: a NEW park is remembered",
              await db[dr.PARK_MARK_COLLECTION].count_documents({"dino_class": "BP_Kentrosaurus_C"}) == 1)
        await server._record_park_marks()
        check("marks: the tick is idempotent",
              await db[dr.PARK_MARK_COLLECTION].count_documents({"dino_class": "BP_Kentrosaurus_C"}) == 1)
        # The tracking set must not grow for the life of the process.
        rows_now = await asyncio.to_thread(server.vault.get_parked, SID)
        check("marks: high-water mark reached the newest row",
              server._park_mark_high_water == max(int(r["id"]) for r in rows_now),
              f'{server._park_mark_high_water} vs {max(int(r["id"]) for r in rows_now)}')
        # A recovery grant is not a park; marking it would let a grant
        # suppress a genuine death of the same species minutes later.
        granted_ids = [c["vault_row_id"] async for c in
                       db[dr.RECOVERY_COLLECTION].find({"vault_row_id": {"$exists": True}},
                                                       {"_id": 0, "vault_row_id": 1})]
        marked_ids = [m["vault_row_id"] async for m in
                      db[dr.PARK_MARK_COLLECTION].find({}, {"_id": 0, "vault_row_id": 1})]
        check("marks: rows created by the recovery lane are NOT marked as parks",
              not (set(granted_ids) & set(marked_ids)),
              f"overlap {sorted(set(granted_ids) & set(marked_ids))}")

        # Now that a park ledger exists, every death that predates it must be
        # flagged — those are the ones a redeemed park could be hiding in.
        server._park_ledger_start_ts = None       # recompute against the new marks
        r = await c.get("/api/admin/recoverable", params={"q": SID})
        flagged = r.json()["lost"]
        check("ledger: older deaths are flagged once parks are being recorded",
              flagged and all(l["park_unverified"] for l in flagged),
              str([(l["ts"], l["park_unverified"]) for l in flagged]))

        # ---------- a claim that died mid-flight must not wedge the dino -----
        wedged = "manual:%s:Wedged:1" % SID
        await db[dr.RECOVERY_COLLECTION].insert_one({
            "death_key": wedged, "steam_id": SID, "status": "pending",
            "created_at": "2020-01-01T00:00:00+00:00", "source": "test"})
        check("stale claim: recognised as takeable",
              server._recovery_claim_is_stale(
                  {"status": "pending", "created_at": "2020-01-01T00:00:00+00:00"}) is True)
        check("stale claim: a DONE claim is never takeable",
              server._recovery_claim_is_stale(
                  {"status": "done", "created_at": "2020-01-01T00:00:00+00:00"}) is False)
        check("stale claim: a FRESH pending claim is not takeable",
              server._recovery_claim_is_stale(
                  {"status": "pending", "created_at": now_iso_str()}) is False)
        check("stale claim: unreadable stamp never wedges the lane",
              server._recovery_claim_is_stale({"status": "pending", "created_at": "???"}) is True)

        # ---------- the index is NOT the only duplicate guard ----------------
        # If the unique index failed to build, a second click must still be
        # refused by the read-before-write check.
        await db[dr.RECOVERY_COLLECTION].drop_index("death_key_1")
        dropped_key = "manual:%s:GuardTest:1" % SID
        await db[dr.RECOVERY_COLLECTION].insert_one({
            "death_key": dropped_key, "steam_id": SID, "status": "done",
            "created_at": now_iso_str(), "source": "test"})
        before = len(await asyncio.to_thread(server.vault.get_parked, SID))
        try:
            await server._grant_recovered_dino(
                SID, dr.build_recovery_payload("BP_Carnotaurus_C", 0.5),
                death_key=dropped_key, admin=ADMIN, label="t", source="test")
            check("no-index: duplicate still refused", False, "it granted anyway")
        except Exception as e:
            check("no-index: duplicate still refused", getattr(e, "status_code", 0) == 400, str(e))
        after = len(await asyncio.to_thread(server.vault.get_parked, SID))
        check("no-index: no vault row was written", after == before, f"{before}->{after}")
        dupes = await db[dr.RECOVERY_COLLECTION].count_documents({"death_key": dropped_key})
        check("no-index: no duplicate claim was created", dupes == 1, f"{dupes} claims")
        # Rebuilding the unique index is itself the proof: it can only succeed if
        # nothing slipped through while the index was gone.
        try:
            await db[dr.RECOVERY_COLLECTION].create_index("death_key", unique=True)
            check("no-index: unique index rebuilds cleanly afterwards", True)
        except Exception as e:
            check("no-index: unique index rebuilds cleanly afterwards", False, str(e)[:120])
            await db[dr.RECOVERY_COLLECTION].delete_many({"death_key": dropped_key})
            await db[dr.RECOVERY_COLLECTION].create_index("death_key", unique=True)

        # ---------- a claim whose request died is taken over, not wedged -----
        # Without this the dino could NEVER be recovered again: the claim exists,
        # so every later attempt is refused as "already recovered".
        r = await c.get("/api/admin/recoverable", params={"q": SID})
        wedge_key = next((l["death_key"] for l in r.json()["lost"] if not l["recovered"]), None)
        check("stale claim: a lost dino is available to test with", bool(wedge_key))
        if wedge_key:
            await db[dr.RECOVERY_COLLECTION].insert_one({
                "death_key": wedge_key, "steam_id": SID, "status": "pending",
                "created_at": "2020-01-01T00:00:00+00:00", "source": "test-wedge"})
            before = len(await asyncio.to_thread(server.vault.get_parked, SID))
            r = await c.post("/api/admin/recover-dino",
                             json={"steam_id": SID, "death_key": wedge_key})
            check("stale claim: the route TAKES OVER and grants", r.status_code == 200,
                  r.text[:200])
            after = len(await asyncio.to_thread(server.vault.get_parked, SID))
            check("stale claim: the dino really reached the vault", after == before + 1,
                  f"{before}->{after}")
            claims = await db[dr.RECOVERY_COLLECTION].count_documents({"death_key": wedge_key})
            check("stale claim: exactly one claim remains", claims == 1, f"{claims}")
            doc = await db[dr.RECOVERY_COLLECTION].find_one({"death_key": wedge_key})
            check("stale claim: it is now marked done",
                  bool(doc) and doc.get("status") == "done",
                  str(doc.get("status") if doc else "no claim row"))
            # and a FRESH claim is still respected
            fresh_key = "manual:%s:FreshClaim:1" % SID
            await db[dr.RECOVERY_COLLECTION].insert_one({
                "death_key": fresh_key, "steam_id": SID, "status": "pending",
                "created_at": now_iso_str(), "source": "test-fresh"})
            try:
                await server._grant_recovered_dino(
                    SID, dr.build_recovery_payload("BP_Carnotaurus_C", 0.5),
                    death_key=fresh_key, admin=ADMIN, label="t", source="test")
                check("stale claim: a FRESH pending claim is still refused", False,
                      "it granted anyway")
            except Exception as e:
                check("stale claim: a FRESH pending claim is still refused",
                      getattr(e, "status_code", 0) == 400, str(e)[:120])

        # ---------- auth ----------
        server.app.dependency_overrides.pop(server.get_admin_user, None)
        r = await c.get("/api/admin/recoverable", params={"q": SID})
        check("auth: no admin -> not 200", r.status_code in (401, 403), str(r.status_code))
        r = await c.post("/api/admin/recover-dino", json={"steam_id": SID, "death_key": "x"})
        check("auth: recover is gated too", r.status_code in (401, 403), str(r.status_code))
        server.app.dependency_overrides[server.get_admin_user] = lambda: ADMIN

    # ---------- zero residual ----------
    await server.client.drop_database(db.name)
    print("\ndropped scratch database %s" % db.name)
    return 0


rc = asyncio.run(main())
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d passed, %d failed" % (PASS, len(FAIL)))
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if (FAIL or rc) else 0)
