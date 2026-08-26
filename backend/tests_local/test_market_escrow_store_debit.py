# -*- coding: utf-8 -*-
"""Marketplace vault-escrow journal + store debit guard -- SHIPPED-BYTES gate.

Two defects, both recorded open in the fleet ledgers, both closed 2026-08-07:

  FIX 1 -- "LIN market list DELETES the vault row with no log".
      `_market_create_from_vault` called `vault.delete_owned` (a hard SQL
      DELETE) and wrote NOTHING on success. The only copy of the animal was the
      `vault_payload` snapshot inside the Mongo listing doc, so the
      REMOVED_SPECIES sweep (`db.market.delete_many`) or any Mongo restore took
      a real dino with no record that the site had ever removed it.
      Closed by a write-ahead fsync'd JSONL journal carrying the FULL row, plus
      a `[MARKETVAULT]` log line on every removal AND every restore.

  FIX 2 -- LIN's plain store checkout used an unguarded `$inc` debit.
      `user` is a REQUEST-TIME SNAPSHOT; the route checked it and then applied
      an unconditional `$inc`. N carts submitted at the same instant all passed
      and all debited (balance negative, N carts for the price of one), and a
      double-submit charged and granted twice.
      Closed by an order-key claim before any money moves + ONE conditional
      find_one_and_update carrying the balance guard for BOTH currencies.

WHAT MAKES THIS A REAL GATE: it does not re-implement the routes. It parses the
SHIPPED server.py, extracts the actual function definitions by AST, and execs
those exact bytes against an in-memory Mongo shim and a fake vault. If the
shipped source changes shape, this suite executes the change.

The Mongo shim models the one property the whole fix rests on: `update_one` and
`find_one_and_update` evaluate filter-and-update ATOMICALLY (no await point
between match and write), while every other await is a real interleaving point.
That is what lets the races below be genuine races.

Run:      py -3.12 tests_local/test_market_escrow_store_debit.py
Mutants:  py -3.12 tests_local/test_market_escrow_store_debit.py --mutants
Exit: 0 all pass / 1 a check failed / 2 the suite could not run.
"""
import argparse
import ast
import asyncio
import json
import os
import sys
import tempfile
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
SERVER_PY = os.path.join(BACKEND, "server.py")

PASS = 0
FAIL = 0
FAILED_NAMES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %s" % name)
    else:
        FAIL += 1
        FAILED_NAMES.append(name)
        print("  FAIL %s %s" % (name, detail))


# ---------------------------------------------------------------- shipped bytes
WANT_FUNCS = (
    "_market_escrow_journal_path", "_market_escrow_append", "_market_escrow_record",
    "_market_create_from_vault", "_give_dino", "_store_order_key", "checkout", "purchase",
)

# The 2026-08-11 pricing wave moved every market number behind an owner-editable
# config layer, so `_market_create_from_vault` now reads `_mcfg()` and prices
# through `_merit()`. That is not optional wiring: the list below is the exact
# TRANSITIVE set of module-level helpers the eight roots above reference,
# computed from the AST of the shipped file rather than guessed, minus the
# identity/id helpers build_ns() already fakes (`now_iso`, `new_id`,
# `_steam_id_or_400`, `_bare_species`, `_user_park_cap`, `add_transaction`,
# `get_current_user`).
#
# They are SLICED, not re-implemented. A hand-written `_merit` stub in this file
# would answer whatever number keeps the escrow tests green, which is how a
# fixture starts certifying itself instead of the product -- and the escrow
# ordering these tests exist for runs THROUGH this code, so faking it would mean
# the write-ahead proof no longer runs against the real preconditions.
WANT_MARKET_FUNCS = (
    "_market_warn_once", "_market_defaults", "_mcfg",
    "_knob_int", "_knob_refuse_int", "_tax_pct",
    "_duration_tiers", "_fmt_hours_es", "_join_es", "_duration_or_400",
    "_priced_mut_count", "_inventory_dino_mutation_keys",
    "_growth_pct_exact", "_growth_pct_display", "_growth_gate_ok",
    "_species_base_table", "_merit",
    "_market_clean_title", "_es_num",
    "_market_listing_type_or_400", "_market_growth_gate_or_409",
    "_market_listing_cap_or_409", "_market_price_or_400", "_market_title_or_400",
    "_market_write_gate",
    # Added 2026-08-11 (same wave, second pass): the idempotency ledger, the
    # stale-price refusal, the per-animal move cooldown, and the auction/withdraw
    # money helpers. Recomputed from the AST rather than guessed -- the roots below
    # reach all of these transitively, and a missing name here surfaces as a
    # NameError from inside the SLICED function, which reads like a product defect
    # and is not one.
    "_client_request_id", "_expected_price_or_409",
    "_market_op_peek", "_market_op_lookup", "_market_op_ref", "_market_op_answer",
    "_market_op_take", "_market_op_claim", "_market_op_done", "_market_op_reversed",
    "_move_cooldown_or_429", "_move_cooldown_secs", "_move_cooldown_state",
    "_move_cooldown_keys", "_dino_fingerprint", "_wait_es",
    "_web_is_admin", "_is_owner", "_park_cap_default",
    "_listing_tax_pct", "_market_verify_view",
    "_withdraw_fee", "_min_next_bid", "_bid_step", "_bid_max",
    # step 8 of the create lane became real when the trade subsystem landed:
    # an animal already promised in a pending offer must be refused a listing.
    "_pending_trade_hold",
)
# SPECIES_BASE_DEFAULT must precede MARKET_DEFAULTS: the latter embeds it AT
# ASSIGNMENT TIME. Everything else resolves at call time.
WANT_CONSTS = (
    "MARKET_ESCROW_JOURNAL_MAX_BYTES", "STORE_ORDER_DEDUPE_SECS",
    "SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
    "MARKET_CFG_CACHE_SECS", "MARKET_WRITE_WINDOW_SECS", "_GROWTH_EPS",
    "_MARKET_WARN_CAP", "_MARKET_WRITE_MAP_CAP",
    # module-level MUTABLE state the sliced functions rebind via `global`
    "_MARKET_WARNED_ONCE", "_market_write_hits",
    "_market_cfg_cache", "_market_cfg_cache_at",
    # Added 2026-08-11 (second pass) with the idempotency ledger, the stale-price
    # refusal and the per-animal move cooldown. Recomputed from the AST: these are
    # the module-level names the SLICED functions load and the namespace does not
    # already fake. A missing one surfaces as a NameError raised from inside a
    # sliced function, which reads exactly like a product defect and is not one.
    "MARKET_REQUEST_ID_MAX", "MARKET_OP_STALE_SECS",
    "MOVE_COOLDOWN_FP_COLS", "MARKET_SALE_FEE_RATE",
    "TRADE_STATUSES_OPEN",
)


