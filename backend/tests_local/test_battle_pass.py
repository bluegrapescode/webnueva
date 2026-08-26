# -*- coding: utf-8 -*-
"""Pase de Batalla gate — tracks, claims, tokens, Stripe webhook, settle, XP hooks.

Drives the REAL backend/battle_pass.py against a REAL sqlite parked_dinos table
(the vault lane) and a motor-shaped fake Mongo that enforces the unique indexes
the module relies on — a fake without unique keys would have passed the
double-claim test while the product silently paid twice.

Nothing here contacts the game, Stripe, Discord or prod: the four Stripe seams
and the two game_ipc seams are swapped for recorders, and the Discord role lane
is a no-op because no bot token is configured in this process.

Run: python backend/tests_local/test_battle_pass.py   (or pytest)
"""
import asyncio
import inspect
import os
import re
import sqlite3
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

# ---- env + driver stubs BEFORE importing the backend ------------------------
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "lin_bp_test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ.pop("DISCORD_BOT_TOKEN", None)
os.environ.pop("BP_ROLE_REGULAR", None)
os.environ.pop("BP_ROLE_PREMIUM", None)

# pymongo is not installed in this sandbox; battle_pass only needs the sentinel
# and the duplicate-key type. ★Keep in step with battle_pass.py's import line.
_pymongo = types.ModuleType("pymongo")
_pymongo.ReturnDocument = types.SimpleNamespace(AFTER="after", BEFORE="before")
_pymongo_errors = types.ModuleType("pymongo.errors")


class DuplicateKeyError(Exception):
    pass


_pymongo_errors.DuplicateKeyError = DuplicateKeyError
_pymongo.errors = _pymongo_errors
sys.modules.setdefault("pymongo", _pymongo)
sys.modules.setdefault("pymongo.errors", _pymongo_errors)

# ---- temp vault DB, wired before vault/battle_pass first connect -------------
_TMP = tempfile.mkdtemp(prefix="lin_bp_test_")
_DB_PATH = os.path.join(_TMP, "laislanublar.db")
_SAVED = os.path.join(_TMP, "Saved")
os.makedirs(_SAVED, exist_ok=True)


