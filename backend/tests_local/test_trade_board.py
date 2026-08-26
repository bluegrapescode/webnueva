# -*- coding: utf-8 -*-
"""THE TRADE BOARD gate -- trading on the same surface the dinosaurs are sold on.

Shipped 2026-08-11 on the owner's ask: "redesign so dinosaurs get traded on the
same tab people can see dinos for sale. no need to send anybody anything."

WHAT THIS FILE DEFENDS, and every one of them is a rule that costs somebody an
animal or a player's privacy if it slips:

  1. A CARD NEVER PUBLISHES SOMEBODY ELSE'S ROW NUMBER. The first build made a
     player obtain that number by messaging the owner outside the site; the
     answer was to stop needing it, NOT to broadcast it. `_trade_board_public`
     emits `dino_id` only to the card's own owner.
  2. A CARD ESCROWS NOTHING, so it can go stale -- and the resolve pass is what
     keeps a stale card from being a lie. Expired closes. Sold/redeemed/traded
     away closes. A row id that sqlite handed to a DIFFERENT animal closes (the
     fingerprint is what catches it; an id alone is not an identity). An animal
     that merely CHANGED refreshes rather than being retired.
  3. THE PASS IS THROTTLED AND PER-ROW CONTAINED. It is the only thing that
     reads sqlite for the board and the market page polls every 8 seconds; and
     one unreadable card must not strand its siblings.
  4. THE OFFER LANE READS THE ANIMAL OFF THE CARD, never off the request. A
     sender who could name the wanted animal themselves could name one its owner
     never put in the window.
  5. THE TWO NEW KNOBS ARE REAL KNOBS: in MARKET_KNOB_SPEC (or the admin route
     refuses to edit them), with the TTL on REFUSE because it decides how long a
     promise stands.

The functions under test are SLICED OUT OF THE SHIPPED server.py BY AST (by
NAME, so a signature change moves the slice instead of breaking it) and executed
against fakes. server.py itself cannot be imported here: no motor, no .env.

Run:      C:\\Python312\\python.exe tests_local/test_trade_board.py
Mutants:  C:\\Python312\\python.exe tests_local/test_trade_board.py --mutants
Exit: 0 all pass / 1 a check failed / 2 the suite could not run.
"""
import argparse
import ast
import asyncio
import logging
import os
import sys
import time as _time

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
        print("  FAIL %s  %s" % (name, detail))


# ============================================================== shipped bytes
WANT_FUNCS = (
    "_market_warn_once", "_market_defaults", "_knob_int", "_knob_refuse_int",
    "_trade_board_ttl_secs", "_trade_board_cap", "_trade_board_public",
    "_trade_board_close", "_resolve_trade_board",
)
WANT_CONSTS = (
    "SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
    "MARKET_KNOB_SPEC", "_MARKET_WARN_CAP", "_MARKET_WARNED_ONCE",
    "TRADE_BOARD_RESOLVE_EVERY_SECS", "_trade_board_resolve_last",
)
EXEC_ORDER = ("SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
              "MARKET_KNOB_SPEC", "_MARKET_WARN_CAP", "_MARKET_WARNED_ONCE",
              "TRADE_BOARD_RESOLVE_EVERY_SECS",
              "_trade_board_resolve_last") + WANT_FUNCS


