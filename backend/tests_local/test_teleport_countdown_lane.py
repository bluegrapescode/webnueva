"""Self-executing ON-BOX lane test (needs the backend venv: fastapi installed).

    C:\\LaIslaNublar\\venv\\Scripts\\python.exe tests_local\\test_teleport_countdown_lane.py

Exercises the 2026-07-18 teleport hold machinery INSIDE server.py with a fake
Mongo layer and a fake game_ipc — zero prod contact, zero real writes:

  * stamina gate: <=60% refused (named %), >60% passes; unreadable bars fail closed
  * accept flips pending -> countdown with base positions
  * runner: standing still -> mod teleport command written -> completed
  * runner: requester moves past tolerance -> cancelled, reason NAMES the mover
  * runner: player row vanishes 4 samples -> cancelled ("señal")
  * runner: mod write fails -> cancelled (game down)
  * user cancel mid-hold beats the runner (CAS)
  * lazy cleanup cancels orphaned countdown rows

and the 2026-07-29 30-minute cooldown:

  * default is 1800s; the env knob overrides it; 0 disables
  * remaining time is said in minutes, rounded up, and never "1 minutos"
  * a junk / missing stamp reads as READY, never as locked out forever
  * the window is CLAIMED before the mod command goes out, so two accepted
    requests from the same player can only ever buy ONE teleport
  * a teleport that never reaches the game hands the window straight back
  * the friends payload carries the caller's own remaining seconds
  * _market_verify_view exposes verification facts but never seller-private keys
  * perk gates: plain role=admin staff are NOT subscribers/patreon-bypassed; owner is
"""
import asyncio
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

# Seed required env BEFORE importing server (mirror the on-box .env contract).
_ENV_PATH = os.path.join(BACKEND, ".env")
if os.path.isfile(_ENV_PATH):
    for ln in open(_ENV_PATH, "r", encoding="utf-8-sig"):
        ln = ln.strip()
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k, v.strip())
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "laislanublar")
os.environ.setdefault("JWT_SECRET", "lane-test")

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


class FakeCursorList(list):
    pass


def _field_match(row, key, cond):
    """One field against one Mongo-ish condition. Only the operators this lane
    actually uses are implemented — an unknown operator returns False rather
    than matching, so a query the fake cannot model fails loudly."""
    if isinstance(cond, dict):
        for op, val in cond.items():
            if op == "$exists":
                if bool(val) != (key in row):
                    return False
            elif op == "$in":
                if row.get(key) not in val:
                    return False
            elif op in ("$lte", "$lt", "$gte", "$gt"):
                rv = row.get(key)
                if rv is None:
                    return False
                try:
                    a, b = float(rv), float(val)
                except (TypeError, ValueError):
                    return False
                if op == "$lte" and not a <= b:
                    return False
                if op == "$lt" and not a < b:
                    return False
                if op == "$gte" and not a >= b:
                    return False
                if op == "$gt" and not a > b:
                    return False
            else:
                return False
        return True
    # Mongo: {field: None} matches a null value AND a missing key — row.get does
    # the same, so an absent stamp is matched by the claim filter exactly as it
    # would be in prod.
    return row.get(key) == cond