def _make_vault_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE parked_dinos (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             steam_id TEXT, discord_id TEXT, dino_class TEXT, growth REAL,
             health REAL, max_health REAL, stamina REAL, max_stamina REAL,
             hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL,
             oxygen REAL, max_oxygen REAL, x REAL, y REAL, z REAL,
             is_prime INTEGER, is_elder INTEGER, mutations TEXT,
             parent_mutations TEXT, elder_mutations TEXT, elder_stacks INTEGER,
             skin_code TEXT, skin_data TEXT, diet_a REAL, diet_b REAL, diet_c REAL,
             parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at INTEGER)""")
    conn.commit()
    conn.close()


_make_vault_db(_DB_PATH)

import game_ipc  # noqa: E402

game_ipc.BOT_DB_PATH = _DB_PATH
game_ipc.SAVED_DIR = _SAVED

import glitch_catalog  # noqa: E402
import mutation_catalog  # noqa: E402
import seed_data  # noqa: E402
import vault  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import battle_pass as bp  # noqa: E402

vault.ensure_prime_state_columns()
vault.ensure_custom_name_column()

SID = "76561199000000042"
SID2 = "76561199000000043"

failures = []
passes = [0]


def check(name, cond, detail=""):
    if cond:
        passes[0] += 1
        print(f"  ok   {name}")
    else:
        failures.append(name)
        print(f"FAIL   {name}  {detail}")


# =============================================================================
# motor-shaped fake Mongo WITH unique-index enforcement
# =============================================================================
_MISSING = object()


def _match(doc, query):
    for k, cond in (query or {}).items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = doc.get(k, _MISSING)
        if isinstance(cond, dict) and any(str(op).startswith("$") for op in cond):
            for op, arg in cond.items():
                if op == "$exists":
                    if bool(arg) != (k in doc):
                        return False
                elif op == "$ne":
                    if val == arg:
                        return False
                elif op == "$in":
                    if val is _MISSING or val not in arg:
                        return False
                elif op == "$nin":
                    if val is not _MISSING and val in arg:
                        return False
                elif op == "$gt":
                    if val is _MISSING or not (val > arg):
                        return False
                elif op == "$gte":
                    if val is _MISSING or not (val >= arg):
                        return False
                elif op == "$regex":
                    flags = re.I if "i" in str(cond.get("$options") or "") else 0
                    if val is _MISSING or not re.search(str(arg), str(val), flags):
                        return False
                elif op == "$options":
                    continue  # consumed by $regex above
                else:
                    # An operator the fake cannot model fails LOUDLY rather than
                    # matching everything and turning a guard into a no-op.
                    raise AssertionError(f"fake db cannot model operator {op!r}")
        else:
            if val is _MISSING or val != cond:
                return False
    return True


def _apply_update(doc, update, inserted=False):
    for op, fields in (update or {}).items():
        if op == "$set":
            doc.update(fields)
        elif op == "$inc":
            for f, n in fields.items():
                doc[f] = (doc.get(f) or 0) + n
        elif op == "$unset":
            for f in fields:
                doc.pop(f, None)
        elif op == "$setOnInsert":
            if inserted:
                for f, v in fields.items():
                    doc.setdefault(f, v)
        elif op == "$addToSet":
            for f, v in fields.items():
                cur = list(doc.get(f) or [])
                if v not in cur:
                    cur.append(v)
                doc[f] = cur
        else:
            raise AssertionError(f"fake db cannot model update op {op!r}")


def _project(doc, projection):
    if not projection:
        return dict(doc)
    include = {k for k, v in projection.items() if v and k != "_id"}
    if include:
        return {k: v for k, v in doc.items() if k in include}
    return {k: v for k, v in doc.items() if k != "_id"}


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: (d.get(key) is None, d.get(key)),
                        reverse=(direction < 0))
        return self

    async def to_list(self, n=None):
        return self._docs if n is None else self._docs[:n]


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.docs = []
        self.unique = []          # [(field, field, ...), ...]

    async def create_index(self, keys, unique=False, name=None, **kw):
        if isinstance(keys, str):
            fields = (keys,)
        else:
            fields = tuple(k[0] for k in keys)
        if unique:
            self.unique.append(fields)
        return name or "_".join(fields)

    def _violates_unique(self, doc, skip=None):
        for fields in self.unique:
            key = tuple(doc.get(f) for f in fields)
            if any(v is None for v in key):
                continue
            for other in self.docs:
                if other is skip:
                    continue
                if tuple(other.get(f) for f in fields) == key:
                    return True
        return False

    async def insert_one(self, doc):
        d = dict(doc)
        if self._violates_unique(d):
            raise DuplicateKeyError(f"duplicate key on {self.name}")
        self.docs.append(d)
        return types.SimpleNamespace(inserted_id=d.get("id"))

    async def find_one(self, query=None, projection=None, sort=None):
        for d in self.docs:
            if _match(d, query or {}):
                return _project(d, projection)
        return None

    def find(self, query=None, projection=None):
        return _Cursor([_project(d, projection) for d in self.docs if _match(d, query or {})])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                _apply_update(d, update, inserted=False)
                return types.SimpleNamespace(modified_count=1, matched_count=1)
        if upsert:
            nd = {k: v for k, v in (query or {}).items() if not isinstance(v, dict)}
            _apply_update(nd, update, inserted=True)
            if self._violates_unique(nd):
                raise DuplicateKeyError(f"duplicate key on {self.name}")
            self.docs.append(nd)
            return types.SimpleNamespace(modified_count=0, matched_count=0, upserted_id=nd.get("id"))
        return types.SimpleNamespace(modified_count=0, matched_count=0)

    async def find_one_and_update(self, query, update, projection=None,
                                  return_document="before", upsert=False, **kw):
        for d in self.docs:
            if _match(d, query):
                before = dict(d)
                _apply_update(d, update, inserted=False)
                after = dict(d)
                return _project(after if return_document == "after" else before, projection)
        return None

    async def find_one_and_delete(self, query, projection=None):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                self.docs.pop(i)
                return _project(d, projection)
        return None

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                self.docs.pop(i)
                return types.SimpleNamespace(deleted_count=1)
        return types.SimpleNamespace(deleted_count=0)

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _match(d, query or {}))


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getattr__(self, name):
        c = self.__dict__.setdefault("_c", {})
        if name not in c:
            c[name] = FakeCollection(name)
        return c[name]


TX = []
LOGS = []
PARK_CAP = [0]


async def _fake_add_transaction(user_id, currency, amount, ttype, description):
    TX.append({"user_id": user_id, "currency": currency, "amount": amount,
               "type": ttype, "description": description})


async def _fake_add_log(actor, action, target=None, meta=None):
    LOGS.append({"actor": actor, "action": action, "target": target, "meta": meta})


async def _fake_user_dep(creds=None):
    raise HTTPException(401, "unused in unit tests")


async def _fake_admin_dep(user):
    if (user or {}).get("role") != "admin":
        raise HTTPException(403, "Acceso de administrador requerido")
    return user


def fresh_db():
    d = FakeDB()
    bp.configure(d, current_user_dep=_fake_user_dep, admin_user_dep=_fake_admin_dep,
                 add_transaction=_fake_add_transaction, add_log=_fake_add_log,
                 park_cap=lambda u: PARK_CAP[0])
    return d


async def seed_indexes(d):
    await bp.ensure_indexes()


async def mk_user(d, uid="u1", sid=SID, role="user", **kw):
    doc = {"id": uid, "steam_id": sid, "persona_name": uid, "role": role,
           "coins": 0, "vip_coins": 0, "xp": 0}
    doc.update(kw)
    await d.users.insert_one(doc)
    return await d.users.find_one({"id": uid}, {"_id": 0})


async def set_xp(d, uid, xp, season=None, tier=None, source=None):
    season = season or bp.current_season_id()
    await bp._get_pass(uid, season)
    upd = {"xp": int(xp)}
    if tier:
        upd["tier"] = tier
        upd["tier_source"] = source or "gift"
    await d.bp_passes.update_one({"user_id": uid, "season": season}, {"$set": upd})


def _wipe_vault():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("DELETE FROM parked_dinos")
    conn.commit()
    conn.close()


def _park(sid=SID, growth=0.30, prime=0, diet=(0.0, 0.0, 0.0), routes=None,
          cls="BP_Carnotaurus_C"):
    pd = {"dino": cls, "growth": growth, "is_prime": bool(prime), "is_elder": bool(prime),
          "mutations": "None|None|None|None", "parent_mutations": "None|None|None|None",
          "elder_mutations": "", "diet_a": diet[0], "diet_b": diet[1], "diet_c": diet[2]}
    row_id = vault.save_parked(sid, "d1", pd, 0)
    if routes is not None:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("UPDATE parked_dinos SET prime_route_mig = ?, prime_route_pat = ? WHERE id = ?",
                     (routes[0], routes[1], row_id))
        conn.commit()
        conn.close()
    return row_id


def _row(row_id):
    return vault.get_parked_by_id(int(row_id))


class FakeRequest:
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    async def body(self):
        return self._body


# =============================================================================
# 1. Row tables — the owner's exact numbers (v2 model, 2026-08-07)
#
#   REGULAR row  ($5)   1.000.000 PM + 3.000 AMB, 12 mutations (3 per dino,
#                       non-prime), 20 empty cells
#   PREMIUM row  ($10)  1.000.000 PM + 3.000 AMB, 16 mutations (4 per dino,
#                       PRIME),  0 empty cells
#   a Premium+ buyer claims BOTH -> 2.000.000 PM + 6.000 AMB, 28 mutations
#   (owner order 2026-08-08: 3 random mutations non-prime, 4 prime)
#   NOBODY claims anything without buying. There is no free row.
# =============================================================================
def case_row_totals_exact():
    for track in ("regular", "premium"):
        cells = bp.get_track(track)
        pm = [c["amount"] for c in cells if c["type"] == "coins"]
        amb = [c["amount"] for c in cells if c["type"] == "amber"]
        check(f"{track} row totals 1.000.000 PrimeMeat", sum(pm) == 1_000_000, str(sum(pm)))
        check(f"{track} row totals 3.000 Amberium", sum(amb) == 3_000, str(sum(amb)))
        check(f"{track} row currency cells are all integers",
              all(isinstance(v, int) for v in pm + amb))
        check(f"{track} row is 100 levels", len(cells) == 100, str(len(cells)))
    reg, pre = bp.get_track("regular"), bp.get_track("premium")
    both_pm = sum(c["amount"] for c in reg + pre if c["type"] == "coins")
    both_amb = sum(c["amount"] for c in reg + pre if c["type"] == "amber")
    check("BOTH rows together total 2.000.000 PrimeMeat", both_pm == 2_000_000, str(both_pm))
    check("BOTH rows together total 6.000 Amberium", both_amb == 6_000, str(both_amb))
    check("regular row has 60 PrimeMeat cells",
          sum(1 for c in reg if c["type"] == "coins") == 60)
    check("regular row has 9 Amberium cells",
          sum(1 for c in reg if c["type"] == "amber") == 9)
    check("premium row has 75 PrimeMeat cells",
          sum(1 for c in pre if c["type"] == "coins") == 75)
    check("premium row has 12 Amberium cells (every multiple of 8)",
          [c["level"] for c in pre if c["type"] == "amber"] == list(range(8, 97, 8)))


def case_no_halving_anywhere():
    """v1 listed one row at full price and paid a Regular buyer half. v2 gives
    each row its own literal numbers — nothing is halved, ever."""
    check("the halve helper is GONE", not hasattr(bp, "_halve"))
    for track in ("regular", "premium"):
        for c in bp.get_track(track):
            if c["type"] not in ("coins", "amber"):
                continue
            pub = bp._cell_public(c, track)
            rew = bp._reward_view(c, track)
            if pub["amount"] != c["amount"] or rew["amount"] != c["amount"]:
                check(f"{track} lv{c['level']} amount is literal", False, str(pub))
                return
            if "amount_granted" in pub:
                check("no amount_granted field survives", False, str(pub))
                return
    check("every cell's public amount is LITERAL on both rows", True)
    check("no cell carries amount_granted any more", True)


def case_regular_empty_cells():
    empties = [c["level"] for c in bp.get_track("regular") if c["type"] == "empty"]
    owner_empties = [lv for lv in empties if lv not in bp.REG_RETIRED_LEVELS]
    check("regular row has exactly 20 owner empty cells", len(owner_empties) == 20, str(len(owner_empties)))
    check("every owner empty level ends in 3 or 7", all(lv % 10 in (3, 7) for lv in owner_empties),
          str(owner_empties))
    # ★ owner order 2026-08-08: alba (35) + ambar (95) removed — their cells
    # are retired EMPTY exactly like the premium sol cell.
    check("regular retired cells are exactly 35, 65 and 95",
          sorted(lv for lv in empties if lv in bp.REG_RETIRED_LEVELS) == [35, 65, 95], str(empties))
    # ★ owner order 2026-08-13: the level-20 cell (retired empty with bp_s_sol
    # on 08-08) is re-opened for "supernova" — the premium row has NO empties.
    pre_empties = [c["level"] for c in bp.get_track("premium") if c["type"] == "empty"]
    check("premium row has no empty cells (level 20 re-opened for supernova 08-13)",
          pre_empties == [], str(pre_empties))


def case_row_layout_matches_the_brief():
    reg, pre = bp.get_track("regular"), bp.get_track("premium")
    rtok = {c["level"]: c["token"] for c in reg if c["type"] == "token"}
    check("regular diet tokens at 20/60",
          sorted(k for k, v in rtok.items() if v == "diet") == [20, 60], str(rtok))
    check("regular growth tokens at 40/80",
          sorted(k for k, v in rtok.items() if v == "growth") == [40, 80], str(rtok))
    check("regular row carries NO skin cells (35/65/95 all retired, owner order 08-08)",
          [c["level"] for c in reg if c["type"] == "skin"] == [])
    check("regular Amberium cells and amounts are the owner's hand-set list",
          {c["level"]: c["amount"] for c in reg if c["type"] == "amber"} == bp.REG_AMBER,
          str({c["level"]: c["amount"] for c in reg if c["type"] == "amber"}))

    ptok = {c["level"]: c["token"] for c in pre if c["type"] == "token"}
    check("premium diet tokens at 10/30/65",
          sorted(k for k, v in ptok.items() if v == "diet") == [10, 30, 65], str(ptok))
    check("premium growth tokens at 15/45/85",
          sorted(k for k, v in ptok.items() if v == "growth") == [15, 45, 85], str(ptok))
    check("premium legendary skins at 20/55/90 (20 = constelacion, owner order 08-16)",
          [c["level"] for c in pre if c["type"] == "skin"] == [20, 55, 90])
    # ★ owner order 2026-08-16 ("add the pink glitter in BP"): supernova left
    # this cell for the season leaderboard's 1º prize and the pink-glitter
    # design took it. The CELL SET is unchanged — that is the point of a swap:
    # the coin ramp only re-solves when a cell changes occupancy.
    check("the level-20 cell grants constelacion (the pink glitter)",
          next(c["skin"] for c in pre if c["level"] == 20) == "constelacion")
    for track in ("regular", "premium"):
        check(f"{track} dino cells at 25/50/75/100",
              [c["level"] for c in bp.get_track(track) if c["type"] == "dino"] == [25, 50, 75, 100])
    check("no cell carries premium_only any more (the ROW is the entitlement)",
          not any("premium_only" in bp._cell_public(c, "premium") for c in pre))


def case_mutations_per_row_and_buyer():
    # Owner order 2026-08-08: 3 random mutations if not prime, 4 if prime.
    want = {"regular": (3, 12), "premium": (4, 16)}
    for track, (per, row_total) in want.items():
        check(f"{track} row dinos carry {per} mutations each",
              bp.mutations_per_dino(track) == per, str(bp.mutations_per_dino(track)))
        n = sum(bp.mutations_per_dino(track)
                for c in bp.get_track(track) if c["type"] == "dino")
        check(f"{track} row carries {row_total} mutations", n == row_total, str(n))
    check("a Premium+ buyer nets 28 mutations across both rows",
          bp.mutations_per_dino("regular") * 4 + bp.mutations_per_dino("premium") * 4 == 28)
    check("non-prime count is 3 and prime count is 4",
          bp.MUTATIONS_NON_PRIME == 3 and bp.MUTATIONS_PRIME == 4)
    # Every species either row can grant must have a pool of at least 4
    # diet-legal pickable mutations, so 3 and 4 always deliver in full.
    for slug, cls in sorted(bp._CLASS_BY_SLUG.items()):
        pool = set(mutation_catalog.PICKABLE) & mutation_catalog.allowed_names_for_class(cls)
        check(f"{slug} has >= 4 pickable mutations", len(pool) >= 4, str(len(pool)))
    # The picks are distinct, diet-legal and deterministic (no reroll on retry).
    col_a = bp._pick_mutations("BP_Tyrannosaurus_C", 4, "u1", "s", "premium", 100, "x")
    col_b = bp._pick_mutations("BP_Tyrannosaurus_C", 4, "u1", "s", "premium", 100, "x")
    names = [m for m in col_a.split("|") if m != "None"]
    check("a prime pick yields 4 DISTINCT mutations",
          len(names) == 4 and len(set(names)) == 4, col_a)
    check("the same seed can never reroll", col_a == col_b)
    col3 = bp._pick_mutations("BP_Dryosaurus_C", 3, "u2", "s", "regular", 25, "y")
    n3 = [m for m in col3.split("|") if m != "None"]
    check("a non-prime pick yields exactly 3 mutations and slot 4 stays None",
          len(n3) == 3 and col3.split("|")[3] == "None", col3)


def case_row_flavors_and_prime():
    check("regular row grants BASIC tokens", bp._token_flavor("regular") == "basic")
    check("premium row grants PREMIUM tokens", bp._token_flavor("premium") == "premium")
    check("regular row dinos are NOT prime", bp.ROW_DINO_RULES["regular"]["prime"] is False)
    check("premium row dinos ARE prime", bp.ROW_DINO_RULES["premium"]["prime"] is True)
    check("regular row diet is 50% each (150%)", bp.ROW_DINO_RULES["regular"]["diet"] == 0.5)
    check("premium row diet is 100% each (300%)", bp.ROW_DINO_RULES["premium"]["diet"] == 1.0)
    check("regular row level 100 is the Triceratops", bp.fixed_dino("regular", 100) == "trike")
    check("premium row level 100 is the Tyrannosaurus", bp.fixed_dino("premium", 100) == "trex")


def case_no_invalid_species():
    slugs = {d["slug"] for d in seed_data.DINOSAURS}
    band_slugs = set(bp.BAND_LOW) | set(bp.BAND_MID) | set(bp.BAND_HIGH) | set(bp.APEX_SLUGS)
    check("every band species exists in seed_data", band_slugs <= slugs,
          str(sorted(band_slugs - slugs)))
    check("every band species has a game class",
          all(s in bp._CLASS_BY_SLUG for s in band_slugs))
    check("bands cover the whole 22-species roster", len(band_slugs) == 22, str(len(band_slugs)))
    check("bands do not overlap",
          len(bp.BAND_LOW) + len(bp.BAND_MID) + len(bp.BAND_HIGH) + len(bp.APEX_SLUGS) == 22)
    check("both level-100 species are real",
          set(bp.APEX_BY_TRACK.values()) <= slugs, str(bp.APEX_BY_TRACK))


def case_band_levels():
    """ONE band per dino cell — DinoPicker renders status.dino_bands[cell.band],
    a single key. v3 (owner order 2026-08-07 "for elder dino it should let me
    pick any specie"): the PREMIUM row's picks offer the WHOLE roster (band
    "all", apexes included); the regular row keeps low/mid/high."""
    check("regular lv25 picks from LOW",
          bp.pick_band("regular", 25) == "low"
          and set(bp.band_choices("regular", 25)) == set(bp.BAND_LOW))
    check("regular lv50 picks from MID", bp.pick_band("regular", 50) == "mid")
    check("regular lv75 picks from HIGH", bp.pick_band("regular", 75) == "high")
    for lv in (25, 50, 75):
        check(f"premium lv{lv} picks from the WHOLE roster",
              bp.pick_band("premium", lv) == "all"
              and set(bp.band_choices("premium", lv)) == set(bp.ALL_PICK_SLUGS)
              and len(bp.band_choices("premium", lv)) == 22, str(lv))
    check("premium picks INCLUDE the apexes (his 'any specie')",
          set(bp.APEX_SLUGS) <= set(bp.band_choices("premium", 25)))
    check("regular picks still EXCLUDE the apexes",
          not (set(bp.APEX_SLUGS) & set(bp.band_choices("regular", 25))))
    for track in ("regular", "premium"):
        check(f"{track} lv100 is FIXED (no pick band)", bp.pick_band(track, 100) is None)
    check("no apex species in a bracket band",
          not (set(bp.APEX_SLUGS) & (set(bp.BAND_LOW) | set(bp.BAND_MID) | set(bp.BAND_HIGH))))
    bands = bp.dino_bands_view()
    check("dino_bands carries the five keys the page renders",
          set(bands) == {"low", "mid", "high", "apex", "all"}, str(list(bands)))
    check("dino_bands entries carry slug + name + rarity (what the picker renders)",
          all(set(sp) >= {"slug", "name", "rarity"} for b in bands.values() for sp in b))
    check("the bracket bands + apex still cover all 22 species exactly once",
          sum(len(bands[b]) for b in ("low", "mid", "high", "apex")) == 22)
    check("the 'all' band lists the whole roster for the premium picker",
          len(bands["all"]) == 22
          and {sp["slug"] for sp in bands["all"]} == set(bp.ALL_PICK_SLUGS))
    check("dino_bands rarities are ones RarityBadge styles",
          {sp["rarity"] for b in bands.values() for sp in b}
          <= {"Apex", "Legendary", "Epic", "Rare", "Uncommon", "Common"})
    check("apex band names resolve (nameBySlug covers the level-100 cells)",
          {sp["slug"] for sp in bands["apex"]} == set(bp.APEX_SLUGS))


def case_skins_by_row():
    reg = [c["skin"] for c in bp.get_track("regular") if c["type"] == "skin"]
    pre = [c["skin"] for c in bp.get_track("premium") if c["type"] == "skin"]
    check("regular row skins (none since 08-08) are never Legendary",
          all(bp._bp_skin_rarity(g) != "Legendary" for g in reg), str(reg))
    check("premium row carries three LEGENDARY skins",
          len(pre) == 3 and all(bp._bp_skin_rarity(g) == "Legendary" for g in pre), str(pre))
    # ★ owner order 2026-08-13: the apex rider RETURNS carrying constelacion
    # (Corona del Rey itself stays removed — 08-08 order untouched).
    # ★ owner order 2026-08-16: swapped to supernova when constelacion moved
    # down to the level-20 cell, so no cell pays a duplicate (checked below).
    check("the apex skin rider carries supernova",
          getattr(bp, "APEX_BONUS_SKIN", None) == "supernova")
    all_granted = reg + pre + [bp.APEX_BONUS_SKIN]
    check("every skin cell grants a DISTINCT skin (no cell pays a duplicate)",
          len(set(all_granted)) == len(all_granted) == 4, str(all_granted))


def case_bp_skins_never_drop_from_crates():
    bp_ids = set(glitch_catalog.BP_SKIN_BY_ID)
    # 2 since 2026-08-08: sol, alba, ambar, corona and jungla removed by owner
    # order. 3 since 2026-08-18, when "constelacion for battlepass only" moved
    # the pink glitter design out of the crate list and into this one -- the
    # level-20 cell it already filled is now the ONLY way to win it.
    check("3 Battle Pass exclusive skins", len(bp_ids) == 3, str(sorted(bp_ids)))
    check("constelacion is one of them (2026-08-18 owner order)",
          "constelacion" in bp_ids)
    check("the level-20 cell grants a skin no crate can drop",
          not glitch_catalog.crate_eligible(bp.PRE_SKIN_BY_LEVEL[20]))
    check("every BP skin is flagged bp_exclusive",
          all(g.get("bp_exclusive") for g in glitch_catalog.BP_SKINS))
    check("BP skins are NOT in the crate glitch list",
          not (bp_ids & {g["id"] for g in glitch_catalog.GLITCH_SKINS}))
    leaked = []
    for case in seed_data.CASES:
        for entry in case.get("pool") or []:
            if entry.get("type") == "glitch" and entry.get("glitch") in bp_ids:
                leaked.append((case["id"], entry["glitch"]))
    check("no crate pool can drop a Battle Pass skin", not leaked, str(leaked))
    check("crate_eligible() refuses every BP id",
          not any(glitch_catalog.crate_eligible(g) for g in bp_ids))
    check("crate_eligible() accepts the 9 canonical glitches",
          all(glitch_catalog.crate_eligible(g["id"]) for g in glitch_catalog.GLITCH_SKINS))
    # 2026-08-13 contract: emission is VERBATIM — the authored variation and
    # pattern ride through (the 08-05 var-0.0/pat-0..2 folds are retired).
    for gid in bp_ids:
        g = glitch_catalog.GLITCH_BY_ID[gid]
        cmd = glitch_catalog.build_glitch_command(gid, "Actor_1", "BP_Carnotaurus_C", SID, False)
        if (cmd is None or cmd["variation"] != g["payload"]["variation"]
                or cmd["pattern"] != g["payload"]["pattern"]):
            check(f"BP skin {gid} emits its authored variation+pattern verbatim", False, str(cmd))
            break
    else:
        check("every BP skin emits its authored variation+pattern verbatim", True)
    # A glitch card is a NAME + COLOUR PROXIMITY, never a picture (fleet order
    # 2026-08-11): preview is retired to "" on every BP skin.
    check("no BP skin carries a preview image",
          all(g["preview"] == "" for g in glitch_catalog.BP_SKINS),
          str([g["preview"] for g in glitch_catalog.BP_SKINS]))


# =============================================================================
# 2. XP curve
# =============================================================================
def case_xp_curve():
    check("xp_for_level(1) == 0", bp.xp_for_level(1) == 0)
    check("xp curve is strictly monotonic 1..100",
          all(bp.xp_for_level(n) < bp.xp_for_level(n + 1) for n in range(1, 100)))
    check("level 100 needs 59.251 xp", bp.xp_for_level(100) == 59251, str(bp.xp_for_level(100)))
    check("level caps at 100 (no 101)", bp.level_from_xp(10 ** 9) == 100)
    check("negative / zero xp -> level 1",
          bp.level_from_xp(0) == 1 and bp.level_from_xp(-500) == 1)


def case_level_from_xp_boundaries():
    bad = []
    for n in range(2, 101):
        t = bp.xp_for_level(n)
        if bp.level_from_xp(t) != n or bp.level_from_xp(t - 1) != n - 1:
            bad.append(n)
    check("level_from_xp is exact at EVERY threshold (t -> n, t-1 -> n-1)", not bad, str(bad))
    check("progress at the cap reads 100%",
          bp.level_progress(bp.xp_for_level(100))["percent"] == 100.0)
    check("progress at the cap is flagged capped", bp.level_progress(10 ** 9)["capped"] is True)
    check("progress at 0 xp is level 1", bp.level_progress(0)["level"] == 1)


# =============================================================================
# 3. XP hooks  (XP accrues for everyone, pass or no pass)
# =============================================================================
async def case_passive_xp():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d)
    await bp.hook_passive_xp(u["id"], 3)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("passive pays 60 BP XP per cycle", int(p["xp"]) == 180, str(p))
    await bp.hook_passive_xp(u["id"], 0)
    await bp.hook_passive_xp(u["id"], -5)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("passive with 0 / negative cycles pays nothing", int(p["xp"]) == 180)
    before = dict(await d.users.find_one({"id": u["id"]}, {"_id": 0}))
    check("BP XP never touches the chat-level users.xp", int(before.get("xp") or 0) == 0)
    check("XP accrues for a player with NO pass", p.get("tier") in (None, "free"), str(p))


async def case_quest_xp_by_rarity():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d)
    expect = {"Common": 120, "Uncommon": 250, "Rare": 500, "Epic": 1000, "Legendary": 2000}
    check("quest XP map is exactly LIN's five rarities",
          set(bp.BP_XP_QUEST_BY_RARITY) == set(expect) == set(
              __import__("quest_data").QUEST_RARITIES),
          str(sorted(bp.BP_XP_QUEST_BY_RARITY)))
    total = 0
    for rarity, amt in expect.items():
        await bp.hook_quest_xp(u["id"], rarity)
        total += amt
    await bp.hook_quest_xp(u["id"], "Apex")      # not a LIN rarity
    await bp.hook_quest_xp(u["id"], None)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("quest XP pays the exact per-rarity amount and ignores unknown rarities",
          int(p["xp"]) == total, f"{p['xp']} != {total}")


async def case_kill_xp_fail_closed_and_cooldown():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d)
    bp._kill_pair_seen.clear()
    check("unknown victim species pays nothing", bp.kill_xp_for(None, 0.9) == 0)
    check("unknown victim growth pays nothing", bp.kill_xp_for("Tyrannosaurus", None) == 0)
    check("unrecognised species name pays nothing", bp.kill_xp_for("Godzilla", 0.9) == 0)
    check("growth below the 0.25 floor pays nothing", bp.kill_xp_for("Tyrannosaurus", 0.24) == 0)
    check("growth exactly at the floor pays", bp.kill_xp_for("Tyrannosaurus", 0.25) == 500)
    check("LOW band victim pays 80", bp.kill_xp_for("Dryosaurus", 1.0) == 80)
    check("MID band victim pays 150", bp.kill_xp_for("Carnotaurus", 1.0) == 150)
    check("HIGH band victim pays 250", bp.kill_xp_for("Stegosaurus", 1.0) == 250)
    check("APEX band victim pays 500", bp.kill_xp_for("Triceratops", 1.0) == 500)

    await bp.hook_kill_xp(u["id"], "Tyrannosaurus", 0.9, SID, SID2)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("first kill on a pair pays", int(p["xp"]) == 500, str(p))
    await bp.hook_kill_xp(u["id"], "Tyrannosaurus", 0.9, SID, SID2)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("same pair inside 30 min pays NOTHING (anti-farm)", int(p["xp"]) == 500, str(p))
    await bp.hook_kill_xp(u["id"], "Tyrannosaurus", 0.9, SID, "76561199000000099")
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("a DIFFERENT victim still pays", int(p["xp"]) == 1000, str(p))
    await bp.hook_kill_xp(u["id"], "Tyrannosaurus", 0.9, SID, SID)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("self-kill pays nothing", int(p["xp"]) == 1000, str(p))
    bp._kill_pair_seen[(SID, SID2)] = time.time() - (bp.KILL_PAIR_COOLDOWN_S + 1)
    await bp.hook_kill_xp(u["id"], "Tyrannosaurus", 0.9, SID, SID2)
    p = await d.bp_passes.find_one({"user_id": u["id"]}, {"_id": 0})
    check("the pair pays again once the 30 min elapse", int(p["xp"]) == 1500, str(p))
    await bp.hook_kill_xp(None, "Tyrannosaurus", 0.9, SID, SID2)
    check("a kill with no resolved killer never crashes", True)


# =============================================================================
# 4. ★ ACCESS — the owner's live complaint, pinned
# =============================================================================
async def case_no_purchase_claims_nothing():
    """"im able to use regular without even buying" — a player who has bought
    nothing must be refused on EVERY cell of BOTH rows."""
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="np1")
    await set_xp(d, "np1", bp.xp_for_level(100))          # max level, still no pass
    s = await bp.bp_status(user=u)
    check("a player who bought nothing resolves to tier free", s["tier"] == "free", str(s["tier"]))
    check("a free tier can claim NO row", s["claimable_tracks"] == [], str(s["claimable_tracks"]))
    check("claimable_count is 0 with no pass", s["claimable_count"] == 0, str(s["claimable_count"]))

    refused = []
    for track in ("regular", "premium"):
        for lv in (1, 2, 4, 5, 20, 25, 35, 50, 100):
            try:
                await bp.bp_claim(bp.ClaimIn(track=track, level=lv, choice="dryo"), user=u)
                refused.append(f"{track}:{lv} SUCCEEDED")
            except HTTPException as e:
                if e.status_code != 403:
                    refused.append(f"{track}:{lv} -> {e.status_code} {e.detail}")
    check("EVERY claim on BOTH rows is refused 403 without a purchase", not refused, str(refused))
    check("the refusal names the real reason", True)
    try:
        await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
    except HTTPException as e:
        check("the refusal copy tells them to buy a pass",
              "comprar un Pase" in str(e.detail), str(e.detail))

    r = await bp.bp_claim_all(user=u)
    check("claim-all grants NOTHING without a purchase", r["claimed_count"] == 0, str(r))
    check("no claim row was written", (await d.bp_claims.count_documents({})) == 0)
    check("no currency was paid",
          (await d.users.find_one({"id": "np1"}, {"_id": 0}))["coins"] == 0)
    check("no token was granted", (await d.inventory.count_documents({})) == 0)
    check("no skin was granted", (await d.reward_skins.count_documents({})) == 0)
    check("no dino reached the vault", len(vault.get_parked(SID)) == 0)
    check("both rows are still SERVED for display",
          len(s["regular_track"]) == 100 and len(s["premium_track"]) == 100)


async def case_active_patreon_grants_nothing():
    """Regression pin for the exact account the owner hit: an ACTIVE Patreon
    member with no purchase resolves to free and can claim nothing."""
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="pat1", patreon_patron_status="active_patron",
                      patreon_tier_name="Adult")
    await set_xp(d, "pat1", bp.xp_for_level(50))
    check("the Patreon mapping helpers are GONE",
          not hasattr(bp, "patreon_bp_tier") and not hasattr(bp, "PATREON_TIER_TO_BP")
          and not hasattr(bp, "patreon_tier_key"))
    check("an ACTIVE adult patron resolves to tier free",
          bp.resolve_tier(u, {}) == ("free", "free"), str(bp.resolve_tier(u, {})))
    s = await bp.bp_status(user=u)
    check("an active patron sees tier free on the page", s["tier"] == "free", str(s["tier"]))
    for track in ("regular", "premium"):
        try:
            await bp.bp_claim(bp.ClaimIn(track=track, level=1), user=u)
            check(f"an active patron cannot claim the {track} row", False, "claim succeeded")
        except HTTPException as e:
            check(f"an active patron cannot claim the {track} row", e.status_code == 403,
                  str(e.detail))
    check("even an apex patron resolves free",
          bp.resolve_tier({"patreon_patron_status": "active_patron",
                           "patreon_tier_name": "Apex"}, {}) == ("free", "free"))


async def case_regular_buyer_access():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="rb1")
    await set_xp(d, "rb1", bp.xp_for_level(100), tier=bp.TIER_REGULAR, source="stripe")
    s = await bp.bp_status(user=u)
    check("a $5 buyer may claim the regular row only",
          s["claimable_tracks"] == ["regular"], str(s["claimable_tracks"]))
    r = await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
    check("a $5 buyer claims the regular row", r["ok"] is True, str(r))
    lit = bp.cell_at("regular", 1)["amount"]
    check("the payout is the LITERAL cell amount (nothing halved)",
          r["reward"]["amount"] == lit
          and (await d.users.find_one({"id": "rb1"}, {"_id": 0}))["coins"] == lit, str(r))
    try:
        await bp.bp_claim(bp.ClaimIn(track="premium", level=1), user=u)
        check("a $5 buyer is refused on the premium row", False, "claim succeeded")
    except HTTPException as e:
        check("a $5 buyer is refused on the premium row",
              e.status_code == 403 and "Premium+" in str(e.detail), str(e.detail))
    ra = await bp.bp_claim_all(user=u)
    check("claim-all touches the regular row only",
          {row["track"] for row in ra["claimed"]} == {"regular"},
          str({row["track"] for row in ra["claimed"]}))
    reg_total = sum(c["amount"] for c in bp.get_track("regular") if c["type"] == "coins")
    fresh = await d.users.find_one({"id": "rb1"}, {"_id": 0})
    check("a $5 buyer who claims the whole regular row banks EXACTLY 1.000.000 PrimeMeat",
          int(fresh["coins"]) == reg_total == 1_000_000, str(fresh["coins"]))
    check("...and EXACTLY 3.000 Amberium", int(fresh["vip_coins"]) == 3_000, str(fresh["vip_coins"]))
    toks = await d.inventory.find({"user_id": "rb1"}, {"_id": 0}).to_list(50)
    check("every token the regular row grants is BASIC",
          toks and all(t["token_tier"] == "basic" for t in toks),
          str([t["token_tier"] for t in toks]))


async def case_premium_buyer_access_and_stacking():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="pb1")
    await set_xp(d, "pb1", bp.xp_for_level(100), tier=bp.TIER_PREMIUM, source="stripe")
    s = await bp.bp_status(user=u)
    check("a $10 buyer may claim BOTH rows",
          s["claimable_tracks"] == ["regular", "premium"], str(s["claimable_tracks"]))
    ra = await bp.bp_claim_all(user=u)
    check("claim-all spans both rows",
          {row["track"] for row in ra["claimed"]} == {"regular", "premium"},
          str({row["track"] for row in ra["claimed"]}))
    fresh = await d.users.find_one({"id": "pb1"}, {"_id": 0})
    check("a $10 buyer who claims everything banks EXACTLY 2.000.000 PrimeMeat",
          int(fresh["coins"]) == 2_000_000, str(fresh["coins"]))
    check("...and EXACTLY 6.000 Amberium", int(fresh["vip_coins"]) == 6_000, str(fresh["vip_coins"]))
    toks = await d.inventory.find({"user_id": "pb1"}, {"_id": 0}).to_list(50)
    flavors = sorted(t["token_tier"] for t in toks)
    check("token flavour follows the ROW: 4 basic + 6 premium",
          flavors == ["basic"] * 4 + ["premium"] * 6, str(flavors))

    # claim-all already banked both FIXED level-100 dinos (a fixed cell is not a
    # choice). Only the three picks per row are left.
    for track, first in (("regular", "dryo"), ("premium", "hypsi")):
        for lv, pick in ((25, first), (50, "carno"), (75, "allo")):
            await bp.bp_claim(bp.ClaimIn(track=track, level=lv, choice=pick), user=u)
    rows = vault.get_parked(SID)
    classes = sorted(r["dino_class"] for r in rows)
    check("a $10 buyer gets BOTH the Triceratops and the Tyrannosaurus",
          "BP_Triceratops_C" in classes and "BP_Tyrannosaurus_C" in classes, str(classes))
    check("8 dinos land in total (4 per row)", len(rows) == 8, str(len(rows)))
    muts = sum(len([m for m in str(r["mutations"]).split("|") if m != "None"]) for r in rows)
    check("28 mutations across both rows — 4x3 non-prime + 4x4 prime", muts == 28, str(muts))
    prime = sorted(int(r["is_prime"]) for r in rows)
    check("exactly the 4 premium-row dinos are PRIME", prime == [0, 0, 0, 0, 1, 1, 1, 1], str(prime))
    diets = sorted(float(r["diet_a"]) for r in rows)
    check("diet follows the ROW: four at 50%, four at 100%",
          diets == [0.5] * 4 + [1.0] * 4, str(diets))
    n_skins = await d.reward_skins.count_documents({"user_id": "pb1"})
    # 2026-08-13: cells grant supernova/vacio/eclipse and the premium level-100
    # claim rides the constelacion rider — 4 distinct reward docs.
    check("the premium level-100 claim grants the constelacion rider (4 skin docs)",
          n_skins == len(bp.REG_SKIN_BY_LEVEL) + len(bp.PRE_SKIN_BY_LEVEL) + 1, str(n_skins))
    rider = await d.reward_skins.find_one({"user_id": "pb1", "glitch_id": bp.APEX_BONUS_SKIN})
    check("the rider doc exists with the pass source",
          bool(rider) and str(rider.get("source", "")).startswith("Pase de Batalla"), str(rider)[:120])


# =============================================================================
# 5. Claims
# =============================================================================
async def case_claim_basics_and_double_claim():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d)
    await set_xp(d, u["id"], bp.xp_for_level(30), tier=bp.TIER_REGULAR, source="gift")
    r = await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
    check("a regular-row cell claims", r["success"] is True and r["effects"], str(r))
    lit = bp.cell_at("regular", 1)["amount"]
    fresh = await d.users.find_one({"id": u["id"]}, {"_id": 0})
    check("regular level 1 pays its literal amount", int(fresh["coins"]) == lit, str(fresh))
    try:
        await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
        check("double-claim of the same cell is REFUSED", False, "second claim succeeded")
    except HTTPException as e:
        check("double-claim of the same cell is REFUSED",
              e.status_code == 400 and "Ya reclamaste" in str(e.detail), str(e.detail))
    n = await d.bp_claims.count_documents({"user_id": u["id"]})
    check("exactly one claim row survives the double press", n == 1, str(n))
    fresh = await d.users.find_one({"id": u["id"]}, {"_id": 0})
    check("the refused second claim paid NOTHING", int(fresh["coins"]) == lit, str(fresh))


async def case_legacy_track_names_still_claim():
    """A browser holding the v1 bundle posts track "free"/"pass"."""
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="lg1")
    await set_xp(d, "lg1", bp.xp_for_level(30), tier=bp.TIER_PREMIUM, source="gift")
    r = await bp.bp_claim(bp.ClaimIn(track="free", level=1), user=u)
    check('legacy track "free" maps to the regular row', r["track"] == "regular", str(r))
    r = await bp.bp_claim(bp.ClaimIn(track="pass", level=1), user=u)
    check('legacy track "pass" maps to the premium row', r["track"] == "premium", str(r))
    try:
        await bp.bp_claim(bp.ClaimIn(track="free", level=1), user=u)
        check("a legacy name cannot re-claim a level already taken", False)
    except HTTPException as e:
        check("a legacy name cannot re-claim a level already taken",
              "Ya reclamaste" in str(e.detail), str(e.detail))


async def case_claim_level_and_empty_and_track_gates():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d)
    await set_xp(d, u["id"], bp.xp_for_level(10), tier=bp.TIER_REGULAR, source="gift")
    for name, track, level, frag in (
            ("a level above the player's is refused", "regular", 11, "Todavía no llegas"),
            ("an EMPTY regular cell is refused", "regular", 3, "no tiene recompensa"),
            ("the premium row is refused for a $5 buyer", "premium", 4, "Premium+")):
        try:
            await bp.bp_claim(bp.ClaimIn(track=track, level=level), user=u)
            check(name, False, "claim succeeded")
        except HTTPException as e:
            check(name, frag in str(e.detail), str(e.detail))
    try:
        await bp.bp_claim(bp.ClaimIn(track="nope", level=1), user=u)
        check("an unknown track is refused", False)
    except HTTPException as e:
        check("an unknown track is refused", e.status_code == 400)
    try:
        await bp.bp_claim(bp.ClaimIn(track="regular", level=101), user=u)
        check("level 101 does not exist", False)
    except HTTPException as e:
        check("level 101 does not exist", e.status_code == 400)
    check("claim at the exact level boundary is allowed",
          (await bp.bp_claim(bp.ClaimIn(track="regular", level=10), user=u))["success"])


async def case_dino_claim_choice_validation():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="dino1")
    # level 80: the case claims picks at 25/50 AND the new-apex pin at 75.
    await set_xp(d, "dino1", bp.xp_for_level(80), tier=bp.TIER_PREMIUM, source="gift")
    for name, track, choice, frag in (
            ("a species outside the REGULAR band is refused", "regular", "trex", "especie disponible"),
            # ★ owner order 2026-08-07: deino/stego/trike are APEXES now -- a
            # regular-row pick must refuse every one of them at every pick level.
            ("the apex Deino is refused on a REGULAR pick", "regular", "deino", "especie disponible"),
            ("the apex Stego is refused on a REGULAR pick", "regular", "stego", "especie disponible"),
            ("the apex Trike is refused on a REGULAR pick", "regular", "trike", "especie disponible"),
            ("an unknown slug is refused", "premium", "godzilla", "especie disponible"),
            ("an empty choice is refused", "premium", "", "especie disponible")):
        try:
            await bp.bp_claim(bp.ClaimIn(track=track, level=25, choice=choice), user=u)
            check(name, False, "claim succeeded")
        except HTTPException as e:
            check(name, frag in str(e.detail), str(e.detail))
    check("no claim row was consumed by the refusals",
          (await d.bp_claims.count_documents({"user_id": "dino1"})) == 0)
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=25, choice="dryo"), user=u)
    check("a valid band pick is granted", r["effects"][0]["kind"] == "dino", str(r))
    rows = vault.get_parked(SID)
    check("exactly one dino landed in the vault", len(rows) == 1, str(len(rows)))
    row = rows[0]
    check("the granted dino is 75% grown", abs(float(row["growth"]) - 0.75) < 1e-9,
          str(row["growth"]))
    check("premium row grants PRIME", int(row["is_prime"]) == 1 and int(row["is_elder"]) == 1)
    check("premium row diet is 100% on all three nutrients",
          (float(row["diet_a"]), float(row["diet_b"]), float(row["diet_c"])) == (1.0, 1.0, 1.0),
          str(row))
    muts = [m for m in str(row["mutations"]).split("|") if m != "None"]
    check("a PRIME dino cell carries 4 distinct mutations",
          len(muts) == 4 and len(set(muts)) == 4, str(row["mutations"]))
    allowed = mutation_catalog.allowed_names_for_class("BP_Dryosaurus_C")
    check("the mutation is diet-legal for the species", set(muts) <= allowed, str(muts))
    check("no elder_stacks were minted", int(row["elder_stacks"] or 0) == 0)
    # ★ v3 (owner order 2026-08-07 "for elder dino it should let me pick any
    # specie"): an APEX on a premium pick is a VALID choice and lands prime.
    r2 = await bp.bp_claim(bp.ClaimIn(track="premium", level=50, choice="trex"), user=u)
    check("a premium pick may choose an APEX now", r2["effects"][0]["kind"] == "dino", str(r2))
    rex = [x for x in vault.get_parked(SID) if x["dino_class"] == "BP_Tyrannosaurus_C"]
    check("the picked apex landed in the vault PRIME at 75%",
          len(rex) == 1 and int(rex[0]["is_prime"]) == 1
          and abs(float(rex[0]["growth"]) - 0.75) < 1e-9, str(len(rex)))
    # ★ owner order 2026-08-07: the NEW apexes (deino/stego) are premium-pickable.
    r3 = await bp.bp_claim(bp.ClaimIn(track="premium", level=75, choice="stego"), user=u)
    check("a premium pick may choose the new apex Stego", r3["effects"][0]["kind"] == "dino", str(r3))
    stego = [x for x in vault.get_parked(SID) if x["dino_class"] == "BP_Stegosaurus_C"]
    check("the picked Stego landed in the vault PRIME",
          len(stego) == 1 and int(stego[0]["is_prime"]) == 1, str(len(stego)))


async def case_dino_grant_follows_the_row_not_the_tier():
    """A $10 buyer claiming the REGULAR row's pick gets that row's non-prime
    version — the row decides, never the wallet."""
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="rw1", sid=SID2)
    await set_xp(d, "rw1", bp.xp_for_level(60), tier=bp.TIER_PREMIUM, source="gift")
    await bp.bp_claim(bp.ClaimIn(track="regular", level=25, choice="hypsi"), user=u)
    row = vault.get_parked(SID2)[0]
    check("a Premium+ buyer's REGULAR-row pick is NOT prime", int(row["is_prime"]) == 0)
    check("...and carries the regular row's 150% diet",
          (float(row["diet_a"]), float(row["diet_b"]), float(row["diet_c"])) == (0.5, 0.5, 0.5))
    check("...and 3 mutations (non-prime count)",
          len([m for m in str(row["mutations"]).split("|") if m != "None"]) == 3)
    await bp.bp_claim(bp.ClaimIn(track="premium", level=25, choice="hypsi"), user=u)
    rows = sorted(vault.get_parked(SID2), key=lambda r: int(r["is_prime"]))
    check("the same species on the PREMIUM row IS prime", int(rows[1]["is_prime"]) == 1)
    check("...and carries 300% diet", float(rows[1]["diet_a"]) == 1.0)


async def case_apex_cells():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="apex1")
    await set_xp(d, "apex1", bp.xp_for_level(100), tier=bp.TIER_PREMIUM, source="stripe")
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=100), user=u)
    kinds = [e["kind"] for e in r["effects"]]
    # 2026-08-13 owner order: the apex rider returns carrying constelacion.
    check("premium level 100 grants the dino + the constelacion rider",
          kinds == ["dino", "skin"]
          and r["effects"][1].get("skin") == bp.APEX_BONUS_SKIN, str(r))
    check("premium level 100 is a PRIME Tyrannosaurus",
          vault.get_parked(SID)[0]["dino_class"] == "BP_Tyrannosaurus_C"
          and int(vault.get_parked(SID)[0]["is_prime"]) == 1)
    r = await bp.bp_claim(bp.ClaimIn(track="regular", level=100), user=u)
    check("regular level 100 grants ONLY the dino (no bonus skin)",
          [e["kind"] for e in r["effects"]] == ["dino"], str(r))
    trike = [x for x in vault.get_parked(SID) if x["dino_class"] == "BP_Triceratops_C"]
    check("regular level 100 is a NON-prime Triceratops",
          trike and int(trike[0]["is_prime"]) == 0, str(trike))


async def case_vault_full_refusal_does_not_consume():
    _wipe_vault()
    PARK_CAP[0] = 1
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="full1")
    _park(SID)                       # the single allowed slot is already taken
    await set_xp(d, "full1", bp.xp_for_level(30), tier=bp.TIER_PREMIUM, source="gift")
    try:
        await bp.bp_claim(bp.ClaimIn(track="premium", level=25, choice="dryo"), user=u)
        check("a full vault REFUSES the dino claim", False, "claim succeeded")
    except HTTPException as e:
        check("a full vault REFUSES the dino claim",
              e.status_code == 400 and "Bóveda está llena" in str(e.detail), str(e.detail))
    check("the refused claim was NOT consumed (cell still claimable)",
          (await d.bp_claims.count_documents({"user_id": "full1"})) == 0)
    check("no second dino was written to the vault", len(vault.get_parked(SID)) == 1)
    PARK_CAP[0] = 0
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=25, choice="dryo"), user=u)
    check("once there is room the same cell claims normally", r["effects"][0]["kind"] == "dino")
    PARK_CAP[0] = 0


async def case_claim_all():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="ca1")
    await set_xp(d, "ca1", bp.xp_for_level(30), tier=bp.TIER_PREMIUM, source="gift")
    r = await bp.bp_claim_all(user=u)
    claims = await d.bp_claims.find({"user_id": "ca1"}, {"_id": 0}).to_list(500)
    levels = {(c["track"], c["level"]) for c in claims}
    check("claim-all leaves the level-25 dino CHOICE unclaimed on both rows",
          ("regular", 25) not in levels and ("premium", 25) not in levels, str(sorted(levels)))
    check("claim-all skips every empty regular cell",
          not any(t == "regular" and lv % 10 in (3, 7) for t, lv in levels))
    expected = sum(1 for track in ("regular", "premium")
                   for c in bp.get_track(track)
                   if c["level"] <= 30 and c["type"] not in ("empty", "dino"))
    check("claim-all claimed every other unlocked cell on both rows",
          r["claimed_count"] == expected, f"{r['claimed_count']} != {expected}")
    r2 = await bp.bp_claim_all(user=u)
    check("a second claim-all is a no-op (nothing double-paid)", r2["claimed_count"] == 0, str(r2))


async def case_status_payload():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="st1")
    s = await bp.bp_status(user=u)
    check("a never-visited player gets a pass row lazily at 0 XP",
          s["xp"]["xp"] == 0 and s["level"] == 1, str(s["xp"]))
    check("a player with no purchase sees tier free", s["tier"] == "free")
    check("status carries both rows FLAT, 100 cells each",
          len(s["regular_track"]) == 100 and len(s["premium_track"]) == 100)
    check("status season name is the owner's format",
          s["season"]["name"] == bp.season_display_name(bp.current_season_id()))
    check("status advertises the 70% growth rule", s["rules"]["growth_token_pct"] == 70)
    check("rules report 28 mutations for a Premium+ buyer, 12 regular, 3/4 per dino",
          s["rules"]["mutations_premium"] == 28 and s["rules"]["mutations_regular"] == 12
          and s["rules"]["mutations_per_dino"] == {"regular": 3, "premium": 4},
          str(s["rules"]))
    check("the regular row's level-100 cell previews the Triceratops",
          s["regular_track"][99]["slug"] == "trike", str(s["regular_track"][99]))
    check("the premium row's level-100 cell previews the Tyrannosaurus",
          s["premium_track"][99]["slug"] == "trex", str(s["premium_track"][99]))
    cell25 = s["premium_track"][24]
    check("a premium pick cell carries NO slug and offers the whole roster",
          "slug" not in cell25 and cell25["band"] == "all", str(cell25))
    reg25 = s["regular_track"][24]
    check("a regular pick cell still names its bracket band",
          "slug" not in reg25 and reg25["band"] == "low", str(reg25))
    check("status reports payments disabled with no Stripe key", s["payments_enabled"] is False)
    check("status reports the live token lane off with no capability",
          s["live_tokens_enabled"] is False)


async def case_legacy_track_aliases_still_served():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="al1")
    await set_xp(d, "al1", bp.xp_for_level(20), tier=bp.TIER_PREMIUM, source="gift")
    await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
    s = await bp.bp_status(user=u)
    check("free_track is still served and IS the regular row",
          s["free_track"] == s["regular_track"], "arrays differ")
    check("pass_track is still served and IS the premium row",
          s["pass_track"] == s["premium_track"], "arrays differ")
    check("claimed carries the new key", s["claimed"].get("regular:1") is True)
    check("claimed ALSO carries the deprecated v1 key so an old bundle keeps its ticks",
          s["claimed"].get("free:1") is True, str(list(s["claimed"])))


# =============================================================================
# 6. Tokens
# =============================================================================
async def _give_token(d, uid, token, flavor):
    u = await d.users.find_one({"id": uid}, {"_id": 0})
    return await bp._grant_token(u, token, flavor, bp.current_season_id())


async def case_tokens_are_live_only():
    """v5 (owner orders 2026-08-07: diet first, then "same with this" for
    growth): EVERY pass token refuses the vault target BEFORE anything is
    consumed — both kinds, both flavors — and the stored row is untouched.
    The in-game effects live in the lua lane (bpdiet2 kit's own gates)."""
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="lo1")
    rid = _park(SID, growth=0.30, diet=(0.1, 0.9, 0.0))
    for kind, flavor in (("diet", "basic"), ("diet", "premium"),
                         ("growth", "basic"), ("growth", "premium")):
        t = await _give_token(d, "lo1", kind, flavor)
        try:
            await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t["inv_id"], target="parked",
                                                      vault_id=rid), user=u)
            check(f"a parked {flavor} {kind} redeem is refused", False, "succeeded")
        except HTTPException as e:
            check(f"a parked {flavor} {kind} redeem is refused",
                  e.status_code == 400 and "EN VIVO" in str(e.detail), str(e.detail))
        check(f"the refused {flavor} {kind} token is NOT consumed",
              (await d.inventory.count_documents({"id": t["inv_id"]})) == 1)
    row = _row(rid)
    check("the vault row is untouched by every refusal",
          abs(float(row["growth"]) - 0.30) < 1e-9 and int(row["is_prime"]) == 0
          and (float(row["diet_a"]), float(row["diet_b"]), float(row["diet_c"])) == (0.1, 0.9, 0.0),
          str(dict(row)))
    # The inner lane is belted too: a direct call refuses any token kind.
    for kind in ("diet", "growth"):
        try:
            await bp._redeem_parked(u, {"token": kind, "token_tier": "basic"}, rid)
            check(f"the inner parked lane also refuses {kind} (belt)", False, "succeeded")
        except HTTPException as e:
            check(f"the inner parked lane also refuses {kind} (belt)",
                  e.status_code == 400, str(e.detail))


