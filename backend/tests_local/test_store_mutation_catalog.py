# -*- coding: utf-8 -*-
"""The store's mutation picker must BE the vault catalog, not a copy of it.

Until 2026-07-26 `server.MUTATIONS` was a hand-written 16-entry list while
`mutation_catalog.PICKABLE` carried 36, so the store offered 16 names and the
vault editor offered 36 for the same dinosaur (a Triceratops buyer saw 11 where
the editor showed that same Trike 30). This pins the join so the two lists
cannot drift apart again.

server.py cannot be imported here -- it pulls motor/fastapi, which are prod-only
-- so the store block is SLICED OUT OF THE REAL server.py by AST and executed
against the REAL mutation_catalog. That means these assertions run against the
bytes that ship, not against a restatement of them, and they run identically on
this PC and on the box.
"""
from __future__ import annotations

import ast
import logging
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import mutation_catalog  # noqa: E402  (after sys.path)

# The names the store block defines, in source order.
_WANTED = (
    "_store_mutation_key",
    "_LEGACY_STORE_MUTATIONS",
    "_DEFAULT_MUTATION_COST",
    "_build_store_mutations",
    "MUTATIONS",
    "MUTATIONS_BY_KEY",
    "MAX_MUTATION_SLOTS",
)


def _load_store_block():
    """Execute exactly the store-catalog statements out of the real server.py."""
    src = (_BACKEND / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    picked = []
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        if name in _WANTED:
            picked.append(node)
    found = set()
    for node in picked:
        found.add(getattr(node, "name", None) or getattr(getattr(node, "targets", [None])[0], "id", None)
                  or getattr(getattr(node, "target", None), "id", None))
    missing = [n for n in _WANTED if n not in found]
    assert not missing, f"store block no longer defines {missing} at module level in server.py"

    module = ast.Module(body=picked, type_ignores=[])
    ns = {
        "mutation_catalog": mutation_catalog,
        "logger": logging.getLogger("test.store"),
        "__builtins__": __builtins__,
    }
    exec(compile(module, "<server.py store block>", "exec"), ns)  # noqa: S102
    return ns


@pytest.fixture(scope="module")
def store():
    return _load_store_block()


# ── the join itself ───────────────────────────────────────────────────────────

def test_store_offers_exactly_the_vault_catalog(store):
    assert {m["name"] for m in store["MUTATIONS"]} == set(mutation_catalog.PICKABLE)


def test_store_is_not_the_old_sixteen(store):
    # Sensitivity: this test is worthless if it passes on the pre-fix list.
    assert len(store["MUTATIONS"]) == len(mutation_catalog.PICKABLE) > 16


def test_the_site_offers_exactly_what_the_game_has(store):
    """The game has 41 and the site now offers all 41. Parthenogenesis was held
    back while the C++ half that arms its reproduction-unlock byte was
    unshippable; that DLL went live with the 08-10/08-11 rebuilds (the string
    table of the on-box main.dll carries the name), so the hold-back is over.
    Long means the site sells something that does not exist; short means a
    player cannot pick something the server enabled — which is exactly the
    "my 4th mutation is bugged" ticket the hold-back produced once the game
    started rolling the name (58 parked segments by 08-12)."""
    assert len(store["MUTATIONS"]) == 41
    assert "Parthenogenesis" in {m["name"] for m in store["MUTATIONS"]}


def test_every_store_name_is_canonical(store):
    for m in store["MUTATIONS"]:
        assert mutation_catalog.canonical_mutation_name(m["name"]) == m["name"]


def test_sorted_by_name_like_the_editor(store):
    names = [m["name"] for m in store["MUTATIONS"]]
    assert names == sorted(names)


def test_no_duplicate_keys(store):
    keys = [m["key"] for m in store["MUTATIONS"]]
    assert len(keys) == len(set(keys))
    assert len(store["MUTATIONS_BY_KEY"]) == len(keys)


# ── persisted keys: an inventory row must never be orphaned ───────────────────

def test_every_legacy_key_survives(store):
    """db.inventory rows store these keys and _inventory_dino_mutation_keys
    silently DROPS unresolvable ones, so a lost key = a player losing a stored
    mutation."""
    produced = set(store["MUTATIONS_BY_KEY"])
    assert set(store["_LEGACY_STORE_MUTATIONS"]) <= produced


def test_legacy_keys_are_the_exact_sixteen_the_store_sold(store):
    assert set(store["_LEGACY_STORE_MUTATIONS"]) == {
        "cellular_regeneration", "congenital_hypoalgesia", "efficient_digestion",
        "enlarged_meniscus", "epidermal_fibrosis", "featherweight", "hydrodynamic",
        "photosynthetic_tissue", "accelerated_prey_drive", "hematophagy", "hemomania",
        "hypermetabolic_inanition", "enhanced_digestion", "multichambered_lungs",
        "reinforced_tendons", "osteophagic",
    }


# Key -> (display name, PrimeMeat cost) exactly as the store published them
# before the catalog join, transcribed from the pre-fix server.py. These are
# LITERALS on purpose: reading the price back out of _LEGACY_STORE_MUTATIONS and
# comparing it to itself is circular -- it passes on a table whose numbers have
# been edited, which is the whole thing this guards.
_PRE_FIX_STORE = {
    "cellular_regeneration": ("Cellular Regeneration", 15),
    "congenital_hypoalgesia": ("Congenital Hypoalgesia", 18),
    "efficient_digestion": ("Efficient Digestion", 12),
    "enlarged_meniscus": ("Enlarged Meniscus", 10),
    "epidermal_fibrosis": ("Epidermal Fibrosis", 14),
    "featherweight": ("Featherweight", 8),
    "hydrodynamic": ("Hydrodynamic", 10),
    "photosynthetic_tissue": ("Photosynthetic Tissue", 12),
    "accelerated_prey_drive": ("Accelerated Prey Drive", 16),
    "hematophagy": ("Hematophagy", 12),
    "hemomania": ("Hemomania", 14),
    "hypermetabolic_inanition": ("Hypermetabolic Inanition", 15),
    "enhanced_digestion": ("Enhanced Digestion", 20),
    "multichambered_lungs": ("Multichambered Lungs", 18),
    "reinforced_tendons": ("Reinforced Tendons", 12),
    "osteophagic": ("Osteophagic", 14),
}


def test_legacy_keys_and_prices_are_unchanged(store):
    """Every key/name/price the store already published still resolves to the
    same record. Owner economics -- prices do not move as a side effect of a
    catalog change."""
    for key, (name, cost) in _PRE_FIX_STORE.items():
        rec = store["MUTATIONS_BY_KEY"][key]
        assert rec["name"] == name, f"{key} display name moved"
        assert rec["cost"] == cost, f"{key} price moved {cost} -> {rec['cost']}"


def test_the_legacy_table_itself_still_holds_the_shipped_prices(store):
    table = {k: (v[0], v[1]) for k, v in store["_LEGACY_STORE_MUTATIONS"].items()}
    assert table == _PRE_FIX_STORE


def test_key_derivation_round_trips_for_every_name(store):
    make = store["_store_mutation_key"]
    for m in store["MUTATIONS"]:
        assert make(m["name"]) == m["key"]


# ── what the player reads ────────────────────────────────────────────────────

def test_every_entry_has_a_description(store):
    blank = [m["key"] for m in store["MUTATIONS"] if not (m["desc"] or "").strip()]
    assert not blank, f"no description for {blank}"


def test_descriptions_come_from_the_catalog(store):
    """The site is Spanish end to end; the picker was the last surface still
    showing English blurbs."""
    for m in store["MUTATIONS"]:
        assert m["desc"] == mutation_catalog.DESCRIPTIONS[m["name"]]


def test_every_entry_has_a_cost(store):
    for m in store["MUTATIONS"]:
        assert isinstance(m["cost"], int) and m["cost"] > 0


# ── the diet filter /api/mutations applies ───────────────────────────────────

# Counts moved +1 apiece on 2026-08-12: Parthenogenesis (GENERIC — the exe's
# GenericExc group) joined PICKABLE when its C++ activation half went live.
@pytest.mark.parametrize("dino_class,expected", [
    ("BP_Tyrannosaurus_C", 36),
    ("BP_Triceratops_C", 34),
    ("BP_Gallimimus_C", 29),
])
def test_species_filter_matches_the_vault_editor(store, dino_class, expected):
    """/api/mutations?dino_slug= filters MUTATIONS through
    allowed_names_for_class -- exactly what the editor's catalog_for_class does,
    so both screens must return the same count for the same dinosaur."""
    allowed = mutation_catalog.allowed_names_for_class(dino_class)
    shown = [m for m in store["MUTATIONS"]
             if (mutation_catalog.canonical_mutation_name(m["name"]) or "") in allowed]
    assert len(shown) == expected
    assert {m["name"] for m in shown} == {c["name"] for c in mutation_catalog.catalog_for_class(dino_class)}


def test_carnivore_only_names_never_reach_a_herbivore(store):
    allowed = mutation_catalog.allowed_names_for_class("BP_Triceratops_C")
    for name in mutation_catalog.CARNIVORE_ONLY:
        assert name not in allowed


# ── the ordering rule that keeps this out of the dupe path ───────────────────

_MOD_KNOWN = {
    # LaIslaNublarMutV2.known, live payload 906BE480 (main.full.lua) -- the wave that
    # taught the mod the last four names, live since the 2026-07-27 restart. A name
    # the mod does not know is rejected slot-by-slot on redeem AND sets mutations_ok
    # false -- and a not-ok verdict keeps the vault row alive next to a dino that
    # already spawned. So the store may only ever offer names the LIVE mod accepts.
    "hemomania", "acceleratedpreydrive", "hypermetabolicinanition", "osteophagic",
    "augmentedtapetum", "xerocoleadaptation", "tactileendurance", "hematophagy",
    "truculency", "photosyntheticregeneration", "cellularregeneration",
    "advancedgestation", "sustainedhydration", "efficientdigestion", "featherweight",
    "osteosclerosis", "wader", "epidermalfibrosis", "congenitalhypoalgesia",
    "photosynthetictissue", "nocturnal", "hydroregenerative",
    "increasedinspiratorycapacity", "hydrodynamic", "submergedopticalretention",
    "enhanceddigestion", "reinforcedtendons", "multichamberedlungs",
    "infrasoundcommunication", "heightenedghrelin", "prolificreproduction",
    "gastronomicregeneration", "cannibalistic", "hypervigilance", "enlargedmeniscus",
    "reniculatekidneys", "saltwater", "sequentialhermaphroditism", "traumaticthrombosis",
    "reabsorption", "socialbehavior", "barometricsensitivity", "parthenogenesis",
}


def test_store_never_offers_a_name_the_live_mod_would_reject(store):
    unknown = [m["name"] for m in store["MUTATIONS"]
               if mutation_catalog.normalize_mutation_name(m["name"]) not in _MOD_KNOWN]
    assert not unknown, (
        "the live mod's validator does not know %s -- offering it is a "
        "duplicate-dino path, not a cosmetic bug" % unknown)