def _doc_match(row, q):
    for k, v in q.items():
        if k == "$or":
            if not any(_doc_match(row, c) for c in v):
                return False
        elif k == "$and":
            if not all(_doc_match(row, c) for c in v):
                return False
        elif not _field_match(row, k, v):
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.rows = {}

    async def find_one(self, q, proj=None):
        for r in self.rows.values():
            if _doc_match(r, q):
                return dict(r)
        return None

    async def update_one(self, q, upd):
        matched = 0
        modified = 0
        for r in self.rows.values():
            m = True
            for k, v in q.items():
                if isinstance(v, dict) and "$in" in v:
                    if r.get(k) not in v["$in"]:
                        m = False
                elif isinstance(v, dict):
                    m = False
                elif r.get(k) != v:
                    m = False
            if m:
                matched += 1
                for k, v in (upd.get("$set") or {}).items():
                    r[k] = v
                for k in (upd.get("$unset") or {}):
                    r.pop(k, None)
                modified += 1
                break
        res = types.SimpleNamespace(matched_count=matched, modified_count=modified)
        return res

    async def find_one_and_update(self, q, upd, projection=None, **kw):
        """pymongo default: returns the document as it was BEFORE the update, or
        None when nothing matched — which is exactly how the cooldown claim
        tells 'I won the window' from 'someone else already has it'."""
        for r in self.rows.values():
            if not _doc_match(r, q):
                continue
            before = dict(r)
            for k, v in (upd.get("$set") or {}).items():
                r[k] = v
            for k in (upd.get("$unset") or {}):
                r.pop(k, None)
            if projection:
                keep = {k for k, v in projection.items() if v and k != "_id"}
                before = {k: v for k, v in before.items() if k in keep}
            return before
        return None

    async def insert_one(self, doc):
        self.rows[doc.get("id") or str(len(self.rows))] = dict(doc)
        return types.SimpleNamespace(inserted_id=doc.get("id"))

    async def update_many(self, q, upd):
        n = 0
        now_lt = None
        st = q.get("status")
        cd = q.get("countdown_ends_at")
        if isinstance(cd, dict):
            now_lt = cd.get("$lt")
        for r in self.rows.values():
            if st and r.get("status") != st:
                continue
            if now_lt is not None and not (float(r.get("countdown_ends_at") or 0) < now_lt):
                continue
            for k, v in (upd.get("$set") or {}).items():
                r[k] = v
            n += 1
        return types.SimpleNamespace(matched_count=n, modified_count=n)

    async def delete_many(self, q):
        return types.SimpleNamespace(deleted_count=0)

    def find(self, q, proj=None):
        rows = [dict(r) for r in self.rows.values()]

        class _F:
            def __init__(self, rr):
                self.rr = rr

            def sort(self, *a, **k):
                return self

            async def to_list(self, n):
                return self.rr

        # crude $or side filter for the lists query
        if "$or" in q:
            keep = []
            for r in rows:
                for cond in q["$or"]:
                    if all(r.get(k) == v for k, v in cond.items()):
                        keep.append(r)
                        break
            rows = keep
        return _F(rows)