async def case_token_consume_atomicity():
    """Two tabs redeeming the SAME token copy on the LIVE lane: exactly one may
    win. Self-contained game mocks (instant ok acks)."""
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="at1")
    t = await _give_token(d, "at1", "growth", "premium")
    caps = os.path.join(_SAVED, "laislanublar_restore_caps.json")
    with open(caps, "w", encoding="utf-8") as f:
        f.write('{"restore_contract":"laislanublar_restore_v4","bp_tokens":true}')
    real = (game_ipc.mod_alive, game_ipc.write_game_command, game_ipc.read_restore_status)
    game_ipc.mod_alive = lambda: True
    game_ipc.write_game_command = lambda cmd: True
    game_ipc.read_restore_status = (
        lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
        {"event": event, "cmd_id": cmd_id} if event in ("bp_grow_ok", "bp_diet_ok") else None)
    try:
        results = await asyncio.gather(
            bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t["inv_id"], target="live"), user=u),
            bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t["inv_id"], target="live"), user=u),
            return_exceptions=True)
    finally:
        game_ipc.mod_alive, game_ipc.write_game_command, game_ipc.read_restore_status = real
        try:
            os.remove(caps)
        except OSError:
            pass
    ok = [r for r in results if not isinstance(r, Exception)]
    bad = [r for r in results if isinstance(r, Exception)]
    check("exactly ONE of two concurrent redeems of the same token wins",
          len(ok) == 1 and len(bad) == 1, str(results))
    check("the loser gets an honest HTTP refusal", isinstance(bad[0], HTTPException), str(bad))
    check("the token is gone exactly once",
          (await d.inventory.count_documents({"id": t["inv_id"]})) == 0)