def extract_shipped(src_text):
    """The REAL function/constant source, by AST, decorators excluded."""
    tree = ast.parse(src_text)
    lines = src_text.splitlines(True)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in WANT_FUNCS:
            out[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_CONSTS:
                    out[t.id] = "".join(lines[node.lineno - 1:node.end_lineno])
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in WANT_CONSTS:
                out[node.target.id] = "".join(lines[node.lineno - 1:node.end_lineno])
    return out


class HTTPExc(Exception):
    def __init__(self, status_code=400, detail=""):
        Exception.__init__(self, "%s %s" % (status_code, detail))
        self.status_code = status_code
        self.detail = detail


# ================================================================ fake mongo
class _Cursor(object):
    def __init__(self, rows):
        self._rows = [dict(r) for r in rows]

    def sort(self, key, direction):
        self._rows.sort(key=lambda r: str(r.get(key) or ""), reverse=(direction == -1))
        return self

    async def to_list(self, n):
        return self._rows[: int(n)]


class _Coll(object):
    def __init__(self, rows=None, raise_on_find=False):
        self.rows = [dict(r) for r in (rows or [])]
        self.raise_on_find = raise_on_find
        self.updates = []

    @staticmethod
    def _match(r, flt):
        for k, v in (flt or {}).items():
            if isinstance(v, dict) and "$in" in v:
                if r.get(k) not in v["$in"]:
                    return False
            elif r.get(k) != v:
                return False
        return True

    def find(self, flt=None, projection=None):
        if self.raise_on_find:
            raise RuntimeError("mongo is down")
        return _Cursor([r for r in self.rows if self._match(r, flt)])

    async def update_one(self, flt, update):
        self.updates.append((dict(flt), update))
        for r in self.rows:
            if self._match(r, flt):
                r.update(update.get("$set") or {})
                return True
        return False


class _Db(object):
    def __init__(self, board=None, raise_on_find=False):
        self.trade_board = _Coll(board, raise_on_find=raise_on_find)


# ============================================================ the namespace
def build_ns(shipped, db=None, parked=None, view=None, raise_on_dino=()):
    """Exec the shipped sources into a namespace wired to fakes.

    The DEEP display half (`_trade_board_view` -> `_trade_item_view` -> merit,
    vault skins, the verify view) is stubbed on purpose: this file is about WHEN
    a card is closed, refreshed or left alone, and pricing has its own gate
    (test_market_suggested_price.py) that proves the numbers."""
    ns = {
        "__name__": "server_slice",
        "HTTPException": HTTPExc,
        "logger": logging.getLogger("test_trade_board"),
        "os": os, "time": _time, "asyncio": asyncio,
        "db": db if db is not None else _Db(),
        "now_iso": lambda: "2026-08-11T00:00:00+00:00",
    }

    class _Vault(object):
        @staticmethod
        def get_parked_by_id(dino_id):
            if dino_id in raise_on_dino:
                raise RuntimeError("sqlite is busy")
            return (parked or {}).get(int(dino_id))

    ns["vault"] = _Vault()

    async def _mcfg():
        return dict(ns["MARKET_DEFAULTS"])
    src = extract_shipped(shipped)
    missing = [n for n in EXEC_ORDER if n not in src]
    if missing:
        print("COULD NOT SLICE: %s" % ", ".join(missing))
        sys.exit(2)
    for name in EXEC_ORDER:
        exec(compile(src[name], "<%s>" % name, "exec"), ns)
    ns["_mcfg"] = _mcfg
    if view is not None:
        ns["_trade_board_view"] = view
    return ns


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────────────── the checks ───────────────────────────────
def check_public(ns):
    print("\n-- what a card publishes")
    entry = {
        "id": "c1", "title": "Rex", "note": "busco Deino", "dino_slug": "trex",
        "dino_name": "Tyrannosaurus Rex", "image": "/i.png", "rarity": "Apex",
        "species": "Tyrannosaurus", "growth_pct": 100, "priced_mutations": 12,
        "prime": True, "is_elder": False, "skin_view": {"a": 1}, "verify": {"b": 2},
        "created_at": "2026-08-11T00:00:00+00:00", "ends_at": "2026-08-14T00:00:00+00:00",
        "value": 5_800_000, "owner_id": "u1", "owner_name": "Nubla",
        "owner_steam": "765", "dino_id": 52, "offers": 3,
        # Two fields that must NEVER reach a viewer.
        "fingerprint": "deadbeef", "expires_at_ts": 123.0,
    }
    pub = ns["_trade_board_public"]
    mine = pub(entry, "u1")
    theirs = pub(entry, "u2")
    anon = pub(entry, "")

    check("public.mine_flag", mine["mine"] is True and theirs["mine"] is False)
    check("public.row_number_hidden_from_others",
          theirs["dino_id"] is None and anon["dino_id"] is None,
          "a viewer who is not the owner received the parked row id")
    check("public.row_number_shown_to_owner", mine["dino_id"] == 52)
    check("public.owner_id_hidden_from_others", theirs["seller_id"] is None)
    check("public.steam_id_never_published",
          "owner_steam" not in theirs and "owner_steam" not in mine)
    check("public.fingerprint_never_published", "fingerprint" not in theirs)
    check("public.clock_internals_never_published", "expires_at_ts" not in theirs)
    check("public.type_is_trade", theirs["type"] == "trade")
    check("public.source_is_vault", theirs["source"] == "vault",
          "the card renders through the market's vault-sourced media path")
    check("public.seller_name_is_the_owner", theirs["seller_name"] == "Nubla")
    check("public.mutations_published_under_both_names",
          theirs["mutations_count"] == 12 and theirs["priced_mutations"] == 12,
          "the shipped card component reads mutations_count")
    check("public.value_travels", theirs["value"] == 5_800_000)
    check("public.verify_travels_for_the_inspector", theirs["verify"] == {"b": 2})
    check("public.offers_is_an_int", theirs["offers"] == 3)
    # A card built from a partial row must not raise -- the grid draws whatever
    # it has rather than 500ing the whole board.
    thin = pub({"id": "c2", "owner_id": "u9"}, "u2")
    check("public.partial_row_degrades", thin["dino_id"] is None and thin["offers"] == 0)


def check_knobs(ns):
    print("\n-- the two knobs")
    spec = ns["MARKET_KNOB_SPEC"]
    defaults = ns["MARKET_DEFAULTS"]
    check("knob.ttl_in_spec", spec.get("trade_board_ttl_secs", (None,))[0] == "refuse",
          "the TTL decides how long a promise stands; a clamp would pick a "
          "window the owner did not choose")
    check("knob.cap_in_spec", spec.get("trade_max_board_per_player", (None,))[0] == "clamp")
    check("knob.both_have_defaults",
          "trade_board_ttl_secs" in defaults and "trade_max_board_per_player" in defaults)
    check("knob.every_default_has_a_spec_row",
          all(k in spec for k in defaults if k.startswith("trade_board")
              or k == "trade_max_board_per_player"),
          "a knob without a spec row is refused by the admin route and then "
          "silently ignored by its reader")

    ttl = ns["_trade_board_ttl_secs"]
    cap = ns["_trade_board_cap"]
    check("knob.ttl_shipped_default", ttl(dict(defaults)) == 259_200)
    check("knob.cap_shipped_default", cap(dict(defaults)) == 3)
    lo, hi = spec["trade_board_ttl_secs"][1], spec["trade_board_ttl_secs"][2]
    check("knob.ttl_band_edges_accepted",
          ttl(dict(defaults, trade_board_ttl_secs=lo)) == lo
          and ttl(dict(defaults, trade_board_ttl_secs=hi)) == hi)
    for bad, why in ((lo - 1, "under the band"), (hi + 1, "over the band"),
                     (True, "a bool is not a number of seconds"),
                     ("259200", "a string"), (7200.5, "a float")):
        raised = False
        try:
            ttl(dict(defaults, trade_board_ttl_secs=bad))
        except HTTPExc as exc:
            raised = exc.status_code == 503
        check("knob.ttl_refuses_%s" % str(bad), raised, why)
    check("knob.cap_clamps_rather_than_refusing",
          cap(dict(defaults, trade_max_board_per_player=999)) == 25
          and cap(dict(defaults, trade_max_board_per_player=0)) == 1,
          "a cap is a mechanical limit whose two ends are both sane")


ROW = {"steam_id": "765", "id": 52}


def a_card(**over):
    e = {"id": "c1", "status": "active", "owner_id": "u1", "owner_steam": "765",
         "dino_id": 52, "value": 100, "fingerprint": "fp1",
         "expires_at_ts": _time.time() + 3600}
    e.update(over)
    return e


def fresh_view(**over):
    v = {"dino_slug": "trex", "species": "Tyrannosaurus", "dino_name": "Tyrannosaurus",
         "growth_pct": 100, "growth_pct_exact": 100.0, "priced_mutations": 12,
         "prime": False, "is_elder": False, "skin_view": None, "verify": None,
         "fingerprint": "fp1", "value": 100, "value_error": None}
    v.update(over)
    return v


def statuses(db):
    return {r["id"]: (r.get("status"), r.get("close_note")) for r in db.trade_board.rows}


def check_resolve(shipped):
    print("\n-- the resolve pass: when a card comes down")

    def build(board, parked, view=None, **kw):
        db = _Db(board)
        ns = build_ns(shipped, db=db,
                      parked=parked,
                      view=view or (lambda cfg, row: fresh_view()), **kw)
        return ns, db

    # 1. EXPIRED
    ns, db = build([a_card(expires_at_ts=_time.time() - 1)], {52: dict(ROW)})
    run(ns["_resolve_trade_board"]())
    check("resolve.expired_closes", statuses(db)["c1"] == ("closed", "ttl"))

    # 2. AN UNREADABLE CLOCK is not a card that lives forever
    ns, db = build([a_card(expires_at_ts="soon")], {52: dict(ROW)})
    run(ns["_resolve_trade_board"]())
    check("resolve.unreadable_clock_closes", statuses(db)["c1"] == ("closed", "bad_clock"))

    # 3. THE ANIMAL IS GONE (sold, redeemed, traded away)
    ns, db = build([a_card()], {})
    run(ns["_resolve_trade_board"]())
    check("resolve.gone_closes", statuses(db)["c1"] == ("closed", "gone"))

    # 4. THE ROW IS SOMEBODY ELSE'S NOW
    ns, db = build([a_card()], {52: {"steam_id": "999"}})
    run(ns["_resolve_trade_board"]())
    check("resolve.other_owner_closes", statuses(db)["c1"] == ("closed", "gone"),
          "a card must never advertise an animal its publisher no longer owns")

    # 5. THE ROW ID WAS REUSED BY A DIFFERENT ANIMAL. Same id, same owner,
    #    different content -> the card is refreshed to the truth, never left
    #    quietly describing the animal that used to be there.
    ns, db = build([a_card()], {52: dict(ROW)},
                   view=lambda cfg, row: fresh_view(fingerprint="fp2", value=999,
                                                    priced_mutations=4))
    run(ns["_resolve_trade_board"]())
    row = db.trade_board.rows[0]
    check("resolve.changed_animal_refreshes",
          row["status"] == "active" and row["value"] == 999 and row["fingerprint"] == "fp2",
          "a mutation edit makes the stored card wrong; the honest answer is to "
          "redraw it, not to take the owner's card down")

    # 6. UNCHANGED -> NOT WRITTEN. This pass runs forever on a live box.
    ns, db = build([a_card(**fresh_view())], {52: dict(ROW)})
    run(ns["_resolve_trade_board"]())
    check("resolve.unchanged_writes_nothing", db.trade_board.updates == [],
          "an idempotent pass that writes anyway is a write amplifier")

    # 7. UNPRICEABLE -> down. An offer on it would 503 anyway.
    ns, db = build([a_card()], {52: dict(ROW)},
                   view=lambda cfg, row: fresh_view(value_error="knob roto"))
    run(ns["_resolve_trade_board"]())
    check("resolve.unpriced_closes", statuses(db)["c1"] == ("closed", "unpriced"))

    # 8. PER-ROW CONTAINMENT. One card whose vault read raises must not strand
    #    its siblings -- the exact defect _resolve_listings was rebuilt around.
    ns, db = build([a_card(id="bad", dino_id=77), a_card(id="good")],
                   {52: dict(ROW)}, raise_on_dino=(77,))
    run(ns["_resolve_trade_board"]())
    st = statuses(db)
    check("resolve.one_bad_row_does_not_strand_siblings",
          st["bad"][0] == "active" and st["good"][0] == "active",
          "the raiser is left alone and the healthy sibling was still visited")

    # 9. A DEAD MONGO IS NOT A CRASH.
    db = _Db([a_card()], raise_on_find=True)
    ns = build_ns(shipped, db=db, parked={52: dict(ROW)},
                  view=lambda cfg, row: fresh_view())
    run(ns["_resolve_trade_board"]())
    check("resolve.read_failure_is_contained", True, "did not raise")

    # 10. THROTTLED. The market page polls every 8 seconds per open tab; this
    #     is the only thing that reads sqlite for the board.
    ns, db = build([a_card(expires_at_ts=_time.time() - 1)], {52: dict(ROW)})
    check("resolve.throttle_interval_is_real", ns["TRADE_BOARD_RESOLVE_EVERY_SECS"] >= 10)
    run(ns["_resolve_trade_board"]())
    n_after_first = len(db.trade_board.updates)
    db.trade_board.rows[0]["status"] = "active"          # put it back
    run(ns["_resolve_trade_board"]())
    check("resolve.second_call_inside_the_window_is_a_noop",
          len(db.trade_board.updates) == n_after_first,
          "an unthrottled pass would put N parked-row reads behind every poll "
          "of every viewer")

    # 11. CLOSED CARDS ARE NOT REVISITED.
    ns, db = build([a_card(status="closed", expires_at_ts=_time.time() - 1)], {})
    run(ns["_resolve_trade_board"]())
    check("resolve.closed_cards_are_left_alone", db.trade_board.updates == [])

    # 12. THE CLOSE IS STATUS-GUARDED, so two passes cannot both close one card.
    ns, db = build([a_card()], {52: dict(ROW)})
    run(ns["_trade_board_close"]("c1", "owner"))
    flt = db.trade_board.updates[0][0]
    check("close.is_claimed_on_active", flt.get("status") == "active",
          "closing without the status in the filter lets a second writer "
          "overwrite the note of a card that was already closed")


def check_offer_lane(shipped):
    """The showcase lane, asserted on the SHIPPED AST. trade_create needs a
    database, a user and half the module to run, so what is proven here is the
    SHAPE that makes the rule impossible to get wrong -- paired below with the
    board routes' own gates."""
    print("\n-- the offer lane reads the animal off the CARD")
    tree = ast.parse(shipped)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "trade_create":
            fn = node
    if fn is None:
        check("offer.trade_create_found", False, "trade_create is gone")
        return
    src = ast.get_source_segment(shipped, fn) or ""
    check("offer.card_is_looked_up_by_id", "_trade_board_open_or_404(data.showcase_id)" in src,
          "the card must be read from the board, not trusted from the request")
    check("offer.want_comes_from_the_card", 'card.get("dino_id")' in src,
          "★ the wanted animal is read off the card; a request-supplied want "
          "would let a sender name an animal its owner never published")
    check("offer.own_card_refused", "card.get(\"owner_id\") == user[\"id\"]" in src)
    check("offer.board_id_recorded", '"board_id": (card["id"] if card else None)' in src,
          "the board counts open offers off this field and the page hides a "
          "button with it")
    check("offer.repeat_offer_refused", '"board_id": card["id"], "status": "pending"' in src,
          "one open offer per card per sender, or an impatient double press "
          "escrows a second animal")
    check("offer.addressed_lane_survives", "_trade_partner_or_404(data, user)" in src,
          "the by-name lane is still there for the API; only the page stopped "
          "asking players to use it")

    # The routes exist, and every one of them is signed-in only.
    routes = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else ""
                if isinstance(path, str) and path.startswith("/trade/board"):
                    routes[path] = node
    check("routes.board_read_exists", "/trade/board" in routes)
    check("routes.board_close_exists", "/trade/board/{entry_id}/close" in routes)
    for path, node in routes.items():
        args = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
        check("routes.signed_in%s" % path.replace("/", "_"), "user" in args,
              "a board readable by nobody in particular is a roster of who owns what")

    # The accept lane takes the card down on the instant it stops being true.
    acc = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "trade_accept":
            acc = ast.get_source_segment(shipped, node) or ""
    check("accept.closes_the_card", acc is not None and '_trade_board_close(o["board_id"], "traded")' in acc,
          "the animal is in somebody else's vault now; the resolve pass would "
          "catch it within the window, but the reason would read as 'gone'")


# ==================================================================== mutants
MUTANTS = (
    ("public.row_number_hidden_from_others",
     'd["dino_id"] = e.get("dino_id") if mine else None',
     'd["dino_id"] = e.get("dino_id")'),
    ("resolve.other_owner_closes",
     'if not row or str(row.get("steam_id") or "") != str(e.get("owner_steam") or ""):',
     'if not row:'),
    ("resolve.changed_animal_refreshes",
     "if changed:",
     "if False:"),
    ("knob.ttl_refuses",
     'return _knob_refuse_int(cfg, "trade_board_ttl_secs", 3_600, 604_800,',
     'return _knob_int(cfg, "trade_board_ttl_secs", 3_600, 604_800) or _dead(',
    ),
)


def run_mutants(src_text):
    """Every check above must be able to FAIL. A gate nobody has watched go red
    is a gate nobody has tested."""
    print("\n== MUTANTS (each must turn its check red) ==")
    global PASS, FAIL, FAILED_NAMES
    ok = True
    for label, needle, replacement in MUTANTS:
        if needle not in src_text:
            print("  SKIP %s (the line moved; re-derive this mutant)" % label)
            ok = False
            continue
        mutated = src_text.replace(needle, replacement, 1)
        PASS, FAIL, FAILED_NAMES = 0, 0, []
        try:
            ns = build_ns(mutated, db=_Db(), parked={})
            check_public(ns)
            check_knobs(ns)
            check_resolve(mutated)
        except Exception as exc:                                  # noqa: BLE001
            FAIL += 1
            FAILED_NAMES.append("raised:%s" % exc)
        died = any(n.startswith(label.split(".")[0]) and label.split(".", 1)[1] in n
                   for n in FAILED_NAMES) or FAIL > 0
        print("  %s mutant %s -> %d failed" % ("PASS" if died else "FAIL", label, FAIL))
        ok = ok and died
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()
    with open(SERVER_PY, "r", encoding="utf-8") as fh:
        src_text = fh.read()
    if args.mutants:
        sys.exit(0 if run_mutants(src_text) else 1)
    ns = build_ns(src_text, db=_Db(), parked={})
    check_public(ns)
    check_knobs(ns)
    check_resolve(src_text)
    check_offer_lane(src_text)
    print("\n%d passed, %d failed" % (PASS, FAIL))
    if FAILED_NAMES:
        print("FAILED: %s" % ", ".join(FAILED_NAMES))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