def extract_shipped(src_text):
    """Pull the REAL function/constant source out of server.py by AST.

    Decorators are dropped (the route decorators need a live FastAPI router);
    the function body itself is byte-identical to what ships.

    AnnAssign is read as well as Assign: `_MARKET_WARNED_ONCE: set = set()` and
    `_market_write_hits: dict = {}` are annotated, and an extractor that only
    understood bare Assign would silently drop them -- a MISSING name here does
    not fail loudly at extraction, it fails as a NameError deep inside a route.
    """
    tree = ast.parse(src_text)
    lines = src_text.splitlines(True)
    want_funcs = set(WANT_FUNCS) | set(WANT_MARKET_FUNCS)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in want_funcs:
            start = node.lineno - 1          # decorators deliberately excluded
            out[node.name] = "".join(lines[start:node.end_lineno])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_CONSTS:
                    out[t.id] = "".join(lines[node.lineno - 1:node.end_lineno])
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in WANT_CONSTS:
                out[node.target.id] = "".join(lines[node.lineno - 1:node.end_lineno])
    return out


# ------------------------------------------------------------------ mongo shim
def _match(doc, flt):
    for k, cond in flt.items():
        if k == "$or":
            if not any(_match(doc, c) for c in cond):
                return False
            continue
        have = doc.get(k, None)
        if isinstance(cond, dict) and any(str(x).startswith("$") for x in cond):
            for op, val in cond.items():
                if op == "$gte":
                    if have is None or have < val:
                        return False
                elif op == "$lt":
                    if have is None or not (have < val):
                        return False
                elif op == "$gt":
                    if have is None or not (have > val):
                        return False
                elif op == "$lte":
                    if have is None or not (have <= val):
                        return False
                elif op == "$ne":
                    if have == val:
                        return False
                elif op == "$in":
                    if have not in val:
                        return False
                elif op == "$exists":
                    if (k in doc) != bool(val):
                        return False
                else:
                    raise AssertionError("shim: unsupported op %s" % op)
        elif have != cond:
            return False
    return True


def _apply_update(doc, upd):
    for op, body in upd.items():
        if op == "$set":
            doc.update(body)
        elif op == "$inc":
            for k, v in body.items():
                doc[k] = doc.get(k, 0) + v
        elif op == "$setOnInsert":
            pass
        else:
            raise AssertionError("shim: unsupported update %s" % op)


class _Res(object):
    def __init__(self, n):
        self.modified_count = n
        self.matched_count = n
        self.deleted_count = n


class FakeCol(object):
    """Async collection. Reads/writes yield; match+update never yields."""

    def __init__(self, name, hooks):
        self.name = name
        self.docs = []
        self.hooks = hooks

    async def _tick(self):
        self.hooks.setdefault("seq", [0])
        self.hooks["seq"][0] += 1
        await asyncio.sleep(0)

    async def insert_one(self, doc):
        await self._tick()
        if "_id" in doc:
            if any(d.get("_id") == doc["_id"] for d in self.docs):
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("dup _id %s" % doc["_id"])
        self.docs.append(dict(doc))
        return _Res(1)

    async def find_one(self, flt, proj=None):
        await self._tick()
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt, upd, upsert=False):
        await self._tick()
        for d in self.docs:            # ATOMIC: no await between match and write
            if _match(d, flt):
                _apply_update(d, upd)
                return _Res(1)
        if upsert:
            nd = dict(flt)
            nd.update(upd.get("$setOnInsert", {}))
            _apply_update(nd, {k: v for k, v in upd.items() if k != "$setOnInsert"})
            self.docs.append(nd)
            return _Res(1)
        return _Res(0)

    async def find_one_and_update(self, flt, upd, return_document=None, upsert=False):
        await self._tick()
        for d in self.docs:            # ATOMIC
            if _match(d, flt):
                before = dict(d)
                _apply_update(d, upd)
                after = dict(d)
                try:
                    from pymongo import ReturnDocument
                    want_after = (return_document == ReturnDocument.AFTER)
                except Exception:
                    want_after = False
                return after if want_after else before
        return None

    async def delete_one(self, flt):
        await self._tick()
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return _Res(1)
        return _Res(0)

    async def delete_many(self, flt):
        await self._tick()
        keep = [d for d in self.docs if not _match(d, flt)]
        n = len(self.docs) - len(keep)
        self.docs = keep
        return _Res(n)

    async def count_documents(self, flt):
        await self._tick()
        return len([d for d in self.docs if _match(d, flt)])

    async def create_index(self, *a, **k):
        return "idx"


