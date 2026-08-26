# -*- coding: utf-8 -*-
"""MERIT PRICING gate -- what one ANIMAL is worth, and who keeps the money.

REWRITTEN 2026-08-11. This file previously defended the RETIRED model: the
seller could not name a price and the server forced every listing to the mean of
that species' last 5 sales. That model is gone (each sale raised the next
suggestion, so the series could only climb -- the tell is in the owner's own
live data, active listings repeating to the coin). The rule it now defends is:

    priced_mutations = min(mutation_cap 12, count(mutations) + count(elder_mutations))
                       # parent_mutations EXCLUDED
    suggested        = species_base[slug] + per_mutation_bonus(400,000) * priced_mutations
    price_min        = max(abs_min_price 10,000,      suggested * price_floor_pct(50)   // 100)
    price_max        = min(abs_max_price 25,000,000,  suggested * price_ceiling_pct(300) // 100)
    tax              = price * tax_pct(25) // 100     # INTEGER FLOOR, never round()
    net              = price - tax                    # price == tax + net, ALWAYS

Owner's worked example, which is the arithmetic check: trex 1,000,000 +
12 x 400,000 = 5,800,000; rails 2,900,000 .. 17,400,000; at 25% he nets
4,350,000.

★ WHY THIS FILE LOOKS NOTHING LIKE ITS PREDECESSOR.
The old gate GREPPED SOURCE TEXT -- it asserted that the string
`'"price": data.price'` did not appear in server.py, that `"Price must be
between"` was absent, that two specific log lines were present, and that
`data.price` occurred exactly twice. Those checks lock an IMPLEMENTATION, not an
OUTCOME. They cannot tell a defect from a rename, they go red on a legitimate
change, and one of them (`input_price_optional`) passed against the WRONG CLASS
for weeks -- a DOTALL regex anchored on `class MarketListInput` that actually
matched `StoreItemUpdate.price` 120 lines later. A check that passes for the
wrong reason is worse than one that fails.

So every check below COMPUTES THE EXPECTED NUMBER AND COMPARES IT. The one
remaining structural assertion is AST-SCOPED to a single class node so it cannot
wander into a neighbour, and it is paired with the behaviour it exists to buy.

The functions under test are SLICED OUT OF THE SHIPPED server.py BY AST (by
NAME, so a signature change moves the slice instead of breaking it -- the old
regex `^async def _suggested_price_info\\(slug: str\\) -> dict:` is precisely how
this file died) and executed against real `vault`, a real `mutation_catalog` and
a fake Mongo. server.py itself cannot be imported here: no motor, no .env.

Run:      C:\\Python312\\python.exe tests_local/test_market_suggested_price.py
Mutants:  C:\\Python312\\python.exe tests_local/test_market_suggested_price.py --mutants
Exit: 0 all pass / 1 a check failed / 2 the suite could not run.
"""
import argparse
import ast
import asyncio
import logging
import math
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
SERVER_PY = os.path.join(BACKEND, "server.py")

import mutation_catalog                                             # noqa: E402
import vault                                                        # noqa: E402

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
# The TRANSITIVE closure of module-level helpers the pricing lane needs,
# computed from the AST of server.py rather than guessed.
WANT_FUNCS = (
    "_market_warn_once", "_market_defaults", "_mcfg",
    "_knob_int", "_knob_refuse_int", "_tax_pct", "_tax_on", "_listing_tax_pct",
    "_species_base_table", "_merit",
    "_priced_mut_count", "_inventory_dino_mutation_keys", "_store_mutation_key",
    "_growth_pct_exact", "_growth_pct_display", "_growth_gate_ok",
    "_market_growth_gate_or_409", "_market_price_or_400", "_es_num",
    "_market_stats_info",
)
# SPECIES_BASE_DEFAULT must precede MARKET_DEFAULTS (the latter embeds it at
# assignment time). Everything else resolves at call time.
WANT_CONSTS = (
    "SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
    "MARKET_CFG_CACHE_SECS", "MARKET_SUGGESTED_SALES_WINDOW",
    "MARKET_SALE_FEE_RATE", "_GROWTH_EPS", "_MARKET_WARN_CAP",
    "_MARKET_WARNED_ONCE", "_market_cfg_cache", "_market_cfg_cache_at",
)
EXEC_ORDER = ("SPECIES_BASE_DEFAULT", "MARKET_DEFAULTS", "MARKET_ENV_SEEDS",
              "MARKET_CFG_CACHE_SECS", "MARKET_SUGGESTED_SALES_WINDOW",
              "MARKET_SALE_FEE_RATE", "_GROWTH_EPS", "_MARKET_WARN_CAP",
              "_MARKET_WARNED_ONCE", "_market_cfg_cache",
              "_market_cfg_cache_at") + WANT_FUNCS


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
            # `_MARKET_WARNED_ONCE: set = set()` is annotated; an extractor that
            # only understood bare Assign would drop it silently.
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
    """Honours sort + limit + projection, and RECORDS what was asked for, so the
    query semantics `_market_stats_info` relies on (sold-only, this species
    only, newest first, bounded window, the asking price never fetched) are
    exercised rather than assumed."""

    def __init__(self, rows, projection, journal):
        self._rows = [dict(r) for r in rows]
        self._proj = projection or {}
        self._journal = journal

    def sort(self, key, direction):
        self._journal["sort"] = (key, direction)
        self._rows.sort(key=lambda r: str(r.get(key) or ""), reverse=(direction == -1))
        return self

    async def to_list(self, n):
        self._journal["limit"] = int(n)
        keep = {k for k, v in self._proj.items() if v}
        out = []
        for r in self._rows[: int(n)]:
            out.append({k: v for k, v in r.items() if k in keep} if keep else dict(r))
        return out