async def main():
    import server

    fake_db = types.SimpleNamespace(
        teleport_requests=FakeCollection(),
        users=FakeCollection(),
        friends=FakeCollection(),
    )
    server.db = fake_db

    # fake game_ipc: scripted per-sid rows + captured commands
    rows = {}
    written = []

    def read_player(sid, force_fresh=False):
        v = rows.get(str(sid))
        return dict(v) if isinstance(v, dict) else None

    def write_game_command(cmd):
        written.append(dict(cmd))
        return write_game_command.ok

    write_game_command.ok = True
    server.game_ipc.read_player = read_player
    server.game_ipc.write_game_command = write_game_command

    def live(sid, x=0.0, stamina=900.0):
        rows[sid] = {"actor_name": f"A{sid[-2:]}", "dino": "BP_Tyrannosaurus_C",
                     "x": x, "y": 0.0, "z": 0.0,
                     "stamina": stamina, "max_stamina": 900.0,
                     "health": 5000.0, "max_health": 5000.0,
                     "last_updated": time.time()}

    # ── stamina gate ─────────────────────────────────────────────────────────
    from fastapi import HTTPException
    live("901", stamina=540.0)  # exactly 60%
    try:
        server._teleport_stamina_gate(rows["901"])
        check("stamina 60% refused", False)
    except HTTPException as e:
        check("stamina 60% refused", "60%" in str(e.detail) and "Energ" in str(e.detail), e.detail)
    live("901", stamina=550.0)  # ~61%
    try:
        server._teleport_stamina_gate(rows["901"])
        check("stamina 61% passes", True)
    except HTTPException as e:
        check("stamina 61% passes", False, e.detail)
    try:
        server._teleport_stamina_gate({"stamina": 1, "max_stamina": 0})
        check("unreadable stamina fails closed", False)
    except HTTPException:
        check("unreadable stamina fails closed", True)

    # ── countdown runner: happy path ─────────────────────────────────────────
    def seed_countdown(rid, secs=1.2):
        now = time.time()
        fake_db.teleport_requests.rows[rid] = {
            "id": rid, "status": "countdown",
            "requester_id": "u1", "target_id": "u2",
            "requester_name": "Reque", "target_name": "Targe",
            "requester_sid": "901", "target_sid": "902",
            "countdown_started_at": now, "countdown_ends_at": now + secs,
            "countdown_base": {"requester": {"x": 0.0, "y": 0.0, "z": 0.0},
                               "target": {"x": 500.0, "y": 0.0, "z": 0.0}},
        }
        fake_db.users.rows["u1"] = {"id": "u1"}

    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    seed_countdown("t1")
    await server._teleport_countdown_runner("t1")
    r = fake_db.teleport_requests.rows["t1"]
    check("still -> completed", r.get("status") == "completed", r.get("status"))
    check("teleport command written", written and written[0]["type"] == "teleport"
          and written[0]["steamid"] == "901", repr(written))
    check("dest = target current pos + offset",
          written and abs(written[0]["x"] - 620.0) < 1e-6, repr(written))
    check("cooldown window claimed for the teleport",
          "teleport_last_at" in fake_db.users.rows["u1"])

    # ── mover cancels, reason names the mover ────────────────────────────────
    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    seed_countdown("t2", secs=3.0)

    async def move_soon():
        await asyncio.sleep(0.4)
        live("901", x=400.0)  # requester takes a real step (400 uu > 150)

    await asyncio.gather(server._teleport_countdown_runner("t2"), move_soon())
    r = fake_db.teleport_requests.rows["t2"]
    check("mover -> cancelled", r.get("status") == "cancelled", r.get("status"))
    check("reason names mover", "Reque" in str(r.get("cancel_reason")), r.get("cancel_reason"))
    check("no command after cancel", not written, repr(written))

    # ── vanished row -> señal perdida ────────────────────────────────────────
    live("901", x=0.0)
    live("902", x=500.0)
    seed_countdown("t3", secs=8.0)
    rows.pop("902")
    t0 = time.time()
    await server._teleport_countdown_runner("t3")
    r = fake_db.teleport_requests.rows["t3"]
    check("lost signal -> cancelled", r.get("status") == "cancelled", r.get("status"))
    check("señal reason", "señal" in str(r.get("cancel_reason")).lower(), r.get("cancel_reason"))
    check("cancelled before full hold", time.time() - t0 < 7.5)

    # ── mod down at fire time ────────────────────────────────────────────────
    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    write_game_command.ok = False
    seed_countdown("t4", secs=0.8)
    await server._teleport_countdown_runner("t4")
    r = fake_db.teleport_requests.rows["t4"]
    check("mod-down -> cancelled", r.get("status") == "cancelled", r.get("status"))
    write_game_command.ok = True

    # ── user cancel mid-hold wins ────────────────────────────────────────────
    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    seed_countdown("t5", secs=2.5)

    async def user_cancel_soon():
        await asyncio.sleep(0.4)
        fake_db.teleport_requests.rows["t5"]["status"] = "cancelled"
        fake_db.teleport_requests.rows["t5"]["cancel_reason"] = "Cancelado a mano"

    await asyncio.gather(server._teleport_countdown_runner("t5"), user_cancel_soon())
    r = fake_db.teleport_requests.rows["t5"]
    check("manual cancel sticks", r.get("status") == "cancelled" and not written,
          f"{r.get('status')} written={written!r}")

    # ── orphan cleanup in _teleport_lists ────────────────────────────────────
    now = time.time()
    fake_db.teleport_requests.rows["t6"] = {
        "id": "t6", "status": "countdown", "requester_id": "u1", "target_id": "u2",
        "requester_name": "Reque", "target_name": "Targe",
        "countdown_ends_at": now - 60,
    }
    tp_in, tp_out, tp_live = await server._teleport_lists("u1")
    r = fake_db.teleport_requests.rows["t6"]
    check("orphan countdown cancelled", r.get("status") == "cancelled", r.get("status"))
    check("tp_live carries outcome rows",
          any(t["id"] == "t6" and t["status"] == "cancelled" for t in tp_live), repr(tp_live))

    # ── 30-MINUTE COOLDOWN (owner ruling 2026-07-29) ─────────────────────────
    os.environ.pop("LIN_TELEPORT_COOLDOWN_SECS", None)
    check("default cooldown is 30 minutes", server._teleport_cooldown_secs() == 1800,
          repr(server._teleport_cooldown_secs()))
    os.environ["LIN_TELEPORT_COOLDOWN_SECS"] = "90"
    check("the env knob still overrides it", server._teleport_cooldown_secs() == 90)
    os.environ["LIN_TELEPORT_COOLDOWN_SECS"] = "0"
    check("0 still disables the cooldown", server._teleport_cooldown_secs() == 0)
    os.environ["LIN_TELEPORT_COOLDOWN_SECS"] = "media hora"
    check("junk in the knob falls back to 30 minutes", server._teleport_cooldown_secs() == 1800)
    os.environ["LIN_TELEPORT_COOLDOWN_SECS"] = "   "
    check("a blank knob falls back to 30 minutes", server._teleport_cooldown_secs() == 1800)
    os.environ.pop("LIN_TELEPORT_COOLDOWN_SECS", None)

    tnow = time.time()
    check("a player who never teleported is ready", server._teleport_cooldown_left({}) == 0)
    check("a junk stamp reads as READY, never locked out forever",
          server._teleport_cooldown_left({"teleport_last_at": "ayer"}) == 0)
    check("a non-finite stamp reads as READY",
          server._teleport_cooldown_left({"teleport_last_at": float("inf")}) == 0)
    check("a stamp older than the window is ready",
          server._teleport_cooldown_left({"teleport_last_at": tnow - 1801}) == 0)
    left10 = server._teleport_cooldown_left({"teleport_last_at": tnow - 600})
    check("10 minutes ago leaves ~20 minutes", 1195 <= left10 <= 1200, repr(left10))

    check("phrase: 1799s is '30 minutos'", server._teleport_wait_phrase(1799) == "30 minutos",
          server._teleport_wait_phrase(1799))
    check("phrase: 60s is '1 minuto'", server._teleport_wait_phrase(60) == "1 minuto",
          server._teleport_wait_phrase(60))
    check("phrase: 61s rounds UP and never says '1 minutos'",
          server._teleport_wait_phrase(61) == "2 minutos", server._teleport_wait_phrase(61))
    check("phrase: under a minute stays in seconds",
          server._teleport_wait_phrase(45) == "45 segundos", server._teleport_wait_phrase(45))
    check("phrase: 1s is singular", server._teleport_wait_phrase(1) == "1 segundo",
          server._teleport_wait_phrase(1))

    # request route: refused, and the refusal is readable
    live("901", x=0.0)
    live("902", x=500.0)
    fake_db.friends.rows["f1"] = {"requester_id": "u1", "addressee_id": "u2", "status": "accepted"}
    u1_cooling = {"id": "u1", "steam_id": "901", "persona_name": "Reque",
                  "teleport_last_at": time.time() - 60}
    fake_db.users.rows["u1"] = dict(u1_cooling)
    fake_db.users.rows["u2"] = {"id": "u2", "steam_id": "902", "persona_name": "Targe"}
    try:
        await server.friends_teleport_request(types.SimpleNamespace(user_id="u2"),
                                              user=dict(u1_cooling))
        check("request refused during the cooldown", False, "the request went through")
    except HTTPException as e:
        check("request refused during the cooldown", e.status_code == 429, repr(e.status_code))
        check("...and says the wait in minutes, not raw seconds",
              "minutos" in str(e.detail) and "segundos" not in str(e.detail), e.detail)

    # accept route: the burst is refused up front, by name
    fake_db.teleport_requests.rows["a1"] = {
        "id": "a1", "status": "pending", "requester_id": "u1", "target_id": "u2",
        "requester_name": "Reque", "target_name": "Targe",
        "expires_at": time.time() + 120}
    try:
        await server.friends_teleport_respond(
            types.SimpleNamespace(request_id="a1", accept=True),
            user=dict(fake_db.users.rows["u2"]))
        check("accept refused while the requester is cooling down", False, "accept went through")
    except HTTPException as e:
        check("accept refused while the requester is cooling down", e.status_code == 429,
              repr(e.status_code))
        check("...and the refusal names the player who is waiting",
              "Reque" in str(e.detail), e.detail)
    fake_db.teleport_requests.rows.pop("a1", None)

    # THE BURST: two accepted requests in flight for the SAME player
    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    seed_countdown("b1", secs=0.6)
    seed_countdown("b2", secs=0.6)          # re-seeds u1 with no stamp: window is open
    await asyncio.gather(server._teleport_countdown_runner("b1"),
                         server._teleport_countdown_runner("b2"))
    b_rows = [fake_db.teleport_requests.rows["b1"], fake_db.teleport_requests.rows["b2"]]
    done = [r for r in b_rows if r.get("status") == "completed"]
    lost = [r for r in b_rows if r.get("status") == "cancelled"]
    check("a burst of accepted requests buys exactly ONE teleport", len(done) == 1,
          repr([r.get("status") for r in b_rows]))
    check("...and exactly one mod command goes out",
          len([c for c in written if c.get("type") == "teleport"]) == 1, repr(written))
    check("...the loser is cancelled, with a reason the player can read",
          len(lost) == 1 and "teletransporte" in str(lost[0].get("cancel_reason")).lower(),
          repr(lost and lost[0].get("cancel_reason")))

    # a teleport that never reaches the game hands the window straight back
    live("901", x=0.0)
    live("902", x=500.0)
    written.clear()
    write_game_command.ok = False
    seed_countdown("r1", secs=0.6)
    await server._teleport_countdown_runner("r1")
    check("mod down -> cancelled (again, with the claim in play)",
          fake_db.teleport_requests.rows["r1"].get("status") == "cancelled")
    check("a teleport that never fired RELEASES the cooldown",
          "teleport_last_at" not in fake_db.users.rows["u1"], repr(fake_db.users.rows["u1"]))
    old_stamp = time.time() - 5000
    seed_countdown("r2", secs=0.6)
    fake_db.users.rows["u1"] = {"id": "u1", "teleport_last_at": old_stamp}
    await server._teleport_countdown_runner("r2")
    check("...and an earlier stamp is put back exactly, not refreshed",
          abs(float(fake_db.users.rows["u1"].get("teleport_last_at", 0)) - old_stamp) < 1e-6,
          repr(fake_db.users.rows["u1"]))
    write_game_command.ok = True

    # the dock is told how long is left, so it never has to guess
    fake_db.friends.rows.clear()
    payload = await server.friends_list(
        user={"id": "u1", "steam_id": "901", "teleport_last_at": time.time() - 300})
    check("the friends payload carries the caller's own remaining seconds",
          1495 <= int(payload.get("tp_cooldown_left") or 0) <= 1500,
          repr(payload.get("tp_cooldown_left")))
    ready = await server.friends_list(user={"id": "u1", "steam_id": "901"})
    check("...and 0 for a player who is ready", ready.get("tp_cooldown_left") == 0,
          repr(ready.get("tp_cooldown_left")))

    # ── market verify view ───────────────────────────────────────────────────
    vp = {"id": 7, "steam_id": "76561190000000001", "discord_id": "d", "dino_class": "BP_Carnotaurus_C",
          "growth": 0.9, "health": 100, "max_health": 200, "stamina": 1, "max_stamina": 2,
          "hunger": 1, "max_hunger": 2, "thirst": 1, "max_thirst": 2, "oxygen": 1, "max_oxygen": 2,
          "x": 111.0, "y": 222.0, "z": 333.0, "is_prime": 1, "is_elder": 0,
          "mutations": "Titan|None|Feral", "parent_mutations": "None", "elder_mutations": "",
          "elder_stacks": 0, "skin_code": "SECRET", "skin_data": "", "diet_a": 1, "diet_b": 2, "diet_c": 3,
          "parked_at": "2026-07-18T00:00:00+00:00", "redeem_pending_cmd_id": ""}
    v = server._market_verify_view(vp)
    check("verify shaped", isinstance(v, dict) and v.get("mutations") == "Titan|None|Feral", repr(v)[:120])
    private_leak = [k for k in ("steam_id", "discord_id", "skin_code", "x", "y", "z", "id",
                                "redeem_pending", "parked_at") if k in (v or {})]
    check("verify leaks nothing private", not private_leak, repr(private_leak))
    check("verify malformed -> None", server._market_verify_view({"id": "not-an-int"}) is None)

    # ── perk gates owner-only ────────────────────────────────────────────────
    staff = {"role": "admin", "staff_rank": "admin", "steam_id": "7656000", "id": "s1"}
    owner = {"role": "admin", "staff_rank": "owner", "steam_id": "7656000", "id": "o1"}
    check("staff not subscriber", server._is_subscriber(staff) is False)
    check("owner is subscriber", server._is_subscriber(owner) is True)
    acc_staff = await server._patreon_access(dict(staff))
    check("staff no patreon bypass", acc_staff.get("via") != "admin" and not acc_staff.get("allowed"),
          repr({k: acc_staff.get(k) for k in ("via", "allowed")}))
    acc_owner = await server._patreon_access(dict(owner))
    check("owner keeps bypass", acc_owner.get("via") == "admin" and acc_owner.get("allowed"))
    g_staff = server._swap_growth_for(staff)
    check("staff swap growth not admin-tier", g_staff[1] != "Admin", repr(g_staff))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    asyncio.run(main())