class FakeDB(object):
    def __init__(self):
        self.hooks = {}
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cols:
            self._cols[name] = FakeCol(name, self.hooks)
        return self._cols[name]


# ------------------------------------------------------------------ fake vault
PARKED_COLS = ["id", "steam_id", "dino_class", "growth", "health", "hunger",
               "is_prime", "mutations", "skin_data", "diet_a", "parked_at"]


class FakeVault(object):
    def __init__(self, journal_path_getter):
        self.rows = {}
        self.delete_calls = []
        self.saved = []
        self.raise_on_delete = None
        self.delete_returns = None
        self.journal_path_getter = journal_path_getter
        self.journal_size_at_delete = None

    def add_row(self, dino_id, sid, **kw):
        row = {c: None for c in PARKED_COLS}
        row.update({"id": dino_id, "steam_id": sid, "dino_class": "BP_Rex_C",
                    "growth": 0.87, "health": 900, "hunger": 400, "is_prime": 1,
                    "mutations": "Robust,Keen", "skin_data": "AAAABBBBCCCC" * 12,
                    "diet_a": "Deer", "parked_at": "2026-08-07T00:00:00Z"})
        row.update(kw)
        self.rows[int(dino_id)] = row
        return row

    def get_parked_by_id(self, dino_id):
        r = self.rows.get(int(dino_id))
        return dict(r) if r else None

    def resolve_stale_redeem_pending(self, row):
        return row

    def clean_custom_name(self, n):
        return n or ""

    def delete_owned(self, dino_id, steam_id):
        # ORDERING ORACLE: how big was the journal at the moment of the delete?
        p = self.journal_path_getter()
        self.journal_size_at_delete = os.path.getsize(p) if os.path.exists(p) else 0
        self.delete_calls.append((int(dino_id), str(steam_id)))
        if self.raise_on_delete:
            raise self.raise_on_delete
        if self.delete_returns is not None:
            return self.delete_returns
        r = self.rows.get(int(dino_id))
        if not r or str(r["steam_id"]) != str(steam_id):
            return 0
        del self.rows[int(dino_id)]
        return 1

    def resolve_discord_id(self, sid):
        return "discord-%s" % sid

    def save_parked(self, sid, discord_id, payload, cap):
        if len(self.saved) >= 999:
            return None
        if getattr(self, "save_returns_none", False):
            return None
        new_id_ = 9000 + len(self.saved)
        self.saved.append({"id": new_id_, "steam_id": sid, "payload": dict(payload)})
        return new_id_

    def count_parked(self, sid):
        return 0

    def _mutation_count(self, m):
        return 0

    def _parked_skin(self, s):
        return None


# ------------------------------------------------------------------ namespace
class HTTPExc(Exception):
    def __init__(self, status_code=400, detail=""):
        Exception.__init__(self, "%s %s" % (status_code, detail))
        self.status_code = status_code
        self.detail = detail


class _UnreachableCatalog(dict):
    """The store mutation catalog, which this gate has no honest copy of.

    `MUTATIONS_BY_KEY = {m["key"]: m for m in _build_store_mutations()}` and
    pulling that in would drag half the store into an escrow gate. It is only
    consulted by `_inventory_dino_mutation_keys`, i.e. the INVENTORY listing
    lane, and this gate's root is the VAULT lane. An empty dict here would be
    the dangerous shape: every key would read as unknown and the price would
    quietly build from zero mutations."""

    def __contains__(self, key):
        raise AssertionError(
            "MUTATIONS_BY_KEY was consulted: the inventory listing lane is now "
            "reachable from this gate's roots. Wire the real catalog into "
            "build_ns() -- do not let it read as empty.")

    def get(self, *a, **k):
        raise AssertionError("MUTATIONS_BY_KEY was consulted (see build_ns).")