async def case_live_token_lane():
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="lv1")
    t = await _give_token(d, "lv1", "diet", "premium")
    check("the live lane is OFF until the mod advertises bp_tokens",
          bp.live_tokens_enabled() is False)
    try:
        await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t["inv_id"], target="live"), user=u)
        check("target=live is refused without the capability", False)
    except HTTPException as e:
        # v4 copy is NEUTRAL on purpose: diet may not fall back to the vault,
        # so the unavailable message recommends retrying, never the Bóveda.
        check("target=live is refused without the capability",
              e.status_code == 503 and "no se gastó" in str(e.detail)
              and "Bóveda" not in str(e.detail), str(e.detail))
    check("the refused live redeem did not consume the token",
          (await d.inventory.count_documents({"id": t["inv_id"]})) == 1)

    caps = os.path.join(_SAVED, "laislanublar_restore_caps.json")
    with open(caps, "w", encoding="utf-8") as f:
        f.write('{"restore_contract":"laislanublar_restore_v4","bp_tokens":true}')
    real_alive, real_write, real_read = (game_ipc.mod_alive, game_ipc.write_game_command,
                                         game_ipc.read_restore_status)
    sent = []
    game_ipc.mod_alive = lambda: True
    game_ipc.write_game_command = lambda cmd: (sent.append(dict(cmd)) or True)
    try:
        check("the capability probe sees bp_tokens once advertised",
              bp.live_tokens_enabled() is True)
        game_ipc.read_restore_status = (
            lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
            {"event": event, "cmd_id": cmd_id} if event == "bp_diet_ok" else None)
        r = await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t["inv_id"], target="live"), user=u)
        check("a live redeem with an ok ack succeeds", r["target"] == "live", str(r))
        check("the token is consumed only after the ack",
              (await d.inventory.count_documents({"id": t["inv_id"]})) == 0)
        cmd = sent[-1]
        check("the IPC command carries the agreed contract",
              cmd["type"] == "bp_diet" and cmd["steamid"] == SID and cmd["tier"] == "premium"
              and len(cmd["cmd_id"]) == 32 and isinstance(cmd["issued_at_ms"], int), str(cmd))
        t2 = await _give_token(d, "lv1", "growth", "basic")
        game_ipc.read_restore_status = lambda *a, **k: None
        old_to = bp.LIVE_ACK_TIMEOUT_S
        bp.LIVE_ACK_TIMEOUT_S = 0.4
        try:
            await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t2["inv_id"], target="live"), user=u)
            check("a live redeem that never acks is refused", False)
        except HTTPException as e:
            check("a live redeem that never acks is refused",
                  e.status_code == 409 and "devolvimos" in str(e.detail), str(e.detail))
        finally:
            bp.LIVE_ACK_TIMEOUT_S = old_to
        check("the un-acked token is given back",
              (await d.inventory.count_documents({"id": t2["inv_id"]})) == 1)
        t3 = await _give_token(d, "lv1", "growth", "basic")
        game_ipc.read_restore_status = (
            lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
            {"event": event, "reason": "no_pawn"} if event == "bp_grow_failed" else None)
        try:
            await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t3["inv_id"], target="live"), user=u)
            check("an explicit failure ack is refused", False)
        except HTTPException as e:
            check("an explicit failure ack is refused", e.status_code == 409, str(e.detail))
        check("the failed token is given back",
              (await d.inventory.count_documents({"id": t3["inv_id"]})) == 1)
        try:
            await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id="does-not-exist", target="live"),
                                     user=u)
            check("an unknown inventory id is refused", False)
        except HTTPException as e:
            check("an unknown inventory id is refused", e.status_code == 404, str(e.detail))
        # ★ v5 (owner order 2026-08-07 "didnt give me 100% food. should give me
        # 100%"): a live GROWTH redeem also fires a full-food rider through the
        # armed diet lane — grow first, then bp_diet premium, own cmd_id.
        t4 = await _give_token(d, "lv1", "growth", "premium")
        game_ipc.read_restore_status = (
            lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
            {"event": event, "cmd_id": cmd_id} if event in ("bp_grow_ok", "bp_diet_ok") else None)
        sent.clear()
        r4 = await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t4["inv_id"], target="live"), user=u)
        kinds = [c["type"] for c in sent]
        check("a live GROWTH redeem sends the grow AND the full-food rider",
              kinds == ["bp_grow", "bp_diet"], str(kinds))
        check("the food rider is a premium full-fill with its OWN cmd_id",
              sent[1]["tier"] == "premium" and sent[1]["cmd_id"] != sent[0]["cmd_id"], str(sent))
        check("the effects report the food fill",
              any("Comida al 100%" in e for e in r4["effects"]), str(r4["effects"]))
        # rider hiccup: growth landed, food never acked -> token stays spent,
        # the answer says so honestly, nothing is refunded.
        t5 = await _give_token(d, "lv1", "growth", "basic")
        game_ipc.read_restore_status = (
            lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
            {"event": event, "cmd_id": cmd_id} if event == "bp_grow_ok" else None)
        old_rider = bp.LIVE_FOOD_RIDER_TIMEOUT_S
        bp.LIVE_FOOD_RIDER_TIMEOUT_S = 0.3
        try:
            r5 = await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t5["inv_id"], target="live"),
                                          user=u)
        finally:
            bp.LIVE_FOOD_RIDER_TIMEOUT_S = old_rider
        check("a rider timeout keeps the growth and reports honestly",
              any("no se pudo rellenar" in e for e in r5["effects"]), str(r5["effects"]))
        check("the token stays spent when only the rider lagged",
              (await d.inventory.count_documents({"id": t5["inv_id"]})) == 0)
        # a full-food dino: the rider's already_full refusal still reads as fed
        t6 = await _give_token(d, "lv1", "growth", "premium")
        game_ipc.read_restore_status = (
            lambda sid, dino_id=None, event=None, actor_name=None, cmd_id=None:
            {"event": event, "cmd_id": cmd_id} if event == "bp_grow_ok"
            else ({"event": event, "cmd_id": cmd_id, "reason": "already_full"}
                  if event == "bp_diet_failed" else None))
        r6 = await bp.bp_token_redeem(bp.TokenRedeemIn(inv_id=t6["inv_id"], target="live"), user=u)
        check("an already-full food rider still reads as Comida al 100%",
              any("Comida al 100%" in e for e in r6["effects"]), str(r6["effects"]))
    finally:
        game_ipc.mod_alive, game_ipc.write_game_command, game_ipc.read_restore_status = (
            real_alive, real_write, real_read)
        try:
            os.remove(caps)
        except OSError:
            pass