class _Coll(object):
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.journal = {}

    @staticmethod
    def _match(r, flt):
        return all(r.get(k) == v for k, v in (flt or {}).items())

    def find(self, flt=None, projection=None):
        self.journal["filter"] = dict(flt or {})
        self.journal["projection"] = dict(projection or {})
        return _Cursor([r for r in self.rows if self._match(r, flt)], projection, self.journal)

    async def find_one(self, flt=None, projection=None):
        for r in self.rows:
            if self._match(r, flt):
                return dict(r)
        return None


class _Db(object):
    def __init__(self, market=None, market_config=None):
        self.market = _Coll(market)
        self.market_config = _Coll(market_config)


# ============================================================ the namespace
_REAL_MUT_KEYS = None


def build_ns(shipped, db=None, mutate=None):
    """Exec the shipped sources into a namespace wired to real dependencies.

    NOTHING under test is re-implemented here. `vault` and `mutation_catalog`
    are the REAL backend modules (stdlib-only, importable without motor), and
    the store mutation catalog is derived from the real
    `mutation_catalog.PICKABLE` through the real `_store_mutation_key`, so the
    inventory branch's catalog-membership filter is satisfied by genuine keys
    rather than by an invented dictionary."""
    global _REAL_MUT_KEYS
    records = []

    class _Cap(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage() if not rec.args else (rec.msg % rec.args))

    log = logging.getLogger("lin.market.gate.%d" % id(records))
    log.handlers = [_Cap()]
    log.propagate = False
    log.setLevel(logging.DEBUG)

    ns = {
        "os": os, "math": math, "time": __import__("time"),
        "logger": log, "HTTPException": HTTPExc,
        "vault": vault, "db": db if db is not None else _Db(),
    }
    for nm in EXEC_ORDER:
        src = shipped[nm]
        if mutate:
            src = mutate(nm, src)
        exec(compile(src, "<shipped:%s>" % nm, "exec"), ns)

    if _REAL_MUT_KEYS is None:
        _REAL_MUT_KEYS = {ns["_store_mutation_key"](n): {"key": ns["_store_mutation_key"](n),
                                                         "name": n}
                          for n in mutation_catalog.PICKABLE}
    ns["MUTATIONS_BY_KEY"] = dict(_REAL_MUT_KEYS)
    ns["__warnings"] = records
    return ns


def cfg_of(ns, **overrides):
    """The SHIPPED defaults with explicit overrides -- i.e. exactly the dict
    `_mcfg()` produces when db.market_config carries those keys."""
    c = ns["_market_defaults"]()
    c.update(overrides)
    return c


KEY = None          # real catalog key lookup, filled in main()


def mkeys(*names):
    """Real store keys for real catalog names. A typo'd name raises here rather
    than silently dropping out of the count inside the function under test."""
    out = []
    for n in names:
        k = n.lower().replace(" ", "_")
        if k not in _REAL_MUT_KEYS:
            raise AssertionError("%r is not in mutation_catalog.PICKABLE" % n)
        out.append(k)
    return out


# The three mutation names in the owner's real-shaped row are all real catalog
# entries; an 8-slot elder set is built from real names too.
ROW_ACTIVE = "Nocturnal|Photosynthetic Tissue|Efficient Digestion|None"   # 3
ELDER_8 = ("Cellular Regeneration|Congenital Hypoalgesia|Efficient Digestion|"
           "Enhanced Digestion|Featherweight|Nocturnal|Photosynthetic Tissue|"
           "Accelerated Prey Drive")                                      # 8
PARENT_FULL = "Cannibalistic|Featherweight|Nocturnal|Hypervigilance"              # 4, must NOT count


def vrow(mutations=ROW_ACTIVE, elder="", parent=PARENT_FULL, growth=0.87):
    return {"mutations": mutations, "elder_mutations": elder,
            "parent_mutations": parent, "growth": growth}