def build_ns(shipped, tmpdir, mutate=None):
    """Exec the shipped function sources into a namespace wired to fakes."""
    import logging
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    class _GI(object):
        pass
    gi = _GI()
    gi.DATA_DIR = tmpdir

    db = FakeDB()
    ns = {
        "os": os, "json": json, "time": time, "asyncio": asyncio,
        # math/re/unicodedata arrived with the pricing wave: _growth_pct_display
        # floors through math, _market_clean_title collapses whitespace with re
        # and reads unicode categories.
        "math": __import__("math"), "re": __import__("re"),
        "unicodedata": __import__("unicodedata"),
        "hashlib": __import__("hashlib"), "logging": logging,
        "logger": logging.getLogger("lin.test"),
        "HTTPException": HTTPExc, "ReturnDocument": ReturnDocument,
        "DuplicateKeyError": DuplicateKeyError,
        "game_ipc": gi, "db": db,
        # Reached ONLY through the inventory lane, which is not one of this
        # gate's roots. Stubbing it as {} would make every inventory mutation
        # key "unknown" and quietly price at zero mutations -- a wrong number
        # that passes. This raises instead, so the day a slice does reach it the
        # gate says so out loud rather than certifying a fake catalog.
        "MUTATIONS_BY_KEY": _UnreachableCatalog(),
        "now_iso": lambda: "2026-08-07T12:00:00+00:00",
        "new_id": lambda: "id-%d" % int(time.time() * 1e6 % 1e9),
        "SKIN_USES_PER_GRANT": 5,
        "MARKET_SALE_FEE_RATE": 0.1,
        "_user_park_cap": lambda u: 10,
        "_steam_id_or_400": lambda u: str(u.get("steam_id") or ""),
        "_bare_species": lambda c: "Rex",
        "_duration_fee_rate": lambda h, t: (24, 0.1),
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "timedelta": __import__("datetime").timedelta,
        # route signatures are evaluated at def time
        "Depends": lambda f: None, "get_current_user": None,
        "PurchaseInput": object, "CheckoutInput": object,
    }
    vault = FakeVault(lambda: os.path.join(gi.DATA_DIR, "market_vault_escrow.jsonl"))
    ns["vault"] = vault

    class _GT(object):
        EVRIMA_SPECIES = {"Rex": "tyrannosaurus"}
    ns["game_telemetry"] = _GT()

    class _SD(object):
        DINO_IMG = {"tyrannosaurus": "rex.png"}
    ns["seed_data"] = _SD()

    # `_suggested_price_info` used to be stubbed here. It is GONE from server.py
    # (the 2026-08-11 wave replaced it with `_merit` + display-only
    # `_market_stats_info`), and a stub for a function nothing calls is a lie
    # about what this namespace models.

    async def _add_tx(uid, cur, amt, ttype, desc):
        await db.transactions.insert_one({"user_id": uid, "currency": cur,
                                          "amount": amt, "type": ttype})
    ns["add_transaction"] = _add_tx

    order = ["MARKET_ESCROW_JOURNAL_MAX_BYTES", "STORE_ORDER_DEDUPE_SECS",
             # --- the pricing/config layer, in assignment-safe order ---
             "SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
             "MARKET_CFG_CACHE_SECS", "MARKET_WRITE_WINDOW_SECS", "_GROWTH_EPS",
             "_MARKET_WARN_CAP", "_MARKET_WRITE_MAP_CAP", "_MARKET_WARNED_ONCE",
             "_market_write_hits", "_market_cfg_cache", "_market_cfg_cache_at",
             # second pass 2026-08-11: idempotency ledger + stale-price refusal +
             # per-animal move cooldown. Listing a name in WANT_CONSTS only makes
             # it EXTRACTABLE; it also has to be exec'd here or it is simply absent.
             "MARKET_REQUEST_ID_MAX", "MARKET_OP_STALE_SECS",
             "MOVE_COOLDOWN_FP_COLS", "MARKET_SALE_FEE_RATE",
             "TRADE_STATUSES_OPEN",
             ] + list(WANT_MARKET_FUNCS) + [
             "_market_escrow_journal_path", "_market_escrow_append",
             "_market_escrow_record", "_give_dino", "_market_create_from_vault",
             "_store_order_key", "checkout", "purchase"]
    for nm in order:
        src = shipped[nm]
        if mutate:
            src = mutate(nm, src)
        exec(compile(src, "<shipped:%s>" % nm, "exec"), ns)
    ns["__db"] = db
    ns["__vault"] = vault
    ns["__gi"] = gi
    return ns


class Obj(object):
    """Stand-in for a pydantic input model.

    It carries the SAME DEFAULTS as the real model rather than a blanket
    ``__getattr__`` that answers None for anything asked of it: a bag that
    invents an attribute on demand cannot tell a field the route legitimately
    reads from a field name the route got WRONG, and the second one has to stay
    a visible AttributeError. New optional fields on the real model are added
    here by name, deliberately.
    """

    #: mirrors MarketListInput's optional fields and their defaults
    _DEFAULTS = {"inv_id": None, "type": "sale", "price": None, "duration_hours": 24,
                 "title": None, "source": None, "dino_id": None,
                 "client_request_id": None, "expected_price": None}

    def __init__(self, **kw):
        self.__dict__.update(self._DEFAULTS)
        self.__dict__.update(kw)