async def case_vault_targets_and_no_dinos():
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="vt1")
    r = await bp.bp_vault_targets(user=u)
    check("a player with nothing parked sees an empty target list", r["targets"] == [], str(r))
    rid = _park(SID, growth=0.42, routes=(2, 4))
    r = await bp.bp_vault_targets(user=u)
    tgt = r["targets"][0]
    check("a parked row is offered as a target with its real growth",
          tgt["id"] == tgt["dino_id"] == rid and abs(tgt["growth"] - 0.42) < 1e-9, str(tgt))
    check("the target reports routes at cap", tgt["routes_at_cap"] is True, str(tgt))
    check("the target resolves its species SLUG and its readable name",
          tgt["species"] == "carno" and tgt["name"] == "Carnotaurus", str(tgt))
    u_nosid = {"id": "nosid", "steam_id": "", "role": "user"}
    try:
        await bp.bp_vault_targets(user=u_nosid)
        check("a player with no Steam link is told to link it", False)
    except HTTPException as e:
        check("a player with no Steam link is told to link it",
              e.status_code == 400 and "Steam" in str(e.detail), str(e.detail))


# =============================================================================
# 7. Tier resolve, gifts, purchases
# =============================================================================
def case_tier_source_precedence():
    check("nobody with no pass document resolves to free", bp.resolve_tier({}, {}) == ("free", "free"))
    check("a stripe purchase resolves to its tier",
          bp.resolve_tier({}, {"tier": "premium_plus", "tier_source": "stripe"})
          == ("premium_plus", "stripe"))
    check("a staff gift resolves to its tier",
          bp.resolve_tier({}, {"tier": "regular", "tier_source": "gift"}) == ("regular", "gift"))
    check("a revoked pass resolves to free",
          bp.resolve_tier({}, {"tier": "free", "tier_source": "revoked"})[0] == "free")
    check("a Patreon membership adds NOTHING on top of a purchase",
          bp.resolve_tier({"patreon_patron_status": "active_patron", "patreon_tier_name": "Apex"},
                          {"tier": "regular", "tier_source": "stripe"}) == ("regular", "stripe"))
    check("tier free can claim no row", bp.TIER_TRACKS["free"] == ())
    check("tier regular claims the regular row only",
          bp.TIER_TRACKS["regular"] == ("regular",))
    check("tier premium_plus claims BOTH rows",
          bp.TIER_TRACKS["premium_plus"] == ("regular", "premium"))
    check("can_claim_track agrees",
          not bp.can_claim_track("free", "regular")
          and bp.can_claim_track("regular", "regular")
          and not bp.can_claim_track("regular", "premium")
          and bp.can_claim_track("premium_plus", "premium"))


async def case_gift_idempotent():
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="admin1", sid="1", role="admin")
    await mk_user(d, uid="gift1")
    r1 = await bp.bp_admin_gift(bp.AdminGiftIn(user="gift1", tier="regular", note="test"),
                                admin=admin)
    check("gift grants the tier", r1["granted"] is True, str(r1))
    r2 = await bp.bp_admin_gift(bp.AdminGiftIn(user="gift1", tier="regular"), admin=admin)
    check("gifting the SAME tier again is a no-op", r2.get("already") is True, str(r2))
    r3 = await bp.bp_admin_gift(bp.AdminGiftIn(user="gift1", tier="premium_plus"), admin=admin)
    check("gifting a HIGHER tier upgrades", r3["granted"] is True, str(r3))
    r4 = await bp.bp_admin_gift(bp.AdminGiftIn(user="gift1", tier="regular"), admin=admin)
    check("gifting a LOWER tier never downgrades", r4.get("already") is True, str(r4))
    p = await d.bp_passes.find_one({"user_id": "gift1"}, {"_id": 0})
    check("the stored tier is the best one granted", p["tier"] == "premium_plus", str(p))
    try:
        await bp.bp_admin_gift(bp.AdminGiftIn(user="nope", tier="regular"), admin=admin)
        check("gifting to an unknown user is refused", False)
    except HTTPException as e:
        check("gifting to an unknown user is refused", e.status_code == 404)


async def case_admin_grant_xp():
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="admin2", sid="2", role="admin")
    await mk_user(d, uid="xp1")
    r = await bp.bp_admin_grant_xp(bp.AdminGrantXpIn(user="xp1", amount=5000), admin=admin)
    check("admin XP grant lands", r["xp"] == 5000 and r["level"] == bp.level_from_xp(5000), str(r))
    r = await bp.bp_admin_grant_xp(bp.AdminGrantXpIn(user="xp1", amount=-99999), admin=admin)
    check("a negative grant can never leave a negative pass", r["xp"] == 0, str(r))
    try:
        await bp.bp_admin_grant_xp(bp.AdminGrantXpIn(user="nope", amount=10), admin=admin)
        check("granting XP to an unknown user is refused", False)
    except HTTPException as e:
        check("granting XP to an unknown user is refused", e.status_code == 404)


def case_checkout_plan_prices():
    check("free -> regular costs $5",
          bp._checkout_plan("free", "regular") == {"lookup_key": "bp_regular_monthly",
                                                   "amount": 500, "upgrade": False})
    check("free -> premium_plus costs $10",
          bp._checkout_plan("free", "premium_plus") == {"lookup_key": "bp_premium_plus_monthly",
                                                        "amount": 1000, "upgrade": False})
    check("regular -> premium_plus uses the $5 UPGRADE price",
          bp._checkout_plan("regular", "premium_plus") == {"lookup_key": "bp_upgrade_monthly",
                                                           "amount": 500, "upgrade": True})
    for cur, want, label in (("regular", "regular", "same tier"),
                             ("premium_plus", "regular", "lower tier"),
                             ("premium_plus", "premium_plus", "same top tier")):
        try:
            bp._checkout_plan(cur, want)
            check(f"checkout at the {label} is refused", False)
        except HTTPException as e:
            check(f"checkout at the {label} is refused", e.status_code == 400, str(e.detail))
    try:
        bp._checkout_plan("free", "nonsense")
        check("an invalid tier is refused", False)
    except HTTPException as e:
        check("an invalid tier is refused", e.status_code == 400)