# =============================================================== THE CHECKS
async def run_all(shipped, label=""):
    global PASS, FAIL, FAILED_NAMES
    PASS, FAIL, FAILED_NAMES = 0, 0, []
    ns = build_ns(shipped)
    merit = ns["_merit"]
    tax_on = ns["_tax_on"]
    muts_of = ns["_priced_mut_count"]
    C = cfg_of(ns)

    # ---------------------------------------------------------------------
    print("\n-- 1) THE OWNER'S WORKED EXAMPLE, to the coin --")
    # ---------------------------------------------------------------------
    m = merit(C, "trex", 12)
    check("owner.suggested: trex 1,000,000 + 12 x 400,000 = 5,800,000",
          m["suggested"] == 5_800_000, "got %s" % m["suggested"])
    check("owner.base: read from the 22-row table, not the fallback",
          m["base"] == 1_000_000 and m["base_source"] == "table" and m["base_missing"] is False,
          "base=%s src=%s" % (m["base"], m["base_source"]))
    check("owner.rails: 2,900,000 .. 17,400,000",
          (m["min"], m["max"]) == (2_900_000, 17_400_000), "got %s..%s" % (m["min"], m["max"]))
    tax = tax_on(5_800_000, 25)
    net = 5_800_000 - tax
    check("owner.net: at 25% the seller nets 4,350,000",
          tax == 1_450_000 and net == 4_350_000, "tax=%s net=%s" % (tax, net))
    check("owner.rails are what the rail formula says, not a coincidence",
          m["min"] == m["suggested"] * 50 // 100 and m["max"] == m["suggested"] * 300 // 100)

    # ---------------------------------------------------------------------
    print("\n-- 2) THE MUTATION COUNT: own + elder, PARENT EXCLUDED, capped --")
    # ---------------------------------------------------------------------
    check("mut.vault: real-shaped row 3 active + 8 elder = 11",
          muts_of(C, vault_row=vrow(elder=ELDER_8)) == 11,
          "got %s" % muts_of(C, vault_row=vrow(elder=ELDER_8)))
    # THE DANGEROUS DIRECTION: a full parent column must add exactly nothing.
    check("mut.vault: a FULL parent column adds nothing (grandparent genes are not paid)",
          muts_of(C, vault_row=vrow(elder=ELDER_8, parent=PARENT_FULL))
          == muts_of(C, vault_row=vrow(elder=ELDER_8, parent="None|None|None|None"))
          == 11)
    check("mut.vault: elder set alone is counted (8 with no active slots)",
          muts_of(C, vault_row=vrow(mutations="None|None|None|None", elder=ELDER_8)) == 8,
          "got %s" % muts_of(C, vault_row=vrow(mutations="None|None|None|None", elder=ELDER_8)))
    # 4 active + 12 elder = 16 raw, capped to 12 -- and 12 is the ceiling that
    # makes the owner's own worked example the TOP of the ladder.
    big_elder = "|".join(sorted(mutation_catalog.PICKABLE)[:12])
    check("mut.cap: 4 active + 12 elder = 16 raw -> 12",
          muts_of(C, vault_row=vrow(mutations="Nocturnal|Hypervigilance|Featherweight|Cannibalistic",
                                    elder=big_elder)) == 12,
          "got %s" % muts_of(C, vault_row=vrow(
              mutations="Nocturnal|Hypervigilance|Featherweight|Cannibalistic", elder=big_elder)))
    check("mut.cap is THE KNOB, not a literal: mutation_cap=4 caps at 4",
          muts_of(cfg_of(ns, mutation_cap=4),
                  vault_row=vrow(mutations="Nocturnal|Hypervigilance|Featherweight|Cannibalistic",
                                 elder=big_elder)) == 4)
    # first-run / never-used / empty shapes
    check("mut.empty: blank, None and all-None rows all count 0, no raise",
          muts_of(C, vault_row={}) == 0
          and muts_of(C, vault_row=vrow(mutations=None, elder=None, parent=None)) == 0
          and muts_of(C, vault_row=vrow(mutations="None|None|None|None", elder="")) == 0)
    check("mut.junk: an unreadable mutation column counts 0 rather than raising",
          muts_of(C, vault_row=vrow(mutations=12345, elder=object())) >= 0)
    # the inventory storage shape -- the OTHER branch of the same definition
    inv = {"id": "i1", "mutation_groups": {
        "child": mkeys("Nocturnal", "Photosynthetic Tissue", "Efficient Digestion"),
        "parent": mkeys("Cannibalistic", "Featherweight", "Nocturnal", "Hypervigilance"),
        "elder_a": mkeys("Cellular Regeneration", "Congenital Hypoalgesia",
                         "Enhanced Digestion", "Featherweight"),
        "elder_b": mkeys("Accelerated Prey Drive", "Advanced Gestation",
                         "Augmented Tapetum", "Barometric Sensitivity")}}
    check("mut.inventory: child 3 + elder_a 4 + elder_b 4 = 11, parent's 4 excluded",
          muts_of(C, inv_item=inv) == 11, "got %s" % muts_of(C, inv_item=inv))
    check("mut.inventory: emptying ONLY the parent group changes nothing",
          muts_of(C, inv_item=dict(inv, mutation_groups=dict(inv["mutation_groups"],
                                                             parent=[]))) == 11)
    check("mut.inventory: a first-run doc with no groups at all counts 0, no raise",
          muts_of(C, inv_item={"id": "i2"}) == 0)
    check("mut.inventory: a pre-grouped-editor flat doc is WARNED, never silently priced",
          muts_of(C, inv_item={"id": "i3", "mutations": mkeys("Nocturnal", "Hypervigilance")}) == 2
          and any("mutation_groups" in w for w in ns["__warnings"]),
          str(ns["__warnings"])[:160])
    # the same count, the same price
    check("mut.feeds the price: 11 priced mutations price trex at 5,400,000",
          merit(C, "trex", muts_of(C, vault_row=vrow(elder=ELDER_8)))["suggested"]
          == 1_000_000 + 400_000 * 11)

    # ---------------------------------------------------------------------
    print("\n-- 3) THE TAX: INTEGER FLOOR, and price == tax + net ALWAYS --")
    # ---------------------------------------------------------------------
    P = 5_800_006
    tax = tax_on(P, 25)
    net = P - tax
    naive_round_net = int(round(P * 0.75))          # the implementation this is NOT
    check("tax.floor: 5,800,006 at 25% -> tax 1,450,001, net 4,350,005",
          tax == 1_450_001 and net == 4_350_005, "tax=%s net=%s" % (tax, net))
    check("tax.RED CONTROL: a naive round() answers 4,350,004 -- a DIFFERENT number, "
          "so this check would go red the day the floor becomes a round",
          naive_round_net == 4_350_004 and net != naive_round_net,
          "floor_net=%s round_net=%s" % (net, naive_round_net))
    # conservation over a wide, deliberately awkward range x the whole legal band
    bad_pair = None
    neg_net = None
    for p in (10_000, 10_001, 12_345, 99_999, 100_000, 333_333, 1_000_001,
              2_900_000, 5_800_000, 5_800_006, 5_800_007, 12_345_679,
              17_400_000, 24_999_999, 25_000_000):
        for pct in range(0, 96):
            t = tax_on(p, pct)
            n = p - t
            if t + n != p or t < 0 or t > p:
                bad_pair = (p, pct, t, n)
            if n <= 0:
                neg_net = (p, pct, t, n)
    check("tax.conservation: price == tax + net for 15 prices x every legal percent 0..95",
          bad_pair is None, "first bad %s" % (bad_pair,))
    check("tax.net > 0 at the TOP of the tax band (95%) for every legal price",
          neg_net is None, "first non-positive net %s" % (neg_net,))
    check("tax.floor favours the SELLER: never more than the exact share",
          all(tax_on(p, 25) <= p * 25 / 100.0 for p in (10_001, 5_800_006, 24_999_999)))
    # the dangerous direction: a cut that could PAY the seller out of the treasury
    check("tax.never negative: price <= 0 or pct <= 0 taxes nothing",
          tax_on(0, 25) == 0 and tax_on(-5_000_000, 25) == 0
          and tax_on(5_800_000, 0) == 0 and tax_on(5_800_000, -25) == 0)
    check("tax.junk input answers 0 instead of raising",
          tax_on(None, 25) == 0 and tax_on("abc", 25) == 0
          and tax_on(5_800_000, None) == 0 and tax_on(float("nan"), 25) == 0)
    # the percent a listing SETTLES at is the snapshot, never today's knob
    lp = ns["_listing_tax_pct"]
    check("tax.snapshot: a listing settles on its own tax_pct, not the live knob",
          lp({"tax_pct": 25}) == 25 and lp({"tax_pct": 10, "fee_rate": 0.25}) == 10)
    check("tax.grandfathered: a pre-wave row derives its percent from fee_rate",
          lp({"fee_rate": 0.15}) == 15 and lp({"fee_rate": 0.10}) == 10 and lp({}) == 15)
    check("tax.snapshot junk: an unreadable snapshot clamps into 0..100, never raises",
          lp({"tax_pct": True}) == 15 and lp({"fee_rate": "x"}) == 15
          and 0 <= lp({"fee_rate": 99.0}) <= 100)

    # ---------------------------------------------------------------------
    print("\n-- 4) THE RAILS: 50% floor, 300% ceiling, absolutes clamp when tighter --")
    # ---------------------------------------------------------------------
    for slug, base in (("trex", 1_000_000), ("deino", 1_500_000), ("troodon", 300_000)):
        for n in (0, 1, 12):
            mm = merit(C, slug, n)
            want = base + 400_000 * n
            if not (mm["suggested"] == want
                    and mm["min"] == max(10_000, want * 50 // 100)
                    and mm["max"] == min(25_000_000, want * 300 // 100)):
                check("rails.formula %s@%s" % (slug, n), False, str(mm))
                break
    else:
        check("rails.formula holds for 3 species x 0/1/12 mutations", True)
    check("rails.floor is 50%: trex@12 min is exactly half the suggestion",
          merit(C, "trex", 12)["min"] * 2 == 5_800_000)
    check("rails.ceiling is 300%: trex@12 max is exactly triple the suggestion",
          merit(C, "trex", 12)["max"] == 3 * 5_800_000)
    check("rails.the RAIL binds under the shipped table (not the absolutes)",
          merit(C, "trex", 12)["min_bound_by"] == "rail"
          and merit(C, "trex", 12)["max_bound_by"] == "rail")
    # ABSOLUTE MIN binds: it is max(abs_min, rail_lo), so raising abs_min above
    # the rail must RAISE the floor. If min were min(), this reads 500,000.
    hi_min = merit(cfg_of(ns, abs_min_price=1_000_000), "trex", 0)
    check("rails.abs_min CLAMPS UP when tighter than the 50% rail",
          hi_min["suggested"] == 1_000_000 and hi_min["min"] == 1_000_000
          and hi_min["min_bound_by"] == "abs", str(hi_min))
    # ABSOLUTE MAX binds: min(abs_max, rail_hi). With the owner-editable
    # per_mutation_bonus at the top of its band the rail overshoots the cap.
    hi_max = merit(cfg_of(ns, per_mutation_bonus=1_000_000), "deino", 12)
    check("rails.abs_max CLAMPS DOWN when tighter than the 300% rail",
          hi_max["suggested"] == 13_500_000 and hi_max["max"] == 25_000_000
          and hi_max["max_bound_by"] == "abs" and hi_max["min"] == 6_750_000, str(hi_max))
    check("rails.min is never above max, even when both absolutes are pinched",
          merit(cfg_of(ns, abs_min_price=1_000_000, abs_max_price=1_000_000),
                "troodon", 0)["min"] <= merit(cfg_of(ns, abs_min_price=1_000_000,
                                                     abs_max_price=1_000_000),
                                              "troodon", 0)["max"])
    check("rails.floor/ceiling percents are KNOBS: 10% / 1000% move the rails",
          merit(cfg_of(ns, price_floor_pct=10, price_ceiling_pct=1000), "trex", 12)["min"]
          == 580_000
          and merit(cfg_of(ns, price_floor_pct=10, price_ceiling_pct=1000),
                    "trex", 12)["max"] == 25_000_000)
    # the dangerous direction: a negative count must not discount an animal
    check("rails.a negative mutation count floors at 0, never below the base",
          merit(C, "trex", -5)["suggested"] == 1_000_000)

    # ---- the seller's own number, against those rails ----
    price_or_400 = ns["_market_price_or_400"]
    m12 = merit(C, "trex", 12)

    def refused(raw, mm=m12):
        try:
            price_or_400(raw, mm)
            return None
        except HTTPExc as e:
            return e

    check("price.accepts EXACTLY the floor and EXACTLY the ceiling (boundaries are legal)",
          price_or_400(2_900_000, m12) == 2_900_000
          and price_or_400(17_400_000, m12) == 17_400_000)
    check("price.refuses one coin below the floor and one coin above the ceiling",
          refused(2_899_999) is not None and refused(17_400_001) is not None)
    check("price.refusal names the number that actually bound",
          "2.900.000" in (refused(2_899_999).detail or "")
          and "17.400.000" in (refused(17_400_001).detail or ""),
          refused(2_899_999).detail)
    check("price.absolute minimum fires before the rail message can mislead",
          "10.000" in (refused(1, merit(cfg_of(ns, price_floor_pct=10), "troodon", 0)).detail or ""),
          refused(1, merit(cfg_of(ns, price_floor_pct=10), "troodon", 0)).detail)
    # THE DANGEROUS DIRECTION for a raw, uncoerced field: True is an int in
    # Python and would price a 5,800,000 animal at 1.
    check("price.TYPE refusals: True / 5.5 / \"5000\" / None are all refused, "
          "so no animal can be sold for 1",
          all(refused(x) is not None for x in (True, False, 5.5, "5000", None, "", [1])),
          "one of them was ACCEPTED")
    check("price.a legal int inside the rails is returned unchanged (the seller's own number)",
          price_or_400(5_800_000, m12) == 5_800_000)

    # ---------------------------------------------------------------------
    print("\n-- 5) THE 80% GROWTH GATE, in BOTH unit systems --")
    # ---------------------------------------------------------------------
    exact = ns["_growth_pct_exact"]
    disp = ns["_growth_pct_display"]
    gate = ns["_growth_gate_ok"]
    # vault stores a 0..1 FLOAT; these three are real measured live values
    check("growth.vault real values: 0.898333 -> 89 ok, 0.800854 -> 80 ok, 0.263085 -> 26 refused",
          (disp(exact(0.898333, "vault")), gate(C, exact(0.898333, "vault"))) == (89, True)
          and (disp(exact(0.800854, "vault")), gate(C, exact(0.800854, "vault"))) == (80, True)
          and (disp(exact(0.263085, "vault")), gate(C, exact(0.263085, "vault"))) == (26, False))
    check("growth.vault BOUNDARY: exactly 0.80 is ADMITTED and displays 80",
          gate(C, exact(0.80, "vault")) is True and disp(exact(0.80, "vault")) == 80)
    check("growth.vault BOUNDARY: 0.7999 is REFUSED and displays 79",
          gate(C, exact(0.7999, "vault")) is False and disp(exact(0.7999, "vault")) == 79)
    # website inventory stores an INTEGER PERCENT (park_dino writes round(g,1))
    check("growth.inventory BOUNDARY: exactly 80 is ADMITTED and displays 80",
          gate(C, exact(80, "inventory")) is True and disp(exact(80, "inventory")) == 80)
    check("growth.inventory BOUNDARY: 79.9 is REFUSED and displays 79",
          gate(C, exact(79.9, "inventory")) is False and disp(exact(79.9, "inventory")) == 79)
    check("growth.inventory real value 87.3 -> 87, admitted",
          disp(exact(87.3, "inventory")) == 87 and gate(C, exact(87.3, "inventory")) is True)
    # THE UNIT TRAP: a gate written against the wrong unit refuses everything or
    # refuses nothing, and both failures are silent.
    check("growth.unit: 0.87 read as INVENTORY is 0.87% -> refused (not 87%)",
          disp(exact(0.87, "inventory")) == 0 and gate(C, exact(0.87, "inventory")) is False)
    check("growth.unit: 87 read as VAULT is out of the 0..1 range -> unreadable, refused",
          exact(87, "vault") is None and gate(C, exact(87, "vault")) is False)
    check("growth.unreadable is REFUSED, never admitted "
          "(None, '', 'abc', NaN, inf, -1, 101)",
          all(gate(C, exact(v, "inventory")) is False
              for v in (None, "", "abc", float("nan"), float("inf"), -1, 101))
          and all(gate(C, exact(v, "vault")) is False
                  for v in (None, "abc", float("nan"), float("inf"), -0.5, 1.5)))
    # ★ THE PAIRING LAW: a card can NEVER display 80% for an animal the gate refuses.
    broken = []
    for i in range(0, 10_001):
        f = i / 10_000.0                       # vault: 0.0000 .. 1.0000
        if (disp(exact(f, "vault")) >= 80) != bool(gate(C, exact(f, "vault"))):
            broken.append(("vault", f))
        p = i / 100.0                          # inventory: 0.00 .. 100.00
        if (disp(exact(p, "inventory")) >= 80) != bool(gate(C, exact(p, "inventory"))):
            broken.append(("inventory", p))
    check("growth.PAIRING LAW over 20,002 values in both unit systems: "
          "displayed >= 80  <=>  the gate admits it",
          not broken, "first %s of %d breaks" % (broken[:3], len(broken)))
    check("growth.gate is the KNOB: min_growth_pct=90 refuses an 87% animal that 80 admits",
          gate(cfg_of(ns, min_growth_pct=90), exact(0.87, "vault")) is False
          and gate(C, exact(0.87, "vault")) is True)
    # the refusal a player actually reads
    g409 = ns["_market_growth_gate_or_409"]
    try:
        g409(C, exact(0.263085, "vault"))
        caught = None
    except HTTPExc as e:
        caught = e
    check("growth.409 quotes the real numbers (80 required, 26 held, 54 short)",
          caught is not None and caught.status_code == 409
          and "80%" in caught.detail and "26%" in caught.detail and "54" in caught.detail,
          caught.detail if caught else "no refusal raised")
    try:
        g409(C, exact(None, "vault"))
        caught2 = None
    except HTTPExc as e:
        caught2 = e
    check("growth.409 on UNREADABLE growth says so, rather than passing",
          caught2 is not None and caught2.status_code == 409)
    check("growth.an admitted animal raises nothing",
          g409(C, exact(0.898333, "vault")) is None)

    # ---------------------------------------------------------------------
    print("\n-- 6) A SPECIES MISSING FROM THE BASE TABLE FALLS BACK, AND SAYS SO --")
    # ---------------------------------------------------------------------
    ns2 = build_ns(shipped)
    mm = ns2["_merit"](cfg_of(ns2), "brachiosaurus", 2)
    check("base.miss: an unknown slug takes the 400,000 fallback, flagged as fallback",
          mm["base"] == 400_000 and mm["base_source"] == "fallback"
          and mm["base_missing"] is True and mm["suggested"] == 1_200_000, str(mm))
    check("base.miss is NOT SILENT: a warning naming the slug is logged",
          any("species_base MISS" in w and "brachiosaurus" in w for w in ns2["__warnings"]),
          str(ns2["__warnings"])[:200])
    ns3 = build_ns(shipped)
    ns3["_merit"](cfg_of(ns3), "trex", 2)
    check("base.hit is quiet (so the check above is not vacuous)",
          not any("species_base MISS" in w for w in ns3["__warnings"]),
          str(ns3["__warnings"])[:200])
    check("base.empty slug falls back rather than raising",
          ns2["_merit"](cfg_of(ns2), "", 0)["base"] == 400_000
          and ns2["_merit"](cfg_of(ns2), None, 0)["base"] == 400_000)
    ns4 = build_ns(shipped)
    bad_table = dict(ns4["SPECIES_BASE_DEFAULT"])
    bad_table["trex"] = 99_999_999          # outside 50,000..2,000,000
    mm4 = ns4["_merit"](cfg_of(ns4, species_base=bad_table), "trex", 0)
    check("base.an out-of-band table entry is treated as ABSENT (never coerced), and warns",
          mm4["base"] == 400_000 and mm4["base_source"] == "fallback"
          and any("species_base[" in w for w in ns4["__warnings"]), str(mm4))
    check("base.the whole table being junk falls back to the shipped 22 rows",
          ns4["_merit"](cfg_of(ns4, species_base="not a table"), "trex", 0)["base"] == 1_000_000)

    # ---------------------------------------------------------------------
    print("\n-- 7) THE STATS LANE IS DISPLAY ONLY: A WASH SALE MOVES NOTHING --")
    # ---------------------------------------------------------------------
    def sold(slug, sold_price, at, ask=None):
        return {"dino_slug": slug, "status": "sold", "type": "sale",
                "price": ask if ask is not None else sold_price,
                "sold_price": sold_price, "sold_at": at}

    def active(slug, ask):
        return {"dino_slug": slug, "status": "active", "type": "sale",
                "price": ask, "sold_price": None, "sold_at": None}

    rows = [sold("dilo", 350_000, "2026-08-05T10:00:00+00:00"),
            sold("dilo", 340_000, "2026-08-05T09:00:00+00:00"),
            sold("dilo", 360_000, "2026-08-05T08:00:00+00:00"),
            active("dilo", 99_000_000),                       # an ASK, never a sale
            sold("trex", 8_000_000, "2026-08-05T10:30:00+00:00")]   # another species
    dbx = _Db(market=rows)
    nsq = build_ns(shipped, db=dbx)
    st = await nsq["_market_stats_info"]("dilo")
    check("stats.median of the real sales, active asks and other species excluded",
          st["samples"] == 3 and st["median"] == 350_000
          and (st["low"], st["high"]) == (340_000, 360_000), str(st))
    check("stats.last_sold is the NEWEST sale",
          st["last_sold"] and st["last_sold"]["price"] == 350_000, str(st.get("last_sold")))
    j = dbx.market.journal
    check("stats.query semantics: sold-only, this species only, newest first, "
          "bounded to the window",
          j["filter"] == {"dino_slug": "dilo", "status": "sold"}
          and j["sort"] == ("sold_at", -1)
          and j["limit"] == nsq["MARKET_SUGGESTED_SALES_WINDOW"], str(j))
    check("stats.the ASKING price is never even fetched (not in the projection)",
          "price" not in j["projection"] and j["projection"].get("sold_price") == 1,
          str(j["projection"]))
    # SURVIVING RULE, repointed from the retired _suggested_price_info: a row
    # whose price cannot be read is SKIPPED, never raised on.
    dbb = _Db(market=[sold("carno", "garbage", "2026-08-05T10:00:00+00:00"),
                      sold("carno", None, "2026-08-05T09:30:00+00:00"),
                      sold("carno", 500_000, "2026-08-05T09:00:00+00:00")])
    nsb = build_ns(shipped, db=dbb)
    stb = await nsb["_market_stats_info"]("carno")
    check("stats.bad_row_skipped: an unreadable price is SKIPPED, never raised on",
          stb["samples"] == 1 and stb["median"] == 500_000, str(stb))
    dbe = _Db(market=[])
    nse = build_ns(shipped, db=dbe)
    ste = await nse["_market_stats_info"]("hypsi")
    check("stats.first run: no sales answers samples 0 / median None, no raise",
          ste["samples"] == 0 and ste["median"] is None and ste["last_sold"] is None, str(ste))
    # ★ THE HEADLINE: the ratchet is structurally dead.
    before = merit(C, "dilo", 3)
    wash = [sold("dilo", 25_000_000, "2026-08-06T%02d:00:00+00:00" % i) for i in range(10)]
    dbw = _Db(market=rows + wash)
    nsw = build_ns(shipped, db=dbw)
    stw = await nsw["_market_stats_info"]("dilo")
    after = nsw["_merit"](cfg_of(nsw), "dilo", 3)
    check("stats.the wash sales really landed (the fixture is not vacuous)",
          stw["median"] == 25_000_000 and stw["samples"] == 10, str(stw))
    check("★ WASH SALE CANNOT MOVE THE PRICE: 10 sales at 25,000,000 leave the "
          "suggestion and both rails byte-identical",
          (after["suggested"], after["min"], after["max"])
          == (before["suggested"], before["min"], before["max"])
          == (1_600_000, 800_000, 4_800_000),
          "before=%s after=%s" % (before["suggested"], after["suggested"]))

    # ---------------------------------------------------------------------
    print("\n-- 8) THE CONFIG LAYER IS LIVE (a knob change needs no deploy) --")
    # ---------------------------------------------------------------------
    nsc = build_ns(shipped, db=_Db(market_config=[
        {"_id": "market", "sale_tax_pct": 10, "per_mutation_bonus": 250_000,
         "not_a_real_knob": "ignored"}]))
    live = await nsc["_mcfg"]()
    check("cfg.a stored document OVERRIDES the shipped default",
          live["sale_tax_pct"] == 10 and live["per_mutation_bonus"] == 250_000)
    check("cfg.a stray field in the document is never merged in",
          "not_a_real_knob" not in live)
    check("cfg.untouched knobs keep their shipped defaults",
          live["mutation_cap"] == 12 and live["abs_min_price"] == 10_000
          and live["price_ceiling_pct"] == 300)
    check("cfg.the live document actually moves the price",
          nsc["_merit"](live, "trex", 12)["suggested"] == 1_000_000 + 250_000 * 12)
    check("cfg.the live document actually moves the tax",
          nsc["_tax_on"](5_800_000, nsc["_tax_pct"](live, "sale")) == 580_000)
    # REFUSE, not clamp: a knob that decides who gets paid must never be guessed.
    for bad in (500, -1, True, 25.0, "25", None):
        try:
            nsc["_tax_pct"](cfg_of(nsc, sale_tax_pct=bad), "sale")
            check("cfg.REFUSE sale_tax_pct=%r" % (bad,), False, "it was ACCEPTED")
            break
        except HTTPExc as e:
            if e.status_code != 503 or "sale_tax_pct" not in (e.detail or ""):
                check("cfg.REFUSE sale_tax_pct=%r" % (bad,), False, e.detail)
                break
    else:
        check("cfg.a broken tax knob REFUSES with 503 naming the knob "
              "(500 / -1 / True / 25.0 / \"25\" / None), never clamps", True)
    check("cfg.defaults are never mutated through the dict a caller was handed",
          cfg_of(nsc, mutation_cap=1) is not None
          and nsc["MARKET_DEFAULTS"]["mutation_cap"] == 12
          and nsc["_market_defaults"]()["species_base"]["trex"] == 1_000_000)

    print("\n%s%d passed, %d failed" % (label, PASS, FAIL))
    return PASS, FAIL, list(FAILED_NAMES)


# =============================================================== structural
def structural(src_text):
    """The ONE structural assertion left, and it is AST-SCOPED.

    It replaces the retired `input_price_optional`, which used a DOTALL regex
    anchored on `class MarketListInput(BaseModel):` and in fact matched
    `StoreItemUpdate.price: Optional[int] = None` 120 lines further down -- it
    had been passing for the wrong class. This reads the MarketListInput class
    NODE and nothing else, so it cannot wander.

    What it pins is the precondition for the type refusals proved in section 4:
    `price` must reach the route RAW. Typed `Optional[int]`, pydantic would
    coerce "5000" to 5000 and answer 5.5 with a 422 in English, and the lane
    owes this owner's players one exact Spanish sentence per wrong shape."""
    tree = ast.parse(src_text)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MarketListInput":
            for st in node.body:
                if isinstance(st, ast.AnnAssign) and getattr(st.target, "id", None) == "price":
                    ann = ast.unparse(st.annotation)
                    dflt = ast.unparse(st.value) if st.value is not None else "<none>"
                    check("input.MarketListInput.price is RAW (`Any`), not coerced by pydantic "
                          "-- AST-scoped to this class, unlike the check it replaces",
                          ann == "Any" and dflt == "None",
                          "annotation=%r default=%r" % (ann, dflt))
                    return
            check("input.MarketListInput declares a `price` field", False,
                  "no annotated `price` in the class body")
            return
    check("input.MarketListInput class exists in server.py", False, "class not found")


# ================================================================== mutants
# Each mutant reverts one decision in an IN-MEMORY copy of the shipped source.
# Disk is never touched. A mutant that leaves the battery green is a leg that
# proves nothing.
MUTANTS = {
    "M1 tax FLOOR becomes round()": [
        ("_tax_on", "    return p * q // 100",
         "    return int(round(p * q / 100.0))")],
    "M2 elder column dropped from the count (vault)": [
        ("_priced_mut_count", "             + vault._mutation_count(vault_row.get(\"elder_mutations\")))",
         "             + 0)")],
    "M2b elder groups dropped from the count (inventory)": [
        ("_priced_mut_count", "    return max(0, min(cap, len(own) + len(ea) + len(eb)))",
         "    return max(0, min(cap, len(own)))")],
    "M3 rails: min swapped for max on the FLOOR": [
        ("_merit", "    lo = max(abs_min, rail_lo)", "    lo = min(abs_min, rail_lo)")],
    "M3b rails: max swapped for min on the CEILING": [
        ("_merit", "    hi = min(abs_max, rail_hi)", "    hi = max(abs_max, rail_hi)")],
    "M4 mutation cap 12 becomes 4": [
        ("MARKET_DEFAULTS", '    "mutation_cap": 12,', '    "mutation_cap": 4,')],
    "M5 parent mutations INCLUDED (vault)": [
        ("_priced_mut_count", "             + vault._mutation_count(vault_row.get(\"elder_mutations\")))",
         "             + vault._mutation_count(vault_row.get(\"elder_mutations\"))\n"
         "             + vault._mutation_count(vault_row.get(\"parent_mutations\")))")],
    "M5b parent groups INCLUDED (inventory)": [
        ("_priced_mut_count", "    return max(0, min(cap, len(own) + len(ea) + len(eb)))",
         "    return max(0, min(cap, len(own) + len(_parent) + len(ea) + len(eb)))")],
    "M6 growth DISPLAY floors -> rounds (breaks the pairing law)": [
        ("_growth_pct_display", "        return int(math.floor(float(exact) + _GROWTH_EPS))",
         "        return int(round(float(exact)))")],
    "M7 vault growth read in the WRONG UNIT (fraction as percent)": [
        ("_growth_pct_exact", "        return val * 100.0", "        return val")],
    "M8 species_base MISS goes silent": [
        ("_merit", "    if missing:\n", "    if False:\n")],
    "M9 the sales window shrinks from the knob to 3": [
        ("MARKET_SUGGESTED_SALES_WINDOW", "MARKET_SUGGESTED_SALES_WINDOW = 10",
         "MARKET_SUGGESTED_SALES_WINDOW = 3")],
    "M10 a negative price is taxed (pays the seller out of the treasury)": [
        ("_tax_on", "    if p <= 0 or q <= 0:", "    if False:")],
    "M11 the price TYPE check is removed (True prices an animal at 1)": [
        ("_market_price_or_400", "    if isinstance(raw, bool) or not isinstance(raw, int):",
         "    if False:")],
    "M12 the mutation count is no longer floored at 0": [
        ("_merit", "    n = max(0, int(muts))", "    n = int(muts)")],
    "M13 the stats median is fed back into the suggestion (the retired ratchet)": [
        ("_merit", "    sug = base + per_mut * n",
         "    sug = base + per_mut * n + int(_RATCHET[0])")],
}
# M13 needs one extra name; it exists only so the ratchet can be reintroduced
# and proven dead. It is injected for every run, mutant or not, and is 0 in the
# baseline so it changes nothing.
_RATCHET_INJECT = "_RATCHET = [0]\n"


async def run_mutants(shipped):
    print("\n=== MUTANTS (each must turn the battery RED) ===")
    survivors = []
    for name, edits in MUTANTS.items():
        mutated = dict(shipped)
        stale = False
        for target, old, new in edits:
            if old not in mutated[target]:
                print("\n### %s -- ANCHOR NOT FOUND in %s (mutant is stale)" % (name, target))
                survivors.append(name + " [stale anchor]")
                stale = True
                break
            mutated[target] = mutated[target].replace(old, new, 1)
        if stale:
            continue
        if name.startswith("M13"):
            mutated["SPECIES_BASE_DEFAULT"] = ("_RATCHET = [25_000_000]\n"
                                               + mutated["SPECIES_BASE_DEFAULT"])
        print("\n### %s" % name)
        try:
            mp, mf, names = await run_all(mutated, label="mutant: ")
        except Exception as exc:
            mp, mf, names = 0, 1, ["the suite RAISED: %s: %s" % (type(exc).__name__, exc)]
            print("  (suite raised: %s: %s)" % (type(exc).__name__, exc))
        if mf == 0:
            survivors.append(name)
            print("  !! SURVIVED -- no leg caught it")
        else:
            print("  killed by: %s" % "; ".join(names[:3]))
    print("\n=== mutant summary ===")
    if survivors:
        print("SURVIVORS (%d/%d) -- the battery is too weak: %s"
              % (len(survivors), len(MUTANTS), survivors))
        return 1
    print("ALL %d MUTANTS KILLED" % len(MUTANTS))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    with open(SERVER_PY, "r", encoding="utf-8") as fh:
        src = fh.read()
    shipped = extract_shipped(src)
    missing = [n for n in WANT_FUNCS + WANT_CONSTS if n not in shipped]
    if missing:
        print("CANNOT RUN: not found in server.py: %s" % missing)
        return 2
    # the M13 hook, inert in the baseline (see _RATCHET_INJECT)
    shipped["SPECIES_BASE_DEFAULT"] = _RATCHET_INJECT + shipped["SPECIES_BASE_DEFAULT"]
    print("shipped bytes under test: %s" % ", ".join(sorted(WANT_FUNCS)))

    p, f, _ = asyncio.run(run_all(shipped))
    structural(src)
    print("\nTOTAL: %d passed, %d failed" % (PASS, FAIL))
    if FAIL:
        print("FAILED: %s" % ", ".join(FAILED_NAMES))
    if not args.mutants:
        return 0 if FAIL == 0 else 1
    if FAIL:
        print("\nbaseline is RED -- not running mutants")
        return 1
    return asyncio.run(run_mutants(shipped))


if __name__ == "__main__":
    sys.exit(main())