def journal_lines(tmpdir):
    p = os.path.join(tmpdir, "market_vault_escrow.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


# THE SELLER'S OWN NUMBER for every vault-lane fixture below.
#
# These fixtures used to pass price=1, which the pre-wave lane accepted because
# the SERVER priced the listing and threw the client's number away. The
# 2026-08-11 wave hands pricing back to the seller inside a per-animal rail, so
# 1 is now a 400 (`abs_min_price` is 10,000) and every escrow test would die on
# the price check before ever reaching the journal it exists to prove.
#
# Derivation against THIS file's fakes, so the number is not a magic constant:
#   _bare_species (faked) -> "Rex" -> EVRIMA_SPECIES (faked) -> slug
#   "tyrannosaurus", which is NOT one of the 22 rows in SPECIES_BASE_DEFAULT,
#   so `_merit` takes the loud fallback base of 400,000. FakeVault
#   `_mutation_count` answers 0, so priced_mutations = 0 and suggested =
#   400,000. Rails: max(10,000, 400,000*50//100) = 200,000 ..
#   min(25,000,000, 400,000*300//100) = 1,200,000.
# 500,000 sits inside that band with room either side, so a knob nudge does not
# silently re-red the whole escrow battery -- and f1.price below asserts the
# band the SERVER actually computed, so if it ever moves out, the failure names
# the real reason instead of surfacing as "the journal is empty".
LEGAL_PRICE = 500_000


async def seed_user(db, uid="u1", sid="76561198000000001", coins=100000, vip=0):
    doc = {"id": uid, "steam_id": sid, "persona_name": "Tester",
           "coins": coins, "vip_coins": vip}
    await db.users.insert_one(doc)
    return doc


# ====================================================================== FIX 1
async def t_fix1(shipped):
    print("\n-- FIX 1: marketplace vault escrow journal --")

    # 1/2/4: happy path -- write-ahead ordering, full payload, both events
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        row = vault.add_row(4242, u["steam_id"])
        data = Obj(dino_id=4242, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        res = await ns["_market_create_from_vault"](data, u)
        recs = journal_lines(td)
        kinds = [r["event"] for r in recs]

        check("f1.write-ahead: journal non-empty BEFORE delete_owned ran",
              vault.journal_size_at_delete is not None and vault.journal_size_at_delete > 0,
              "size_at_delete=%s" % vault.journal_size_at_delete)
        check("f1.events: list_escrow then list_removed",
              kinds == ["list_escrow", "list_removed"], str(kinds))
        esc = recs[0] if recs else {}
        pay = esc.get("vault_payload") or {}
        check("f1.payload: FULL vault row captured",
              esc.get("vault_payload") is not None
              and all(c in pay for c in PARKED_COLS),
              str(sorted(pay.keys()))[:200])
        check("f1.payload: values are the row's own, untransformed",
              pay.get("growth") == 0.87
              and pay.get("skin_data") == row["skin_data"]
              and pay.get("is_prime") == 1)
        check("f1.identity: listing/dino/steam/user all recorded",
              esc.get("listing_id") == res["id"] and esc.get("dino_id") == "4242"
              and esc.get("steam_id") == u["steam_id"] and esc.get("user_id") == "u1")
        check("f1.vault row really removed", 4242 not in vault.rows)
        check("f1.route still returns its contract",
              res.get("success") is True and "id" in res and "price" in res)
        # NEW (2026-08-11 wave): the fixture price is not a magic number -- it is
        # asserted against the rails the SERVER computed for this animal, and the
        # seller's own number is what gets escrowed. Under the retired model the
        # server overwrote it, so this check could not have existed.
        listed = await db.market.find_one({"id": res["id"]})
        check("f1.price: the seller's own number is inside the server's rails "
              "and is what the listing + journal carry",
              res["price"] == LEGAL_PRICE
              and res["price_min"] <= LEGAL_PRICE <= res["price_max"]
              and listed["price"] == LEGAL_PRICE
              and esc.get("price") == LEGAL_PRICE,
              "price=%s rails=%s..%s listed=%s journal=%s" % (
                  res.get("price"), res.get("price_min"), res.get("price_max"),
                  (listed or {}).get("price"), esc.get("price")))

    # 3: THE DANGEROUS DIRECTION -- journal fails => nothing is deleted
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        vault.add_row(77, u["steam_id"])
        ns["__gi"].DATA_DIR = os.path.join(td, "nope") + "\x00bad"   # unwritable
        data = Obj(dino_id=77, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        raised = None
        try:
            await ns["_market_create_from_vault"](data, u)
        except HTTPExc as e:
            raised = e
        check("f1.journal-fail: listing REFUSED (503)",
              raised is not None and raised.status_code == 503,
              "raised=%s" % raised)
        check("f1.journal-fail: vault row NOT deleted (no unjournaled removal)",
              77 in vault.rows and vault.delete_calls == [],
              "delete_calls=%s" % vault.delete_calls)
        check("f1.journal-fail: orphan listing doc cleaned up",
              len(db.market.docs) == 0, str(db.market.docs))

    # 5: delete_owned returns 0 -> list_remove_noop, listing dropped, 409
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        vault.add_row(88, u["steam_id"])
        vault.delete_returns = 0
        data = Obj(dino_id=88, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        raised = None
        try:
            await ns["_market_create_from_vault"](data, u)
        except HTTPExc as e:
            raised = e
        kinds = [r["event"] for r in journal_lines(td)]
        check("f1.noop: 409 + list_remove_noop recorded",
              raised is not None and raised.status_code == 409
              and kinds == ["list_escrow", "list_remove_noop"], "%s %s" % (raised, kinds))
        check("f1.noop: listing doc removed (never both parked AND for sale)",
              len(db.market.docs) == 0)

    # 6: delete_owned raises -> list_remove_raised
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        vault.add_row(99, u["steam_id"])
        vault.raise_on_delete = RuntimeError("database is locked")
        data = Obj(dino_id=99, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        raised = None
        try:
            await ns["_market_create_from_vault"](data, u)
        except HTTPExc as e:
            raised = e
        recs = journal_lines(td)
        kinds = [r["event"] for r in recs]
        check("f1.raise: 409 + list_remove_raised recorded with the error",
              raised is not None and raised.status_code == 409
              and kinds == ["list_escrow", "list_remove_raised"]
              and "locked" in str(recs[-1].get("error", "")), "%s %s" % (raised, kinds))

    # 7: restore closes the ledger
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        vault.add_row(555, u["steam_id"])
        data = Obj(dino_id=555, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        res = await ns["_market_create_from_vault"](data, u)
        listing = await db.market.find_one({"id": res["id"]})
        ok = await ns["_give_dino"]("u1", listing)
        recs = journal_lines(td)
        kinds = [r["event"] for r in recs]
        check("f1.restore: delivery journals a `restore` line",
              ok is True and kinds == ["list_escrow", "list_removed", "restore"], str(kinds))
        check("f1.restore: names the recipient and the new row",
              recs[-1].get("user_id") == "u1" and recs[-1].get("new_row_id") is not None)
        removals = len([k for k in kinds if k == "list_removed"])
        restores = len([k for k in kinds if k == "restore"])
        check("f1.ledger closes: every removal matched by a restore",
              removals == restores == 1, "rm=%s re=%s" % (removals, restores))

    # 7b: failed restore is recorded, never silent
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        vault.add_row(556, u["steam_id"])
        data = Obj(dino_id=556, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        res = await ns["_market_create_from_vault"](data, u)
        listing = await db.market.find_one({"id": res["id"]})
        vault.save_returns_none = True
        ok = await ns["_give_dino"]("u1", listing)
        kinds = [r["event"] for r in journal_lines(td)]
        check("f1.restore-fail: recorded as restore_failed, not silence",
              ok is False and kinds[-1] == "restore_failed", str(kinds))

    # 8: THE HEADLINE -- reconstruct from the JOURNAL ALONE after the market
    #    doc is swept away (REMOVED_SPECIES delete_many), which is exactly how
    #    the old code lost dinos with no trace.
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        db, vault = ns["__db"], ns["__vault"]
        u = await seed_user(db)
        original = dict(vault.add_row(31337, u["steam_id"]))
        data = Obj(dino_id=31337, type="sale", duration_hours=24, title="", price=LEGAL_PRICE, source="vault")
        await ns["_market_create_from_vault"](data, u)
        await db.market.delete_many({})          # the sweep that used to be fatal
        check("f1.sweep: Mongo escrow is gone (defect precondition reproduced)",
              len(db.market.docs) == 0 and 31337 not in vault.rows)
        recs = [r for r in journal_lines(td) if r["event"] == "list_escrow"]
        payload = recs[0]["vault_payload"] if recs else None
        check("f1.RECONSTRUCT: full payload still recoverable from disk alone",
              payload is not None and all(payload.get(c) == original.get(c)
                                          for c in PARKED_COLS),
              "payload=%s" % (str(payload)[:160]))
        if payload:
            back = vault.save_parked(u["steam_id"], "d", payload, 10)
            check("f1.RECONSTRUCT: dino can be re-parked from that record",
                  back is not None and vault.saved[-1]["payload"]["skin_data"] == original["skin_data"])

    # 9: bounded -- rotation caps the journal
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        ns["MARKET_ESCROW_JOURNAL_MAX_BYTES"] = 2048
        p = os.path.join(td, "market_vault_escrow.jsonl")
        for i in range(200):
            ns["_market_escrow_append"]({"event": "x", "i": i, "pad": "y" * 100})
        check("f1.bounded: live journal stays under the cap + one line",
              os.path.getsize(p) < 2048 + 512, "size=%s" % os.path.getsize(p))
        check("f1.bounded: exactly one rotated generation kept",
              os.path.exists(p + ".1") and not os.path.exists(p + ".2"))

    # first-run / missing dir
    with tempfile.TemporaryDirectory() as td:
        ns = build_ns(shipped, td)
        ns["__gi"].DATA_DIR = os.path.join(td, "brand", "new", "deep")
        ok = ns["_market_escrow_append"]({"event": "first"})
        check("f1.first-run: creates its directory and writes", ok is True)


# ====================================================================== FIX 2
async def t_fix2(shipped):
    print("\n-- FIX 2: store checkout conditional + idempotent debit --")

    async def bed(coins=1000, vip=0, price=600, cur="normal", qty=1, tmp=None):
        ns = build_ns(shipped, tmp)
        db = ns["__db"]
        await seed_user(db, coins=coins, vip=vip)
        await db.store_items.insert_one({"id": "it1", "name": "Rex Slot", "price": price,
                                         "currency": cur, "category": "Dinosaurs",
                                         "rarity": "Rare", "image": "x.png"})
        await db.store_items.insert_one({"id": "it2", "name": "Amber Skin", "price": 300,
                                         "currency": "vip", "category": "Skins",
                                         "rarity": "Epic", "image": "y.png"})
        # A DIFFERENT item at the SAME price: lets two carts have different
        # order keys (so the idempotency wall does not apply) while each one
        # still passes the snapshot check on its own.
        await db.store_items.insert_one({"id": "it3", "name": "Cera Slot", "price": price,
                                         "currency": cur, "category": "Dinosaurs",
                                         "rarity": "Rare", "image": "z.png"})
        return ns, db

    with tempfile.TemporaryDirectory() as td:
        # 11: concurrent identical carts, funds for ONE -> exactly one debit
        ns, db = await bed(coins=1000, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1)])
        outs = await asyncio.gather(ns["checkout"](data, user), ns["checkout"](data, user),
                                    return_exceptions=True)
        after = await db.users.find_one({"id": "u1"})
        oks = [o for o in outs if isinstance(o, dict)]
        check("f2.race: balance never negative", after["coins"] >= 0, "coins=%s" % after["coins"])
        check("f2.race: exactly ONE debit of 600", after["coins"] == 400,
              "coins=%s outs=%s" % (after["coins"], outs))
        check("f2.race: purchases recorded once", len(db.purchases.docs) == 1,
              str(len(db.purchases.docs)))
        check("f2.race: both callers still got the route's shape", len(oks) == 2)

    with tempfile.TemporaryDirectory() as td:
        # 12: sequential double-submit inside the window -> one debit, replay echo
        ns, db = await bed(coins=5000, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1)])
        r1 = await ns["checkout"](data, user)
        r2 = await ns["checkout"](data, user)
        after = await db.users.find_one({"id": "u1"})
        check("f2.replay: charged exactly once", after["coins"] == 4400, "coins=%s" % after["coins"])
        check("f2.replay: items granted once", len(db.purchases.docs) == 1)
        check("f2.replay: second call echoes the recorded purchase",
              r2["purchased"] == r1["purchased"] and r2["success"] is True, str(r2))
        check("f2.replay: contract keys unchanged",
              set(r2.keys()) == {"success", "purchased", "total", "balance"}
              and set(r2["balance"].keys()) == {"coins", "vip_coins"}, str(list(r2.keys())))

    with tempfile.TemporaryDirectory() as td:
        # 13: the SAME cart after the window is a real second purchase
        ns, db = await bed(coins=5000, price=600, tmp=td)
        ns["STORE_ORDER_DEDUPE_SECS"] = 0.0
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1)])
        await ns["checkout"](data, user)
        await asyncio.sleep(0.02)
        user = await db.users.find_one({"id": "u1"})
        await ns["checkout"](data, user)
        after = await db.users.find_one({"id": "u1"})
        check("f2.window: a deliberate repeat still charges again",
              after["coins"] == 3800, "coins=%s" % after["coins"])

    with tempfile.TemporaryDirectory() as td:
        # 14: insufficient -> claim released -> retry after topping up works
        ns, db = await bed(coins=100, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1)])
        raised = None
        try:
            await ns["checkout"](data, user)
        except HTTPExc as e:
            raised = e
        check("f2.short: refused 400, nothing debited",
              raised is not None and raised.status_code == 400
              and (await db.users.find_one({"id": "u1"}))["coins"] == 100, str(raised))
        await db.users.update_one({"id": "u1"}, {"$set": {"coins": 5000}})
        user = await db.users.find_one({"id": "u1"})
        r = await ns["checkout"](data, user)
        after = await db.users.find_one({"id": "u1"})
        check("f2.short: retry after topping up is NOT mistaken for a replay",
              r["purchased"] == ["Rex Slot"] and after["coins"] == 4400,
              "coins=%s r=%s" % (after["coins"], r))

    with tempfile.TemporaryDirectory() as td:
        # 15: mixed cart, vip short -> NOTHING moves (no partial debit)
        ns, db = await bed(coins=5000, vip=10, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1), Obj(item_id="it2", quantity=1)])
        raised = None
        try:
            await ns["checkout"](data, user)
        except HTTPExc as e:
            raised = e
        after = await db.users.find_one({"id": "u1"})
        check("f2.atomic: mixed cart with one currency short is refused",
              raised is not None and raised.status_code == 400, str(raised))
        check("f2.atomic: NO partial debit -- coins untouched",
              after["coins"] == 5000 and after["vip_coins"] == 10,
              "coins=%s vip=%s" % (after["coins"], after["vip_coins"]))

    with tempfile.TemporaryDirectory() as td:
        # 15b: THE EXPLOIT SHAPE, and the only leg that isolates the BALANCE
        # GUARD from the idempotency wall. Two DIFFERENT carts (different order
        # keys, so dedupe never fires) each cost 600 against a 1000 balance:
        # each passes the snapshot check on its own, and together they overdraw.
        # Unguarded, both `$inc` land and the balance ends at -200.
        ns, db = await bed(coins=1000, price=600, tmp=td)
        stale = await db.users.find_one({"id": "u1"})
        d1 = Obj(items=[Obj(item_id="it1", quantity=1)])
        d2 = Obj(items=[Obj(item_id="it3", quantity=1)])
        outs = await asyncio.gather(ns["checkout"](d1, stale), ns["checkout"](d2, stale),
                                    return_exceptions=True)
        after = await db.users.find_one({"id": "u1"})
        oks = [o for o in outs if isinstance(o, dict)]
        check("f2.GUARD: two different carts off one stale read cannot overdraw",
              after["coins"] == 400, "coins=%s outs=%s" % (after["coins"], outs))
        check("f2.GUARD: balance never negative", after["coins"] >= 0,
              "coins=%s" % after["coins"])
        check("f2.GUARD: exactly one of the two carts was sold",
              len(oks) == 1 and len(db.purchases.docs) == 1,
              "oks=%s purchases=%s" % (len(oks), len(db.purchases.docs)))

    with tempfile.TemporaryDirectory() as td:
        # 16: a currency with a ZERO total must contribute no filter key.
        # Why it matters: `{"$gte": 0}` does NOT match a document that lacks the
        # field, so an unconditional guard on both currencies would refuse every
        # normal-only cart for any account whose vip_coins was never written.
        check("f2.zero-total: {$gte:0} would NOT match a doc missing the field",
              _match({"coins": 5}, {"vip_coins": {"$gte": 0}}) is False)
        ns, db = await bed(coins=5000, vip=0, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(items=[Obj(item_id="it1", quantity=1)])
        r = await ns["checkout"](data, user)
        check("f2.zero-total: normal-only cart succeeds with vip_coins at 0",
              r["success"] is True and (await db.users.find_one({"id": "u1"}))["coins"] == 4400)

    with tempfile.TemporaryDirectory() as td:
        # empty cart + unknown item: refused BEFORE any order doc exists
        ns, db = await bed(tmp=td)
        raised = None
        try:
            await ns["checkout"](Obj(items=[]), await db.users.find_one({"id": "u1"}))
        except HTTPExc as e:
            raised = e
        check("f2.empty cart refused", raised is not None and raised.status_code == 400)
        raised = None
        try:
            await ns["checkout"](Obj(items=[Obj(item_id="nope", quantity=1)]),
                                 await db.users.find_one({"id": "u1"}))
        except HTTPExc as e:
            raised = e
        check("f2.unknown item 404, no order doc created",
              raised is not None and raised.status_code == 404
              and len(db.store_orders.docs) == 0, str(raised))

    with tempfile.TemporaryDirectory() as td:
        # key stability: item order in the request must not change the key
        ns, db = await bed(tmp=td)
        a = ns["_store_order_key"]("u1", [({"id": "x"}, 1), ({"id": "y"}, 2)])
        b = ns["_store_order_key"]("u1", [({"id": "y"}, 2), ({"id": "x"}, 1)])
        c = ns["_store_order_key"]("u2", [({"id": "x"}, 1), ({"id": "y"}, 2)])
        d = ns["_store_order_key"]("u1", [({"id": "x"}, 1), ({"id": "y"}, 3)])
        check("f2.key: order-independent", a == b)
        check("f2.key: per-user", a != c)
        check("f2.key: quantity-sensitive", a != d)

    with tempfile.TemporaryDirectory() as td:
        # 17: /store/purchase -- same defect, same guard
        ns, db = await bed(coins=1000, price=600, tmp=td)
        user = await db.users.find_one({"id": "u1"})
        data = Obj(item_id="it1")
        outs = await asyncio.gather(ns["purchase"](data, user), ns["purchase"](data, user),
                                    return_exceptions=True)
        after = await db.users.find_one({"id": "u1"})
        check("f2.purchase: concurrent double-buy cannot overdraw",
              after["coins"] == 400, "coins=%s outs=%s" % (after["coins"], outs))
        check("f2.purchase: exactly one succeeded",
              len([o for o in outs if isinstance(o, dict)]) == 1, str(outs))


# ===================================================================== mutants
# Each mutant restores the PRE-FIX shape (or removes one guard) in an IN-MEMORY
# copy of the shipped source -- disk is never touched, so there is no
# checkout-restore trap. A mutant that leaves the battery green is a leg that
# proves nothing.
MUTANTS = {
    "M0-debit-unguarded (the shipped defect)": (
        "checkout",
        ('        charged = await db.users.find_one_and_update(guard, {"$inc": inc})',
         '        charged = await db.users.find_one_and_update({"id": user["id"]}, {"$inc": inc})'),
    ),
    "M1-idempotency-removed": (
        "checkout",
        ("    if not claimed:", "    if False:"),
    ),
    "M2-journal-after-delete": (
        "_market_create_from_vault",
        ('    if not await _market_escrow_record("list_escrow", listing["id"], sid, data.dino_id,',
         '    if False and await _market_escrow_record("list_escrow", listing["id"], sid, data.dino_id,'),
    ),
    "M3-journal-failure-ignored": (
        "_market_escrow_append",
        ("        return False", "        return True"),
    ),
    "M4-purchase-unguarded (the shipped defect)": (
        "purchase",
        ('        paid = await db.users.update_one({"id": user["id"], bal_field: {"$gte": price}},',
         '        paid = await db.users.update_one({"id": user["id"]},'),
    ),
    "M5-restore-not-journalled": (
        "_give_dino",
        ('            "restore" if new_row_id is not None else "restore_failed",',
         '            "quiet" if new_row_id is not None else "quiet",'),
    ),
}


async def run_all(shipped, label=""):
    global PASS, FAIL, FAILED_NAMES
    PASS, FAIL, FAILED_NAMES = 0, 0, []
    await t_fix1(shipped)
    await t_fix2(shipped)
    print("\n%s%d passed, %d failed" % (label, PASS, FAIL))
    return PASS, FAIL, list(FAILED_NAMES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    with open(SERVER_PY, "r", encoding="utf-8") as fh:
        src = fh.read()
    shipped = extract_shipped(src)
    missing = [f for f in WANT_FUNCS + WANT_MARKET_FUNCS + WANT_CONSTS if f not in shipped]
    if missing:
        print("CANNOT RUN: not found in server.py: %s" % missing)
        return 2
    print("shipped bytes under test: %s" % ", ".join(sorted(shipped)))

    p, f, _ = asyncio.run(run_all(shipped))
    if not args.mutants:
        return 0 if f == 0 else 1
    if f:
        print("\nbaseline is RED -- not running mutants")
        return 1

    print("\n=== MUTANTS (each must turn the battery RED) ===")
    survivors = []
    for name, (fn, (old, new)) in MUTANTS.items():
        if old not in shipped[fn]:
            print("\n### %s -- ANCHOR NOT FOUND in %s (mutant is stale)" % (name, fn))
            survivors.append(name + " [stale anchor]")
            continue
        mutated = dict(shipped)
        mutated[fn] = shipped[fn].replace(old, new, 1)

        def _m(nm, s, _t=fn, _v=mutated):
            return _v[nm] if nm == _t else s
        print("\n### %s" % name)
        try:
            mp, mf, names = asyncio.run(run_all(mutated, label="mutant: "))
        except Exception as exc:
            mp, mf, names = 0, 1, ["suite raised: %s" % exc]
        if mf == 0:
            survivors.append(name)
            print("  !! SURVIVED -- no leg caught it")
        else:
            print("  killed by: %s" % ", ".join(names[:4]))

    print("\n=== mutant summary ===")
    if survivors:
        print("SURVIVORS (battery is too weak): %s" % survivors)
        return 1
    print("all %d mutants killed" % len(MUTANTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