async def case_checkout_503_without_stripe():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="ck1")
    try:
        await bp.bp_checkout(bp.CheckoutIn(tier="regular"), user=u)
        check("checkout answers 503 when Stripe is unavailable", False, "checkout succeeded")
    except HTTPException as e:
        check("checkout answers 503 when Stripe is unavailable",
              e.status_code == 503 and e.detail == bp.PAY_UNAVAILABLE, f"{e.status_code} {e.detail}")
    s = await bp.bp_status(user=u)
    check("everything else still works with no Stripe", s["level"] == 1)


# =============================================================================
# 8. Stripe webhook
# =============================================================================
async def case_webhook_unsigned_and_bad_signature():
    d = fresh_db()
    await seed_indexes(d)
    try:
        await bp.bp_stripe_webhook(FakeRequest(b'{"id":"evt_1"}', {}))
        check("an UNSIGNED webhook is refused", False, "webhook accepted")
    except HTTPException as e:
        check("an UNSIGNED webhook is refused",
              e.status_code == 400 and "Firma" in str(e.detail), str(e.detail))
    check("an unsigned webhook never records an event",
          (await d.bp_stripe_events.count_documents({})) == 0)

    real = bp._stripe_construct_event

    def _bad(raw, sig):
        raise ValueError("Invalid signature")

    bp._stripe_construct_event = _bad
    try:
        await bp.bp_stripe_webhook(FakeRequest(b'{"id":"evt_1"}', {"stripe-signature": "t=1,v1=xx"}))
        check("a webhook with an INVALID signature is refused", False)
    except HTTPException as e:
        check("a webhook with an INVALID signature is refused",
              e.status_code == 400 and "inválida" in str(e.detail), str(e.detail))
    finally:
        bp._stripe_construct_event = real
    check("a bad-signature webhook never records an event",
          (await d.bp_stripe_events.count_documents({})) == 0)

    bp._stripe_construct_event = lambda raw, sig: (_ for _ in ()).throw(bp._StripeUnavailable())
    try:
        await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a webhook with no Stripe key answers 503", False)
    except HTTPException as e:
        check("a webhook with no Stripe key answers 503",
              e.status_code == 503 and e.detail == bp.PAY_UNAVAILABLE, str(e.detail))
    finally:
        bp._stripe_construct_event = real


def _session_event(evt_id, session_id, user_id, season, tier):
    return {"id": evt_id, "type": "checkout.session.completed",
            "data": {"object": {"id": session_id,
                                "metadata": {"user_id": user_id, "season": season, "tier": tier}}}}


async def case_webhook_grant_replay_and_not_paid():
    d = fresh_db()
    await seed_indexes(d)
    await mk_user(d, uid="wh1")
    season = bp.current_season_id()
    real_ev, real_sess = bp._stripe_construct_event, bp._stripe_retrieve_session
    paid = {"id": "cs_1", "payment_status": "paid",
            "metadata": {"user_id": "wh1", "season": season, "tier": "premium_plus"}}
    bp._stripe_construct_event = lambda raw, sig: _session_event("evt_1", "cs_1", "wh1", season,
                                                                 "premium_plus")
    bp._stripe_retrieve_session = lambda sid: dict(paid)
    try:
        await d.bp_payments.insert_one({"id": "p1", "session_id": "cs_1", "user_id": "wh1",
                                        "season": season, "tier": "premium_plus", "amount": 1000,
                                        "status": "pending", "bp_applied": False,
                                        "payment_intent": "pi_1", "created_at": bp._now_iso()})
        r = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a signed, re-fetched, PAID session grants the tier", r.get("granted") is True, str(r))
        p = await d.bp_passes.find_one({"user_id": "wh1"}, {"_id": 0})
        check("the pass is stored as premium_plus / stripe",
              p["tier"] == "premium_plus" and p["tier_source"] == "stripe", str(p))
        row = await d.bp_payments.find_one({"session_id": "cs_1"}, {"_id": 0})
        check("the payment row is flagged applied",
              row["bp_applied"] is True and row["status"] == "paid")

        r2 = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a REPLAYED event id is a no-op", r2.get("duplicate") is True, str(r2))
        check("the replay recorded no second event",
              (await d.bp_stripe_events.count_documents({})) == 1)

        bp._stripe_construct_event = lambda raw, sig: _session_event("evt_2", "cs_1", "wh1",
                                                                     season, "premium_plus")
        r3 = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a NEW event for an already-applied session is a no-op",
              r3.get("duplicate_session") is True, str(r3))

        await mk_user(d, uid="wh2", sid=SID2)
        bp._stripe_construct_event = lambda raw, sig: _session_event("evt_3", "cs_2", "wh2",
                                                                     season, "premium_plus")
        bp._stripe_retrieve_session = lambda sid: {"id": "cs_2", "payment_status": "unpaid",
                                                   "metadata": {"user_id": "wh2", "season": season,
                                                                "tier": "premium_plus"}}
        await d.bp_payments.insert_one({"id": "p2", "session_id": "cs_2", "user_id": "wh2",
                                        "season": season, "tier": "premium_plus",
                                        "status": "pending", "bp_applied": False,
                                        "created_at": bp._now_iso()})
        r4 = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a session Stripe reports as NOT PAID is refused",
              r4.get("granted") is False and r4.get("reason") == "not_paid", str(r4))
        p2 = await d.bp_passes.find_one({"user_id": "wh2"}, {"_id": 0})
        check("the unpaid session granted nothing", (p2 or {}).get("tier") in (None, "free"), str(p2))

        await mk_user(d, uid="wh3", sid="76561199000000077")
        bp._stripe_construct_event = lambda raw, sig: _session_event("evt_4", "cs_3", "wh3",
                                                                     "2025-01", "regular")
        bp._stripe_retrieve_session = lambda sid: {"id": "cs_3", "payment_status": "paid",
                                                   "metadata": {"user_id": "wh3",
                                                                "season": "2025-01",
                                                                "tier": "regular"}}
        r5 = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
        check("a purchase for a season that already ENDED is not granted",
              r5.get("granted") is False and r5.get("needs_review") is True, str(r5))
    finally:
        bp._stripe_construct_event, bp._stripe_retrieve_session = real_ev, real_sess


async def case_webhook_refund_revokes():
    d = fresh_db()
    await seed_indexes(d)
    await mk_user(d, uid="rf1")
    season = bp.current_season_id()
    await d.bp_payments.insert_one({"id": "p9", "session_id": "cs_9", "user_id": "rf1",
                                    "season": season, "tier": "premium_plus", "status": "paid",
                                    "bp_applied": True, "payment_intent": "pi_9",
                                    "created_at": bp._now_iso()})
    u = await d.users.find_one({"id": "rf1"}, {"_id": 0})
    await bp.grant_tier(u, season, "premium_plus", "stripe")
    await bp._claim_one(u, season, "premium", 4, "premium_plus", None)
    real = bp._stripe_construct_event
    for evt_id, etype in (("evt_r1", "charge.refunded"), ("evt_r2", "charge.dispute.created")):
        await d.bp_passes.update_one({"user_id": "rf1", "season": season},
                                     {"$set": {"tier": "premium_plus", "tier_source": "stripe"}})
        bp._stripe_construct_event = (lambda e, t: (lambda raw, sig: {
            "id": e, "type": t,
            "data": {"object": {"id": "ch_9", "payment_intent": "pi_9"}}}))(evt_id, etype)
        try:
            r = await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
            check(f"{etype} revokes the pass", r.get("revoked") is True, str(r))
            p = await d.bp_passes.find_one({"user_id": "rf1"}, {"_id": 0})
            check(f"{etype} drops the tier to free",
                  p["tier"] == "free" and p["tier_source"] == "revoked", str(p))
        finally:
            bp._stripe_construct_event = real
    n = await d.bp_claims.count_documents({"user_id": "rf1"})
    check("already-claimed rewards SURVIVE a refund", n == 1, str(n))
    row = await d.bp_payments.find_one({"session_id": "cs_9"}, {"_id": 0})
    check("the payment row records the refund", row["status"] == "refunded", str(row))
    u = await d.users.find_one({"id": "rf1"}, {"_id": 0})
    try:
        await bp.bp_claim(bp.ClaimIn(track="premium", level=5), user=u)
        check("a REVOKED pass can no longer claim", False, "claim succeeded")
    except HTTPException as e:
        check("a REVOKED pass can no longer claim", e.status_code == 403, str(e.detail))


async def case_payment_status_owner_only():
    d = fresh_db()
    await seed_indexes(d)
    a = await mk_user(d, uid="pay1")
    b = await mk_user(d, uid="pay2", sid=SID2)
    await d.bp_payments.insert_one({"id": "px", "session_id": "cs_x", "user_id": "pay1",
                                    "season": bp.current_season_id(), "tier": "regular",
                                    "status": "paid", "bp_applied": True,
                                    "created_at": bp._now_iso()})
    r = await bp.bp_payment_status("cs_x", user=a)
    check("the session OWNER can poll its status", r["payment_status"] == "paid", str(r))
    try:
        await bp.bp_payment_status("cs_x", user=b)
        check("another player cannot read somebody else's payment", False)
    except HTTPException as e:
        check("another player cannot read somebody else's payment", e.status_code == 404)


# =============================================================================
# 9. Season settle
# =============================================================================
async def case_settle_idempotent_and_absent_player():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="s1")
    past = "2025-01"
    await d.bp_passes.insert_one({"id": "sp1", "user_id": "s1", "season": past,
                                  "xp": bp.xp_for_level(30), "tier": "premium_plus",
                                  "tier_source": "gift", "settled": False,
                                  "created_at": bp._now_iso()})
    await bp._claim_one(u, past, "regular", 1, "premium_plus", None)
    before_claims = await d.bp_claims.count_documents({"user_id": "s1"})

    res = await bp.settle_ended_seasons()
    check("the sweep settles an ABSENT player's ended season", res["settled"] == 1, str(res))
    p = await d.bp_passes.find_one({"user_id": "s1", "season": past}, {"_id": 0})
    check("the pass is marked settled", p["settled"] is True, str(p))
    claims = await d.bp_claims.find({"user_id": "s1", "season": past}, {"_id": 0}).to_list(500)
    levels = {(c["track"], c["level"]) for c in claims}
    check("settle auto-granted the unclaimed non-choice cells",
          len(claims) > before_claims, f"{len(claims)} vs {before_claims}")
    check("settle covers BOTH rows for a Premium+ pass",
          {t for t, _lv in levels} == {"regular", "premium"}, str(sorted(levels)))
    check("settle did NOT auto-grant the level-25 dino CHOICE",
          ("regular", 25) not in levels and ("premium", 25) not in levels, str(sorted(levels)))
    check("settle did not grant anything above the player's level",
          all(lv <= 30 for _t, lv in levels), str(sorted(levels)))
    check("settle skipped every empty regular cell",
          not any(t == "regular" and lv % 10 in (3, 7) for t, lv in levels))
    check("settle counted the expired choice cells", p["settle_expired"] >= 2, str(p))

    coins_after = (await d.users.find_one({"id": "s1"}, {"_id": 0}))["coins"]
    res2 = await bp.settle_ended_seasons()
    check("a second sweep settles nothing new", res2["settled"] == 0, str(res2))
    claims2 = await d.bp_claims.count_documents({"user_id": "s1"})
    check("settle is IDEMPOTENT (no cell paid twice)", claims2 == len(claims), f"{claims2}")
    check("a re-run pays no extra currency",
          (await d.users.find_one({"id": "s1"}, {"_id": 0}))["coins"] == coins_after)

    await d.bp_passes.insert_one({"id": "sp2", "user_id": "s1", "season": bp.current_season_id(),
                                  "xp": 100, "tier": "free", "tier_source": "free",
                                  "settled": False, "created_at": bp._now_iso()})
    res3 = await bp.settle_ended_seasons()
    check("the CURRENT season is never settled early", res3["settled"] == 0, str(res3))


async def case_settle_reaches_past_a_wall_of_current_passes():
    """The sweep is limited. If it scanned every unsettled pass, a server with
    more active players than the limit would never REACH the ended seasons."""
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    cur = bp.current_season_id()
    for i in range(60):
        await d.bp_passes.insert_one({"id": f"cur{i}", "user_id": f"cur{i}", "season": cur,
                                      "xp": 500, "tier": "free", "tier_source": "free",
                                      "settled": False, "created_at": bp._now_iso()})
    await mk_user(d, uid="wall1")
    await d.bp_passes.insert_one({"id": "old1", "user_id": "wall1", "season": "2025-03",
                                  "xp": bp.xp_for_level(6), "tier": "regular",
                                  "tier_source": "gift", "settled": False,
                                  "created_at": bp._now_iso()})
    res = await bp.settle_ended_seasons(limit=5)
    check("the sweep reaches the ended season past 60 current-season passes",
          res["settled"] == 1, str(res))
    p = await d.bp_passes.find_one({"user_id": "wall1", "season": "2025-03"}, {"_id": 0})
    check("that pass is settled", p["settled"] is True, str(p))
    check("no current-season pass was settled",
          (await d.bp_passes.count_documents({"season": cur, "settled": True})) == 0)


async def case_settle_grants_nothing_without_a_pass():
    """An ended season for a player who never bought must bank NOTHING."""
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    await mk_user(d, uid="s2")
    past = "2025-02"
    await d.bp_passes.insert_one({"id": "sp3", "user_id": "s2", "season": past,
                                  "xp": bp.xp_for_level(40), "tier": "free",
                                  "tier_source": "free", "settled": False,
                                  "created_at": bp._now_iso()})
    await bp.settle_ended_seasons()
    check("a player with no pass is settled with ZERO grants",
          (await d.bp_claims.count_documents({"user_id": "s2"})) == 0)
    check("...and paid no currency",
          int((await d.users.find_one({"id": "s2"}, {"_id": 0}))["coins"]) == 0)
    p = await d.bp_passes.find_one({"user_id": "s2", "season": past}, {"_id": 0})
    check("...but the pass is still marked settled", p["settled"] is True, str(p))


async def case_settle_regular_row_only_for_a_regular_pass():
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    await mk_user(d, uid="s4")
    past = "2025-04"
    await d.bp_passes.insert_one({"id": "sp4", "user_id": "s4", "season": past,
                                  "xp": bp.xp_for_level(12), "tier": "regular",
                                  "tier_source": "stripe", "settled": False,
                                  "created_at": bp._now_iso()})
    await bp.settle_ended_seasons()
    claims = await d.bp_claims.find({"user_id": "s4"}, {"_id": 0}).to_list(500)
    check("a $5 pass is settled on the REGULAR row only",
          claims and all(c["track"] == "regular" for c in claims),
          str(sorted({c["track"] for c in claims})))


async def case_claim_refused_after_settle():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="s3")
    season = bp.current_season_id()
    await bp._get_pass("s3", season)
    await d.bp_passes.update_one({"user_id": "s3", "season": season},
                                 {"$set": {"xp": bp.xp_for_level(20), "tier": "regular",
                                           "tier_source": "gift", "settled": True}})
    try:
        await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
        check("a settled season refuses new claims", False)
    except HTTPException as e:
        check("a settled season refuses new claims",
              e.status_code == 400 and "cerró" in str(e.detail), str(e.detail))


# =============================================================================
# 10. Admin + the page contract
# =============================================================================
async def case_admin_overview_and_settle_button():
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="admin3", sid="3", role="admin")
    await mk_user(d, uid="plain3", sid=SID2)
    await bp._get_pass("plain3", bp.current_season_id())
    r = await bp.bp_admin_overview(admin=admin)
    check("admin overview counts the passes", r["passes"] >= 1, str(r["passes"]))
    check("admin overview reports the season name",
          r["season"]["name"] == bp.season_display_name(bp.current_season_id()))
    r = await bp.bp_admin_settle(bp.AdminSettleIn(), admin=admin)
    check("the admin settle button runs the sweep", r["success"] is True, str(r))


async def case_auth_gates_are_wired():
    """The admin gate lives in the DEPENDENCY, so calling a handler directly (as
    every test above does) bypasses it. Both halves are proven here instead."""
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="ag1", sid="9", role="admin")
    plain = await mk_user(d, uid="ag2", sid=SID2)
    check("the admin dependency accepts an admin",
          (await bp._require_admin(user=admin))["id"] == "ag1")
    try:
        await bp._require_admin(user=plain)
        check("the admin dependency REFUSES a non-admin", False, "no exception")
    except HTTPException as e:
        check("the admin dependency REFUSES a non-admin", e.status_code == 403, str(e.detail))
    try:
        await bp._require_admin(user={"id": "x"})
        check("the admin dependency refuses a user with no role", False)
    except HTTPException as e:
        check("the admin dependency refuses a user with no role", e.status_code == 403)

    admin_paths, user_paths, open_paths = [], [], []
    for route in bp.router.routes:
        calls = {dep.call for dep in route.dependant.dependencies}
        if bp._require_admin in calls:
            admin_paths.append(route.path)
        elif bp._require_user in calls:
            user_paths.append(route.path)
        else:
            open_paths.append(route.path)
    check("every /admin/ route is admin-gated",
          sorted(admin_paths) == sorted(p for p in admin_paths + user_paths + open_paths
                                        if "/admin/" in p), str(admin_paths))
    check("every non-admin route requires a signed-in user",
          all("/admin/" not in p for p in user_paths) and len(user_paths) == 8,
          str(sorted(user_paths)))
    check("the ONLY unauthenticated route is the Stripe webhook (signature-gated)",
          open_paths == ["/battle-pass/stripe-webhook"], str(open_paths))


async def case_status_matches_the_page_contract():
    """★ Every field name the pass page greps for, pinned against the REAL
    payload builders. A rename here is a blank screen there."""
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="fc1")
    await set_xp(d, "fc1", bp.xp_for_level(30), tier=bp.TIER_REGULAR, source="stripe")
    s = await bp.bp_status(user=u)

    top = {"season", "level", "xp", "tier", "tier_source", "claimable_count",
           "regular_track", "premium_track", "free_track", "pass_track",
           "claimed", "dino_bands", "live_tokens_enabled"}
    check("status carries every top-level field the page reads",
          top <= set(s), str(sorted(top - set(s))))
    check("status keeps this module's own extras too",
          {"tokens", "payments_enabled", "prices", "rules", "claimable_tracks"} <= set(s))
    check("season carries name + ends_at (header + countdown + end banner)",
          {"name", "ends_at", "id"} <= set(s["season"]))
    check("level is a plain int beside xp as the PROGRESS object",
          isinstance(s["level"], int)
          and {"max_level", "percent", "xp_in_level", "xp_span"} <= set(s["xp"]),
          f"level={s['level']!r} xp={sorted(s['xp'])}")

    await bp.bp_claim(bp.ClaimIn(track="regular", level=1), user=u)
    s = await bp.bp_status(user=u)
    check("claimed is keyed exactly \"track:level\"",
          s["claimed"].get("regular:1") is True and "premium:1" not in s["claimed"],
          str(sorted(s["claimed"])[:4]))

    before = s["claimable_count"]
    r = await bp.bp_claim_all(user=u)
    check("claimable_count equals the rows claim-all actually grants",
          before == r["claimed_count"], f"{before} != {r['claimed_count']}")
    check("claimable_count drops to 0 once everything is claimed",
          (await bp.bp_status(user=u))["claimable_count"] == 0)

    s = await bp.bp_status(user=u)
    by_type = {}
    for c in s["premium_track"] + s["regular_track"]:
        by_type.setdefault(c["type"], c)
    check("every cell carries level + type",
          all({"level", "type"} <= set(c) for c in s["premium_track"]))
    check("currency cells carry `amount` literally",
          by_type["coins"]["amount"] > 0 and "amount_granted" not in by_type["coins"],
          str(by_type["coins"]))
    check("token cells carry token + tier (the FLAVOUR, not the pass tier)",
          {"token", "tier"} <= set(by_type["token"])
          and by_type["token"]["tier"] in ("basic", "premium"), str(by_type["token"]))
    check("skin cells carry skin as an OBJECT with name + rarity",
          isinstance(by_type["skin"]["skin"], dict)
          and {"name", "rarity"} <= set(by_type["skin"]["skin"]), str(by_type["skin"]))
    check("dino cells carry band, and slug only when FIXED",
          all("band" in c and ("slug" in c) == (c["level"] == 100)
              for c in s["premium_track"] if c["type"] == "dino"))
    check("premium-row token cells are PREMIUM flavour",
          all(c["tier"] == "premium" for c in s["premium_track"] if c["type"] == "token"))
    check("regular-row token cells are BASIC flavour",
          all(c["tier"] == "basic" for c in s["regular_track"] if c["type"] == "token"))


async def case_claim_responses_match_the_page_contract():
    _wipe_vault()
    PARK_CAP[0] = 0
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="fc2")
    # level 60: the skin-shape pin claims the level-55 cell (20 was retired).
    await set_xp(d, "fc2", bp.xp_for_level(60), tier=bp.TIER_PREMIUM, source="stripe")

    lit = bp.cell_at("premium", 8)["amount"]
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=8), user=u)
    check("claim answers ok + reward + coins + vip_coins",
          r["ok"] is True and {"reward", "coins", "vip_coins"} <= set(r), str(sorted(r)))
    check("claim's reward carries the literal amount", r["reward"]["amount"] == lit, str(r["reward"]))
    check("claim's balance mirrors the wallet (applyBalance reads these two)",
          r["vip_coins"] == (await d.users.find_one({"id": "fc2"}, {"_id": 0}))["vip_coins"])

    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=10), user=u)
    check("a token claim's reward carries token + tier",
          r["reward"]["type"] == "token" and r["reward"]["token"] == "diet"
          and r["reward"]["tier"] == "premium", str(r["reward"]))
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=55), user=u)
    check("a skin claim's reward carries skin.name",
          r["reward"]["skin"]["name"] == "Vacío Primigenio", str(r["reward"]))
    # 2026-08-13: the level-20 cell (retired with bp_s_sol on 08-08) is
    # re-opened; 2026-08-16 it grants constelacion, the pink-glitter design.
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=20), user=u)
    check("the re-opened level-20 cell grants constelacion",
          r["reward"]["skin"]["name"] == "Constelación", str(r["reward"]))
    r = await bp.bp_claim(bp.ClaimIn(track="premium", level=25, choice="dryo"), user=u)
    check("a dino claim's reward carries the PICKED slug",
          r["reward"]["type"] == "dino" and r["reward"]["slug"] == "dryo", str(r["reward"]))

    ra = await bp.bp_claim_all(user=u)
    check("claim-all answers ok + a claimed ARRAY + balances",
          ra["ok"] is True and isinstance(ra["claimed"], list)
          and {"coins", "vip_coins"} <= set(ra), str(sorted(ra)))
    check("each claim-all row carries track + level + reward",
          all({"track", "level", "reward"} <= set(row) for row in ra["claimed"]),
          str(ra["claimed"][:1]))
    amber = next((row for row in ra["claimed"] if row["reward"]["type"] == "amber"), None)
    check("claim-all rows carry the literal amount",
          amber and amber["reward"]["amount"] == bp.cell_at(amber["track"], amber["level"])["amount"],
          str(amber))


async def case_token_and_vault_shapes_match_the_page():
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="fc3")
    t = await bp._grant_token(u, "growth", "premium", bp.current_season_id())
    r = await bp.bp_tokens(user=u)
    row = r["tokens"][0]
    check("a token row carries inv_id/id + token + tier",
          row["inv_id"] == row["id"] == t["inv_id"] and row["token"] == "growth"
          and row["tier"] == "premium", str(row))
    check("the stored document keeps token_tier as its canonical column",
          row["token_tier"] == "premium")
    check("status.tokens carries the same shape",
          (await bp.bp_status(user=u))["tokens"][0]["tier"] == "premium")

    rid = _park(SID, growth=0.42, routes=(2, 4))
    v = await bp.bp_vault_targets(user=u)
    tgt = v["targets"][0]
    check("a vault target carries id + species + name + growth + prime + routes_at_cap + deployed",
          {"id", "species", "name", "growth", "prime", "routes_at_cap", "deployed"} <= set(tgt),
          str(sorted(tgt)))
    check("`species` is the SLUG (the row renders /dinos/<species>.png)",
          tgt["species"] == "carno", str(tgt["species"]))
    check("`name` is the readable species name", tgt["name"] == "Carnotaurus", str(tgt["name"]))
    check("a parked row is not `deployed`", tgt["deployed"] is False)
    check("`prime` is a bool", tgt["prime"] is False)

    # v5: the parked target is live-only-refused; the WIRE MODEL still accepts
    # vault_id/dino_id (an old tab must get the honest refusal, never a 422).
    try:
        await bp.bp_token_redeem(
            bp.TokenRedeemIn(inv_id=t["inv_id"], target="parked", vault_id=rid), user=u)
        check("a parked redeem from an old tab gets the live-only refusal", False)
    except HTTPException as e:
        check("a parked redeem from an old tab gets the live-only refusal",
              e.status_code == 400 and "EN VIVO" in str(e.detail), str(e.detail))
    check("dino_id still works as an alias",
          bp.TokenRedeemIn(inv_id="x", target="parked", dino_id=7).row_id == 7)


async def case_admin_shapes_match_the_page():
    _wipe_vault()
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="fc4", sid="4242", role="admin")
    await mk_user(d, uid="fc5", sid="76561199000000500", persona_name="Moonveil")
    season = bp.current_season_id()

    g = await bp.bp_admin_gift(bp.AdminGiftIn(user="Moonveil", tier="regular", note="x"),
                               admin=admin)
    check("gift resolves a player by NAME", g["ok"] is True and g["user_id"] == "fc5", str(g))
    g2 = await bp.bp_admin_gift(bp.AdminGiftIn(user="76561199000000500", tier="premium_plus"),
                                admin=admin)
    check("gift resolves a player by STEAM ID", g2["granted"] is True, str(g2))
    x = await bp.bp_admin_grant_xp(bp.AdminGrantXpIn(user="Moonveil", amount=2000), admin=admin)
    check("grant-xp resolves the same way", x["xp"] == 2000, str(x))
    try:
        await bp.bp_admin_gift(bp.AdminGiftIn(user="nadie", tier="regular"), admin=admin)
        check("an unknown player is refused honestly", False)
    except HTTPException as e:
        check("an unknown player is refused honestly", e.status_code == 404, str(e.detail))
    await mk_user(d, uid="fc6", sid="76561199000000501", persona_name="Moonveil")
    try:
        await bp.bp_admin_gift(bp.AdminGiftIn(user="Moonveil", tier="regular"), admin=admin)
        check("an AMBIGUOUS name is refused rather than guessing", False)
    except HTTPException as e:
        check("an AMBIGUOUS name is refused rather than guessing",
              e.status_code == 400 and "Steam ID" in str(e.detail), str(e.detail))

    await d.bp_payments.insert_one({"id": "pa", "session_id": "cs_a", "user_id": "fc5",
                                    "season": season, "tier": "premium_plus", "amount": 1000,
                                    "status": "paid", "bp_applied": True, "upgrade": False,
                                    "created_at": bp._now_iso()})
    ov = await bp.bp_admin_overview(admin=admin)
    check("overview carries season as an OBJECT with name + id + ends_at",
          isinstance(ov["season"], dict) and {"id", "name", "ends_at"} <= set(ov["season"]),
          str(ov["season"]))
    check("overview carries buyers{regular,premium_plus,gift}",
          {"regular", "premium_plus", "gift"} <= set(ov["buyers"]), str(ov["buyers"]))
    check("buyers counts the gifted pass", ov["buyers"]["gift"] == 1, str(ov["buyers"]))
    check("overview carries claims_count", isinstance(ov["claims_count"], int))
    check("overview carries revenue_cents (the card divides by 100)",
          ov["revenue_cents"] == 1000, str(ov["revenue_cents"]))
    check("overview carries a purchases feed with at/user_name/tier/source/status",
          ov["purchases"] and {"at", "user_name", "tier", "source", "status"} <= set(ov["purchases"][0]),
          str(ov["purchases"][:1]))
    check("the purchases feed includes the staff GIFT, not just Stripe rows",
          any(p["source"] == "gift" for p in ov["purchases"]),
          str([p["source"] for p in ov["purchases"]]))
    check("purchase sources are labels the table knows",
          {p["source"] for p in ov["purchases"]} <= {"stripe", "upgrade", "gift", "patreon", "purchase"})
    check("purchase statuses are labels the table knows",
          {p["status"] for p in ov["purchases"]} <= {"paid", "pending", "expired", "refunded", "revoked"})
    check("overview resolves user_name for the table",
          all(p["user_name"] for p in ov["purchases"]), str(ov["purchases"]))
    st = await bp.bp_admin_settle(bp.AdminSettleIn(), admin=admin)
    check("settle answers both `settled` and `count`", st["settled"] == st["count"], str(st))


async def case_checkout_and_payment_shapes():
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="fc7")
    real_price, real_sess, real_cat = (bp._stripe_price_id, bp._stripe_create_session,
                                       bp.ensure_catalog)
    bp.ensure_catalog = lambda: {"ready": True}
    bp._stripe_price_id = lambda key: f"price_{key}"
    seen_urls = {}
    bp._stripe_create_session = (lambda pid, meta, ok, cancel:
                                 (seen_urls.update({"ok": ok, "cancel": cancel}) or
                                  {"id": "cs_z", "url": "https://checkout.stripe.com/c/pay/cs_z",
                                   "_meta": meta}))
    try:
        r = await bp.bp_checkout(bp.CheckoutIn(tier="premium_plus"), user=u)
        check("checkout answers `checkout_url` (the modal redirects on it)",
              r["checkout_url"].startswith("https://checkout.stripe.com/"), str(r))
        check("the success URL is the pass PAGE with the bp_session placeholder",
              seen_urls.get("ok") == f"{bp.PUBLIC_SITE_URL}/battle-pass"
                                     "?bp_session={CHECKOUT_SESSION_ID}",
              str(seen_urls))
        check("the cancel URL returns to the pass page too",
              seen_urls.get("cancel") == f"{bp.PUBLIC_SITE_URL}/battle-pass", str(seen_urls))
        p = await bp.bp_payment_status("cs_z", user=u)
        check("payment answers `payment_status` (the poll stops on paid/expired)",
              p["payment_status"] == "pending", str(p))
        check("payment carries bp_tier + bp_applied",
              p["bp_tier"] == "premium_plus" and p["bp_applied"] is False, str(p))
    finally:
        bp._stripe_price_id, bp._stripe_create_session, bp.ensure_catalog = (
            real_price, real_sess, real_cat)

    real_ev = bp._stripe_construct_event
    bp._stripe_construct_event = lambda raw, sig: {
        "id": "evt_x", "type": "checkout.session.expired", "data": {"object": {"id": "cs_z"}}}
    try:
        await bp.bp_stripe_webhook(FakeRequest(b'{}', {"stripe-signature": "t=1"}))
    finally:
        bp._stripe_construct_event = real_ev
    p = await bp.bp_payment_status("cs_z", user=u)
    check("an expired checkout reports payment_status=expired",
          p["payment_status"] == "expired", str(p))


# =============================================================================
# Season rename (owner-editable name, 2026-08-07)
# =============================================================================
def case_season_code_is_structural():
    """★ The money labels used to take the season code by SPLITTING the display
    name on " · ". A custom name without that separator would have dropped the
    whole title into a transaction line. The code is derived from the id now."""
    check("season code of the first season is S01", bp.season_code("2026-01") == "S01")
    check("season code of the live season is S08", bp.season_code("2026-08") == "S08")
    check("season code rolls past the year", bp.season_code("2027-01") == "S13")
    check("a malformed season id still yields a code", bp.season_code("nope") == "S--")
    check("a malformed season id still yields a name",
          bp.season_display_name("nope") == "Pase de Batalla")
    check("month 13 is refused as malformed", bp._season_parts("2026-13") is None)
    check("month 0 is refused as malformed", bp._season_parts("2026-00") is None)
    check("an empty season id is refused", bp._season_parts("") is None)
    src = inspect.getsource(bp)
    check("no label splits the display name any more", "' · ')[0]" not in src)


def case_season_name_sanitizer():
    NUL, TAB, LF, DEL = chr(0), chr(9), chr(10), chr(127)
    check("a plain name survives untouched",
          bp.sanitize_season_name("Cacería Bajo el Sol") == "Cacería Bajo el Sol")
    check("surrounding spaces are trimmed",
          bp.sanitize_season_name("   Sol   ") == "Sol")
    check("runs of spaces collapse to one",
          bp.sanitize_season_name("La    Gran   Caza") == "La Gran Caza")
    check("newlines and tabs become one space",
          bp.sanitize_season_name("La" + LF + TAB + "Caza") == "La Caza")
    check("control characters never reach the header",
          bp.sanitize_season_name("So" + NUL + "l" + DEL) == "So l")
    check("an empty name is empty (that is how the default comes back)",
          bp.sanitize_season_name("") == "")
    check("a whitespace-only name is empty", bp.sanitize_season_name("   " + TAB) == "")
    check("None is empty, not the string None", bp.sanitize_season_name(None) == "")
    check("a number is accepted as text", bp.sanitize_season_name(2026) == "2026")
    long_name = "A" * 400
    check(f"a huge name is capped at {bp.SEASON_NAME_MAX}",
          len(bp.sanitize_season_name(long_name)) == bp.SEASON_NAME_MAX)
    check("the cap never leaves a trailing space",
          bp.sanitize_season_name(("B" * 47) + "   C") == "B" * 47)
    check("emoji and accents survive",
          bp.sanitize_season_name("Caza 🦖 Ámbar") == "Caza 🦖 Ámbar")


def case_season_name_render():
    s = "2026-08"
    default = bp.season_display_name(s)
    check("no override renders the built-in name", bp.render_season_name(s, None) == default)
    check("an empty override renders the built-in name",
          bp.render_season_name(s, {"name": "   "}) == default)
    check("a name keeps the code and the year",
          bp.render_season_name(s, {"name": "La Gran Caza"}) == "S08 · La Gran Caza 2026")
    check("verbatim means EXACTLY what he typed",
          bp.render_season_name(s, {"name": "La Gran Caza", "verbatim": True}) == "La Gran Caza")
    check("verbatim with an empty name still falls back",
          bp.render_season_name(s, {"name": "", "verbatim": True}) == default)
    check("a malformed season id still renders the typed name",
          bp.render_season_name("nope", {"name": "La Gran Caza"}) == "La Gran Caza")


async def case_season_name_override_end_to_end():
    d = fresh_db()
    await seed_indexes(d)
    admin = await mk_user(d, uid="sn_admin", sid="7", role="admin")
    u = await mk_user(d, uid="sn_u1", sid=SID)
    season = bp.current_season_id()
    default = bp.season_display_name(season)

    s = await bp.bp_status(user=u)
    check("the page starts on the built-in name", s["season"]["name"] == default, s["season"]["name"])

    r = await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name="La Gran Caza"), admin=admin)
    check("the rename answers with what the page will show",
          r["name"] == f"S08 · La Gran Caza {season[:4]}" or r["name"].endswith("La Gran Caza " + season[:4]),
          r["name"])
    s = await bp.bp_status(user=u)
    check("the pass page shows the new name at once", s["season"]["name"] == r["name"], s["season"]["name"])

    ov = await bp.bp_admin_overview(admin=admin)
    check("the admin tab shows the new name", ov["season"]["name"] == r["name"])
    check("the admin tab reports the text as typed", ov["season_name_text"] == "La Gran Caza")
    check("the admin tab knows the name is custom", ov["season_name_custom"] is True)
    check("the admin tab carries the built-in name for the reset button",
          ov["season_name_default"] == default)
    check("the admin tab reports the mode", ov["season_name_verbatim"] is False)

    r = await bp.bp_admin_season_name(
        bp.AdminSeasonNameIn(name="Temporada de Sangre", verbatim=True), admin=admin)
    check("verbatim drops the code and the year", r["name"] == "Temporada de Sangre", r["name"])
    s = await bp.bp_status(user=u)
    check("the page follows verbatim too", s["season"]["name"] == "Temporada de Sangre")

    # ★ the exact shape the old split-the-name label would have mangled.
    await bp._grant_skin(await d.users.find_one({"id": "sn_u1"}, {"_id": 0}),
                         glitch_catalog.BP_SKINS[0]["id"], season)
    sk = await d.reward_skins.find_one({"user_id": "sn_u1"}, {"_id": 0})
    check("a granted skin still credits the season CODE, never the custom name",
          sk["source"] == f"Pase de Batalla {bp.season_code(season)}", str(sk.get("source")))

    r = await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name=""), admin=admin)
    check("clearing the box restores the built-in name", r["name"] == default, r["name"])
    check("clearing reports the name is no longer custom", r["custom"] is False)
    s = await bp.bp_status(user=u)
    check("the page goes back to the built-in name", s["season"]["name"] == default)
    check("clearing DELETES the row rather than storing an empty one",
          (await d.bp_seasons.count_documents({})) == 0)

    long_name = "Z" * 300
    r = await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name=long_name), admin=admin)
    check("a 300-character name is stored capped, not rejected",
          len(r["text"]) == bp.SEASON_NAME_MAX and r["text"] == "Z" * bp.SEASON_NAME_MAX)
    s = await bp.bp_status(user=u)
    check("the header can never be blown out by a long name",
          len(s["season"]["name"]) <= bp.SEASON_NAME_MAX + 12, s["season"]["name"])

    try:
        await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name=chr(1) + chr(2)), admin=admin)
        check("a name made only of control characters is refused honestly", False, "no exception")
    except HTTPException as e:
        check("a name made only of control characters is refused honestly",
              e.status_code == 400, str(e.detail))
    s = await bp.bp_status(user=u)
    check("a refused rename changed nothing", ("Z" * bp.SEASON_NAME_MAX) in s["season"]["name"],
          s["season"]["name"])

    try:
        await bp.bp_admin_season_name(bp.AdminSeasonNameIn(season="2026-13", name="x"), admin=admin)
        check("a malformed season is refused", False, "no exception")
    except HTTPException as e:
        check("a malformed season is refused", e.status_code == 400, str(e.detail))

    # A rename aimed at ANOTHER season must not touch the live one.
    other = "2027-03"
    await bp.bp_admin_season_name(bp.AdminSeasonNameIn(season=other, name="Otra"), admin=admin)
    s = await bp.bp_status(user=u)
    check("renaming a different season leaves the live one alone",
          ("Z" * bp.SEASON_NAME_MAX) in s["season"]["name"], s["season"]["name"])
    check("the other season keeps its own name",
          (await bp.season_name(other)) == "S15 · Otra 2027", await bp.season_name(other))

    # A box holding only spaces reads as an empty box, so it restores the
    # built-in name rather than saving a season called " ".
    r = await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name="   " + chr(9)), admin=admin)
    check("a box holding only spaces restores the built-in name", r["name"] == default, r["name"])
    await bp.bp_admin_season_name(bp.AdminSeasonNameIn(season=other, name=""), admin=admin)
    check("every override is gone at the end", (await d.bp_seasons.count_documents({})) == 0)


async def case_season_name_survives_a_broken_read():
    """A rename must never be able to take the page down: an unreadable override
    collection degrades to the built-in name."""
    d = fresh_db()
    await seed_indexes(d)
    u = await mk_user(d, uid="sn_u2", sid=SID)
    admin = await mk_user(d, uid="sn_admin2", sid="8", role="admin")
    await bp.bp_admin_season_name(bp.AdminSeasonNameIn(name="La Gran Caza"), admin=admin)

    class _Boom:
        def find(self, *a, **kw):
            raise RuntimeError("mongo down")

    real = d.bp_seasons
    d._c["bp_seasons"] = _Boom()
    bp._season_name_cache["at"] = None            # force a fresh (failing) read
    bp._season_name_cache["map"] = {}
    s = await bp.bp_status(user=u)
    check("a dead override read still renders the season",
          s["season"]["name"] == bp.season_display_name(bp.current_season_id()),
          s["season"]["name"])
    d._c["bp_seasons"] = real
    bp._season_name_cache["at"] = None
    s = await bp.bp_status(user=u)
    check("the custom name comes back when the read recovers",
          s["season"]["name"].endswith("La Gran Caza " + bp.current_season_id()[:4]),
          s["season"]["name"])


# =============================================================================
# runner
# =============================================================================
SYNC_TESTS = [
    case_row_totals_exact, case_no_halving_anywhere, case_regular_empty_cells,
    case_row_layout_matches_the_brief, case_mutations_per_row_and_buyer,
    case_row_flavors_and_prime, case_no_invalid_species, case_band_levels,
    case_skins_by_row, case_bp_skins_never_drop_from_crates,
    case_xp_curve, case_level_from_xp_boundaries,
    case_tier_source_precedence, case_checkout_plan_prices,
    case_season_code_is_structural, case_season_name_sanitizer, case_season_name_render,
]

ASYNC_TESTS = [
    case_passive_xp, case_quest_xp_by_rarity, case_kill_xp_fail_closed_and_cooldown,
    case_no_purchase_claims_nothing, case_active_patreon_grants_nothing,
    case_regular_buyer_access, case_premium_buyer_access_and_stacking,
    case_claim_basics_and_double_claim, case_legacy_track_names_still_claim,
    case_claim_level_and_empty_and_track_gates, case_dino_claim_choice_validation,
    case_dino_grant_follows_the_row_not_the_tier, case_apex_cells,
    case_vault_full_refusal_does_not_consume, case_claim_all,
    case_status_payload, case_legacy_track_aliases_still_served,
    case_tokens_are_live_only,
    case_token_consume_atomicity, case_live_token_lane, case_vault_targets_and_no_dinos,
    case_gift_idempotent, case_admin_grant_xp, case_checkout_503_without_stripe,
    case_webhook_unsigned_and_bad_signature, case_webhook_grant_replay_and_not_paid,
    case_webhook_refund_revokes, case_payment_status_owner_only,
    case_settle_idempotent_and_absent_player, case_settle_reaches_past_a_wall_of_current_passes,
    case_settle_grants_nothing_without_a_pass, case_settle_regular_row_only_for_a_regular_pass,
    case_claim_refused_after_settle, case_admin_overview_and_settle_button,
    case_auth_gates_are_wired, case_status_matches_the_page_contract,
    case_claim_responses_match_the_page_contract, case_token_and_vault_shapes_match_the_page,
    case_admin_shapes_match_the_page, case_checkout_and_payment_shapes,
    case_season_name_override_end_to_end, case_season_name_survives_a_broken_read,
]


async def run_all():
    for t in SYNC_TESTS:
        print(f"[{t.__name__}]")
        t()
    for t in ASYNC_TESTS:
        print(f"[{t.__name__}]")
        await t()


def test_battle_pass():
    """pytest entry point (there is no pytest-asyncio in this repo)."""
    asyncio.run(run_all())
    assert not failures, f"{len(failures)} check(s) failed: {failures}"


if __name__ == "__main__":
    asyncio.run(run_all())
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        sys.exit(1)
    print(f"ALL OK — {passes[0]} checks passed")
