# -*- coding: utf-8 -*-
"""Crate rework gate — reward pools, glitch catalog, engine payload guard.

Imports the REAL backend/seed_data.py + glitch_catalog.py (both pure data, no
Mongo/env needed). The server.py grant/apply lanes on top are exercised by the
prod E2E; the amount-roll formula is mirrored inline here — kept in sync with
server.py _grant_case_reward.

Run: python backend/tests_local/test_crates_glitch_rewards.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import glitch_catalog as gc  # noqa: E402
import seed_data  # noqa: E402

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


EXPECTED_IDS = [
    "void-prism-gold", "void-prism-blue", "void-prism-green",
    "cobalt-void", "blue-void", "red-void", "orchid-void", "black-cyan",
    "the-devil", "supernova",
]
SLOTS = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")


print("[catalog]")
# 2026-08-18 owner order ("constelacion for battlepass only"): constelacion
# LEFT this list for BP_SKINS. GLITCH_SKINS is the CRATE list, so leaving it
# is the thing that makes "only" true -- see the exclusivity block below.
check("ten crate skins (constelacion left for the Battle Pass 2026-08-18)",
      len(gc.GLITCH_SKINS) == 10, f"got {len(gc.GLITCH_SKINS)}")
check("ids canonical", [g["id"] for g in gc.GLITCH_SKINS] == EXPECTED_IDS)
# GLITCH_BY_ID resolves BOTH families (crate glitches + Battle Pass exclusives);
# GLITCH_SKINS is the CRATE list alone, which is what seed_data enumerates.
check("ids unique across all three families",
      len(gc.GLITCH_BY_ID) == len(gc.GLITCH_SKINS) + len(gc.BP_SKINS) + len(gc.CREATOR_SKINS))
check("no Creator Program id leaks into the crate list",
      not any(g["id"] in {c["id"] for c in gc.CREATOR_SKINS} for g in gc.GLITCH_SKINS)
      and all(not gc.crate_eligible(c["id"]) for c in gc.CREATOR_SKINS))
check("no Battle Pass id leaks into the crate list",
      not any(g.get("bp_exclusive") for g in gc.GLITCH_SKINS))
check("red void + black cyan named",
      gc.GLITCH_BY_ID["red-void"]["name"] == "Red Void"
      and gc.GLITCH_BY_ID["black-cyan"]["name"] == "Black Cyan")
check("the two 08-13 additions named",
      gc.GLITCH_BY_ID["constelacion"]["name"] == "Constelación"
      and gc.GLITCH_BY_ID["supernova"]["name"] == "Supernova")

# ---------------------------------------------------------------------------
# 2026-08-18 OWNER ORDER: "constelacion for battlepass only".
#
# "Only" is a claim about every OTHER way to win it, so it is gated at every
# door at once: the crate id pool, the eligibility predicate, and the two
# podiums that were paying it (the season board here, the creator board in
# test_creator_program). The MOVE is not cosmetic bookkeeping -- the uncommon
# crate's ("glitch","any") wildcard shares its weight across whatever is in
# GLITCH_SKINS, so an entry left behind with only a flag on it would still
# have dropped from a 25.000 PrimeMeat crate.
#
# And the skin itself must be UNCHANGED: this order moved where it is won,
# never what it looks like, so the payload and the wire command are pinned
# byte-for-byte against the owner's own payload 1 below (OWNER_PAYLOAD_1).
print("[battlepass only 2026-08-18]")
check("constelacion is NOT in the crate list",
      "constelacion" not in [g["id"] for g in gc.GLITCH_SKINS])
check("constelacion IS a Battle Pass skin now",
      "constelacion" in [g["id"] for g in gc.BP_SKINS])
check("constelacion is flagged bp_exclusive",
      gc.GLITCH_BY_ID["constelacion"].get("bp_exclusive") is True)
check("no crate may drop constelacion", gc.crate_eligible("constelacion") is False)
check("constelacion is NOT in the crate id pool seed_data enumerates",
      "constelacion" not in seed_data._GLITCH_IDS)
check("constelacion still resolves for granting/applying (already-won copies)",
      gc.GLITCH_BY_ID.get("constelacion") is not None)
check("constelacion keeps its Legendary rarity on the pass cell",
      gc.GLITCH_BY_ID["constelacion"].get("bp_rarity") == "Legendary")
# supernova is the OTHER half of the order and deliberately did NOT move.
check("supernova is still crate-droppable", gc.crate_eligible("supernova") is True
      and "supernova" in seed_data._GLITCH_IDS)
# THE TWO GATES AGREE. Before 2026-08-18 the pool was list membership alone
# while crate_eligible() read the flag -- two sources for one rule. Flagging a
# design is now sufficient wherever it sits.
check("the crate id pool == the crate-eligible members of GLITCH_SKINS",
      seed_data._GLITCH_IDS == [g["id"] for g in gc.GLITCH_SKINS
                                if gc.crate_eligible(g["id"])])
check("no bp/creator exclusive of ANY family reaches the crate id pool",
      not any(gc.GLITCH_BY_ID[i].get("bp_exclusive") for i in seed_data._GLITCH_IDS))
for g in gc.GLITCH_SKINS:
    ok = all(k in g for k in ("id", "name", "subtitle", "accent_hex", "category", "preview", "payload"))
    ok = ok and all(s in g["payload"] for s in SLOTS) and "pattern" in g["payload"]
    check(f"shape {g['id']}", ok)

# A glitch card is a NAME + COLOUR PROXIMITY, never a picture (fleet order
# 2026-08-11). The 08-12 deploy had silently RESURRECTED the retired renders
# because they still lived in frontend/public — this block is the regression
# door, welded: preview "" on every entry, no render files in the repo, and a
# 7-band validated proximity strip on every public view.
_PREVIEW_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public")
check("no glitch skin carries a preview image",
      all(g["preview"] == "" for g in gc.GLITCH_SKINS + gc.BP_SKINS),
      str([g["preview"] for g in gc.GLITCH_SKINS + gc.BP_SKINS if g["preview"]]))
_prev_dir = os.path.join(_PREVIEW_ROOT, "glitch", "previews")
_leftover = sorted(os.listdir(_prev_dir)) if os.path.isdir(_prev_dir) else []
check("no glitch render files under frontend/public (the deploy-resurrection door)",
      not _leftover, str(_leftover))
import re as _re  # noqa: E402
for g in gc.GLITCH_SKINS + gc.BP_SKINS:
    v = gc.public_view(g)
    ok = (v["image"] == "" and isinstance(v.get("proximity"), list)
          and len(v["proximity"]) == 7
          and all(_re.fullmatch(r"#[0-9a-f]{6}", h) for h in v["proximity"]))
    check(f"proximity strip {g['id']} (7 validated hexes, image empty)", ok, str(v.get("proximity")))

print("[guard]  (2026-08-13: emission is VERBATIM — authored variation/pattern ride through)")
for g in gc.GLITCH_SKINS:
    cmd = gc.build_glitch_command(g["id"], "BP_Test_C_1", "BP_Test_C", "76561199000000001", True)
    check(f"{g['id']} authored variation verbatim",
          cmd["variation"] == g["payload"]["variation"], str(cmd["variation"]))
    check(f"{g['id']} authored pattern verbatim",
          cmd["pattern"] == g["payload"]["pattern"], str(cmd["pattern"]))
    check(f"{g['id']} no color_space key", "color_space" not in cmd)
    in_range = True
    polarity_ok = True
    for s in SLOTS:
        r, gg, b, a = cmd[s]
        if max(abs(r), abs(gg), abs(b)) > gc.GLITCH_CHANNEL_MAX + 1e-6 or abs(a) > gc.GLITCH_CHANNEL_MAX + 1e-6:
            in_range = False
        raw = g["payload"][s]
        for rawv, normv in zip(raw[:3], (r, gg, b)):
            if rawv > 0 and normv < 0:
                polarity_ok = False
            if rawv < 0 and normv > 0:
                polarity_ok = False
            if rawv == 0 and normv != 0:
                polarity_ok = False
    check(f"{g['id']} values within +/-{int(gc.GLITCH_CHANNEL_MAX)}", in_range)
    check(f"{g['id']} polarity preserved", polarity_ok)

# Ratio preservation above the anti-garbage ceiling (the catalog itself sits
# below it and passes VERBATIM — this guards a future mis-authored entry).
_raw = [-8.8e12, -9.9e13, -7.7e11, -999]
_norm = gc.normalize_glitch_rgba(_raw)
_raw_ratio = _raw[0] / _raw[1]
_norm_ratio = _norm[0] / _norm[1] if _norm[1] else 0
check("proportional scaling keeps ratios above the ceiling", abs(_raw_ratio - _norm_ratio) < 0.01,
      f"raw {_raw_ratio:.4f} vs norm {_norm_ratio:.4f}")

# 2026-08-13 pattern semantics: authored VERBATIM inside a defensive 0..15
# bound (the owner's proven payload 1 is authored at 3 — the old fold-to-2
# would destroy it); junk and negatives fold to 0.
check("pattern: -8 -> 0", gc.clamp_glitch_pattern(-8) == 0)
check("pattern: 3 -> 3 (the proven payload-1 layout survives)", gc.clamp_glitch_pattern(3) == 3)
check("pattern: 10 -> 10 (verbatim inside the defensive bound)", gc.clamp_glitch_pattern(10) == 10)
check("pattern: 1 -> 1", gc.clamp_glitch_pattern(1) == 1)
check("pattern: 16 -> 0 (defensive bound)", gc.clamp_glitch_pattern(16) == 0)
check("pattern: garbage -> 0", gc.clamp_glitch_pattern("x") == 0)
# 2026-08-13 variation semantics: authored VERBATIM (5 and 8 are the proven
# payloads' values — the old always-0.0 fold is retired); junk folds to 0.0.
check("variation: 5 -> 5.0 verbatim", gc.normalize_glitch_variation(5) == 5.0)
check("variation: 8 -> 8.0 verbatim", gc.normalize_glitch_variation(8) == 8.0)
check("variation: 0 stays 0.0", gc.normalize_glitch_variation(0.0) == 0.0)
check("variation: None -> 0.0", gc.normalize_glitch_variation(None) == 0.0)
check("variation: garbage -> 0.0", gc.normalize_glitch_variation("x") == 0.0)
check("variation: NaN -> 0.0", gc.normalize_glitch_variation(float("nan")) == 0.0)
check("rgba NaN guard", gc.normalize_glitch_rgba([float("nan"), 1, 1, 1]) == [0.0, 0.0, 0.0, 1.0])
check("rgba garbage guard", gc.normalize_glitch_rgba(["a", 1, 1, 1]) == [0.0, 0.0, 0.0, 1.0])
check("rgba short list padded", gc.normalize_glitch_rgba([1, 2]) == [1.0, 2.0, 1.0, 1.0])
check("in-range values untouched", gc.normalize_glitch_rgba([5, 0, 10, -888]) == [5.0, 0.0, 10.0, -888.0])
check("the owner's -1e11 body channel passes VERBATIM (the whole point)",
      gc.normalize_glitch_rgba([-999999888, -99999999999, -777777777, -999])
      == [-999999888.0, -99999999999.0, -777777777.0, -999.0])
check("trigger-scale alpha passes RAW (never folded)",
      gc.normalize_glitch_rgba([1, 1, 1, -999889])[3] == -999889.0)
check("alpha clamped only at the anti-garbage ceiling",
      gc.normalize_glitch_rgba([1, 1, 1, -1e13])[3] == -gc.GLITCH_CHANNEL_MAX)
_folded = gc.normalize_glitch_rgba([9.0e12, 0, 4.5e12, -99999])
check("rgb folded to ceiling keeps hue",
      abs(_folded[0] - gc.GLITCH_CHANNEL_MAX) < 1.0
      and abs(_folded[2] - gc.GLITCH_CHANNEL_MAX * 0.5) < 1.0)

print("[final contract 2026-08-13]  (owner-payload anchored: his two proven screenshots on the post-patch client)")
# The owner's payloads VERBATIM, pinned INDEPENDENTLY of the catalog table —
# one byte of drift (or a resurrected variation/pattern fold: round-1's
# mistake, twice) turns these RED.
OWNER_PAYLOAD_1 = {
    "pattern": 3, "variation": 5.0,
    "body": [-999999888.0, -99999999999.0, -777777777.0, -999.0],
    "markings": [-88888888.0, -77777.0, -6666666.0, -555.0],
    "flank": [68.0, 1.0, 27.0, -888.0],
    "underbelly": [-9500.0, -9500.0, -9000.0, -9999.0],
    "detail1": [-888888888.0, -7777777.0, -999999999.0, -777.0],
    "eyes": [10.1, 1.0, 10.5, 33000.0],
    "male_display": [10.0, -900.0, 10.0, -99999.0],
}
OWNER_PAYLOAD_2 = {
    "pattern": 2, "variation": 8.0,
    "body": [-999999.0, -9999999.0, -9999999.0, -999.0],
    "markings": [-9999999.0, -999999.0, -9999.0, -999889.0],
    "flank": [25.0, 4.0, 25.0, -99999.0],
    "underbelly": [-999999.0, -99999999.0, -9999999.0, -999.0],
    "detail1": [-999999.0, -999999.0, -999999.0, -999667.0],
    "eyes": [255.0, -999999.0, 60.0, 22000.0],
    "male_display": [-9999998.0, 1987.0, 1019.0, -999.0],
}
for _gid, _spec in (("constelacion", OWNER_PAYLOAD_1), ("supernova", OWNER_PAYLOAD_2)):
    _cmd = gc.build_glitch_command(_gid, "A", "BP_Test_C", "76561199000000003", False)
    _ok = (_cmd is not None and _cmd["pattern"] == _spec["pattern"]
           and _cmd["variation"] == _spec["variation"]
           and all(_cmd[_s] == _spec[_s] for _s in SLOTS))
    check(f"{_gid} == the owner's payload byte-exact through emission (incl variation+pattern)",
          _ok, str(_cmd)[:200])

# Donor-structure conformance: every catalog skin is a channel PERMUTATION of
# one of the two owner payloads — per slot, the RGB value MULTISET and the
# alpha equal the donor's, and variation equals the donor's. Nothing invented
# (the R3 law: donor magnitudes only).
for _g in gc.GLITCH_SKINS + gc.BP_SKINS:
    _pl = _g["payload"]
    _donor = (OWNER_PAYLOAD_1 if _pl["variation"] == 5.0
              else OWNER_PAYLOAD_2 if _pl["variation"] == 8.0 else None)
    if _donor is None:
        check(f"{_g['id']} rides a donor structure", False, f"variation={_pl['variation']}")
        continue
    _ok = all(sorted(float(x) for x in _pl[_s][:3]) == sorted(_donor[_s][:3])
              and float(_pl[_s][3]) == _donor[_s][3] for _s in SLOTS)
    check(f"{_g['id']} is a pure channel permutation of its donor", _ok)

_RETIRED_HEADER = "final contract 2026-08-08 r6 (PI regime) — RETIRED by the 08-11 client patch; history in git 0229477"
_seen_payloads = []
for _g in gc.GLITCH_SKINS + gc.BP_SKINS:
    _cmd = gc.build_glitch_command(_g["id"], "A", "BP_Test_C", "76561199000000003", False)
    _vals = [abs(v) for _s in SLOTS for v in _cmd[_s]]
    check(f"{_g['id']} inside the anti-garbage ceiling", max(_vals) <= gc.GLITCH_CHANNEL_MAX + 1e-6, f"max={max(_vals)}")
    check(f"{_g['id']} emits its authored slots byte-verbatim",
          all(_cmd[_s] == [float(x) for x in _g["payload"][_s]] for _s in SLOTS))
    _sig = tuple(tuple(_cmd[_s]) for _s in SLOTS) + (_cmd["pattern"], _cmd["variation"])
    check(f"{_g['id']} is a distinct design", _sig not in _seen_payloads)
    _seen_payloads.append(_sig)

print("[layout pick]  (player-picked layouts 0..2; None keeps the authored layout - refuse, never fold)")
_CON = gc.GLITCH_BY_ID["constelacion"]["payload"]
for _want in (0, 1, 2):
    _cmd = gc.build_glitch_command("constelacion", "A", "BP_Test_C", "76561199000000003", False,
                                   pattern_override=_want)
    check(f"picked layout {_want} honoured verbatim (slots untouched)",
          _cmd is not None and _cmd["pattern"] == _want
          and all(_cmd[_s] == [float(x) for x in _CON[_s]] for _s in SLOTS))
_cmd = gc.build_glitch_command("constelacion", "A", "BP_Test_C", "76561199000000003", False,
                               pattern_override=None)
check("no pick = the authored layout, even outside 0..2 (constelacion authored 3)",
      _cmd is not None and _cmd["pattern"] == 3)
for _bad in (3, -1, True, False, "2", 1.0):
    _cmd = gc.build_glitch_command("constelacion", "A", "BP_Test_C", "76561199000000003", False,
                                   pattern_override=_bad)
    check(f"out-of-domain pick {_bad!r} REFUSED (never folded)", _cmd is None)
_cmd = gc.build_glitch_command("bp_s_eclipse", "A", "BP_Test_C", "76561199000000003", False,
                               pattern_override=1)
check("picked layout rides ANY skin (eclipse honours a picked layout verbatim)",
      _cmd is not None and _cmd["pattern"] == 1
      and _cmd["body"] == [-999999.0, -9999999.0, -9999999.0, -999.0])

print("[species pattern domain 2026-08-17]  (out-of-table layout = the client drops the WHOLE skin; fold rides positive knowledge)")
# The measured table itself is pinned — a patch-day re-measure edits BOTH the
# module and this pin deliberately, never one of them by drift.
check("measured table pinned (22 species, build 24664709, DT_SkinDataList)",
      gc.SPECIES_PATTERN_COUNTS == {
          "Allosaurus": 4, "Austroraptor": 4, "Beipiaosaurus": 3,
          "Carnotaurus": 4, "Ceratosaurus": 3, "Deinosuchus": 3,
          "Diabloceratops": 3, "Dilophosaurus": 3, "Dryosaurus": 3,
          "Gallimimus": 3, "Herrerasaurus": 5, "Hypsilophodon": 3,
          "Kentrosaurus": 3, "Maiasaura": 3, "Omniraptor": 6,
          "Pachycephalosaurus": 5, "Pteranodon": 3, "Stegosaurus": 4,
          "Tenontosaurus": 3, "Triceratops": 6, "Troodon": 3,
          "Tyrannosaurus": 5,
      }, str(sorted(gc.SPECIES_PATTERN_COUNTS.items())))
_CON_PL = gc.GLITCH_BY_ID["constelacion"]["payload"]
# constelacion (authored layout 3) folds to the species' TOP layout on
# 3-layout species and rides verbatim where layout 3 exists — colour slots
# and variation byte-verbatim in BOTH cases (removing the fold, or folding
# the slots with it, turns these red: the mutant pair for this wave).
for _cls, _want in (("BP_Ceratosaurus_C", 2), ("BP_Pteranodon_C", 2),
                    ("BP_Dilophosaurus_C", 2), ("BP_Deinosuchus_C", 2),
                    ("BP_Troodon_C", 2), ("BP_Tyrannosaurus_C", 3),
                    ("BP_Triceratops_C", 3), ("BP_Herrerasaurus_C", 3),
                    ("BP_Allosaurus_C", 3), ("BP_Omniraptor_C", 3)):
    _cmd = gc.build_glitch_command("constelacion", "A", _cls, "76561199000000003", False)
    check(f"constelacion on {_cls} -> layout {_want}, slots+variation byte-verbatim",
          _cmd is not None and _cmd["pattern"] == _want
          and _cmd["variation"] == 5.0
          and all(_cmd[_s] == [float(x) for x in _CON_PL[_s]] for _s in SLOTS),
          str(_cmd)[:160])
# supernova (authored layout 2) sits inside every measured table: never folded.
for _cls in ("BP_Ceratosaurus_C", "BP_Pteranodon_C", "BP_Tyrannosaurus_C",
             "BP_Troodon_C", "BP_Deinosuchus_C"):
    _cmd = gc.build_glitch_command("supernova", "A", _cls, "76561199000000003", False)
    check(f"supernova on {_cls} keeps layout 2 (inside every table)",
          _cmd is not None and _cmd["pattern"] == 2)
# Every OTHER design ships the identical wire on a 3-layout species and on the
# neutral unknown class — the fold is a no-op for every in-table layout.
for _g in gc.GLITCH_SKINS + gc.BP_SKINS + gc.CREATOR_SKINS:
    if _g["id"] == "constelacion":
        continue
    _a = gc.build_glitch_command(_g["id"], "A", "BP_Ceratosaurus_C", "76561199000000003", False)
    _b = gc.build_glitch_command(_g["id"], "A", "BP_Test_C", "76561199000000003", False)
    check(f"{_g['id']} wire unchanged by the species fold",
          _a is not None and _b is not None and _a["pattern"] == _b["pattern"]
          and all(_a[_s] == _b[_s] for _s in SLOTS))
# Positive-knowledge rule: an UNMEASURED class keeps the authored layout.
check("unknown class keeps authored 3 (fold rides knowledge, never absence)",
      gc.pattern_for_class(3, "BP_Test_C") == 3
      and gc.pattern_for_class(3, "") == 3
      and gc.pattern_for_class(3, None) == 3)
check("bare species name resolves (Ceratosaurus: 3 -> 2)",
      gc.pattern_for_class(3, "Ceratosaurus") == 2)
check("in-table layouts never fold (0/1/2 on Ceratosaurus)",
      all(gc.pattern_for_class(pk, "BP_Ceratosaurus_C") == pk for pk in (0, 1, 2)))
check("deep out-of-table folds to the top layout (10 on Ceratosaurus -> 2, on Triceratops -> 5)",
      gc.pattern_for_class(10, "BP_Ceratosaurus_C") == 2
      and gc.pattern_for_class(10, "BP_Triceratops_C") == 5)
# Player picks (0..2) are inside every measured table — the picked lane is
# untouched by the fold on every class.
_cmd = gc.build_glitch_command("constelacion", "A", "BP_Ceratosaurus_C", "76561199000000003", False,
                               pattern_override=1)
check("picked layout on a 3-layout species rides verbatim (no fold in the picked lane)",
      _cmd is not None and _cmd["pattern"] == 1)

print("[pools]  (owner crate rework 2026-07-22 - CRATE_DROPS model)")
check("two cases", [c["id"] for c in seed_data.CASES] == ["common", "uncommon"])
_EGG_TIERS = {"common", "uncommon", "rare", "epic", "legendary"}
_CATALOG_IDS = sorted(g["id"] for g in gc.GLITCH_SKINS)


def _pool(cid):
    return next(c for c in seed_data.CASES if c["id"] == cid)["pool"]


def _pct(cid, pred):
    # on-site % = the RAW `percent` field (what the site displays), NOT the
    # normalised draw weight; a crate's percents can total != 100 by design.
    return sum(p["percent"] for p in _pool(cid) if pred(p))


def _coin_pct(cid, amt):
    return _pct(cid, lambda p: p["type"] == "coins" and p.get("amount") == amt)


def _skin_pct(cid, key):
    return _pct(cid, lambda p: p["type"] == "skin" and p.get("skin") == key)


def _egg_pct(cid, tier):
    return _pct(cid, lambda p: p["type"] == "egg" and p.get("tier") == tier)


# Every pool is built from CRATE_DROPS: weight == on-site %, sums to 100, and
# every referenced key resolves in its catalog (so server.py's grant/view lane
# can never KeyError on a win).
for case in seed_data.CASES:
    pool = case["pool"]
    tot = sum(p["weight"] for p in pool)
    coins = [p for p in pool if p["type"] == "coins"]
    skins = [p for p in pool if p["type"] == "skin"]
    eggs = [p for p in pool if p["type"] == "egg"]
    glitch = [p for p in pool if p["type"] == "glitch"]
    check(f"{case['id']} draw WEIGHT sums to 100 (normalised; on-site % = raw `percent`)", abs(tot - 100.0) < 1e-6, f"{tot:.4f}")
    check(f"{case['id']} every entry carries a raw `percent` for display", all("percent" in p for p in pool))
    check(f"{case['id']} positive weights", bool(pool) and all(p["weight"] > 0 for p in pool))
    check(f"{case['id']} reward types subset of coins/skin/egg/glitch",
          {p["type"] for p in pool} <= {"coins", "skin", "egg", "glitch"}, str({p["type"] for p in pool}))
    check(f"{case['id']} NO Amberium (vip) in pool - owner ruling",
          not any(p["type"] == "vip" for p in pool))
    check(f"{case['id']} coins are FIXED amounts (not ranges)",
          bool(coins) and all("amount" in p and "min" not in p for p in coins))
    check(f"{case['id']} coins never Epic+ (kept OUT of the feed broadcast)",
          all(p["rarity"] in ("Common", "Uncommon", "Rare") for p in coins),
          str([p["rarity"] for p in coins]))
    check(f"{case['id']} skins reference real SKINS keys (view/grant safe)",
          all(p["skin"] in seed_data.SKINS for p in skins))
    check(f"{case['id']} ONLY the owner's coded skins drop (no generic auto-skins)",
          all(str(p["skin"]).startswith("lin_") for p in skins), str([p["skin"] for p in skins]))
    check(f"{case['id']} egg tiers valid (grant lane safe)",
          all(p["tier"] in _EGG_TIERS for p in eggs))
    check(f"{case['id']} glitch ids resolve in catalog (grant/view lane safe)",
          all(p["glitch"] in gc.GLITCH_BY_ID for p in glitch))
    check(f"{case['id']} glitch entries share one positive weight",
          (not glitch) or (len({round(p["weight"], 9) for p in glitch}) == 1 and all(p["weight"] > 0 for p in glitch)))
    check(f"{case['id']} glitch rarity Legendary (rides Epic+ feed broadcast)",
          all(p["rarity"] == gc.GLITCH_RARITY for p in glitch))

check("prices unchanged", seed_data.CASES[0]["price"] == 10000 and seed_data.CASES[1]["price"] == 25000)
check("both crates cost PrimeMeat", all(c["currency"] == "normal" for c in seed_data.CASES))

# --- exact owner odds (2026-07-22 spec + owner answers) ----------------------
# COMÚN [v4]: his EXACT coin/skin list + eggs KEPT (owner "keep the eggs ... even if
# 100% -> 150%"). RAW-% display: every line shows its typed % VERBATIM, so the on-site
# chances total 105.18% (40.98+30+25+4+1+2.5+1.25+0.25+0.1+0.1) ON PURPOSE.
check("común 1500 PrimeMeat = 40.98% exact (raw display)", abs(_coin_pct("common", 1500) - 40.98) < 0.001, f"{_coin_pct('common',1500):.3f}")
check("común 5000 PrimeMeat = 30% exact", abs(_coin_pct("common", 5000) - 30.0) < 0.001, f"{_coin_pct('common',5000):.3f}")
check("común 25000 PrimeMeat = 25% exact", abs(_coin_pct("common", 25000) - 25.0) < 0.001, f"{_coin_pct('common',25000):.3f}")
check("común common egg = 4% (eggs KEPT)", abs(_egg_pct("common", "common") - 4.0) < 0.001, f"{_egg_pct('common','common'):.3f}")
check("común uncommon egg = 1%", abs(_egg_pct("common", "uncommon") - 1.0) < 0.001)
check("común on-site % total = 105.18 (>100 by owner request)",
      abs(sum(p["percent"] for p in _pool("common")) - 105.18) < 0.01, f"{sum(p['percent'] for p in _pool('common')):.2f}")
check("común Forest = 2.5%", abs(_skin_pct("common", "lin_forest") - 2.5) < 0.001)
check("común Tiger = 1.25%", abs(_skin_pct("common", "lin_tiger") - 1.25) < 0.001)
check("común Albino = 0.25% (rarest)", abs(_skin_pct("common", "lin_albino") - 0.25) < 0.001)
check("común Albino rarer than Tiger", _skin_pct("common", "lin_albino") < _skin_pct("common", "lin_tiger"))
check("común has exactly 2 glitch drops", len([p for p in _pool("common") if p["type"] == "glitch"]) == 2)
check("común has exactly ONE green skin (Forest)",
      [p["skin"] for p in _pool("common") if p["type"] == "skin" and seed_data.SKINS[p["skin"]]["rarity"] == "Uncommon"] == ["lin_forest"])
check("común has NO Legendary skin (Obsidian is premium-only)",
      not any(p["type"] == "skin" and seed_data.SKINS[p["skin"]]["rarity"] == "Legendary" for p in _pool("common")))

# POCO COMÚN: lines sum to exactly 100, so chance == typed %.
check("poco común 20000 PrimeMeat = 40% (owner 2026-07-23: dialled 60 -> 40)",
      abs(_coin_pct("uncommon", 20000) - 40.0) < 0.02, f"{_coin_pct('uncommon',20000):.3f}")
check("poco común coins = 20000 @40% + 5000 @20% (5000 fills the 20% his list was short)",
      sorted(p["amount"] for p in _pool("uncommon") if p["type"] == "coins") == [5000, 20000]
      and abs(_coin_pct("uncommon", 5000) - 20.0) < 0.02, f"5000={_coin_pct('uncommon',5000):.3f}")
check("poco común legendary egg = 2%", abs(_egg_pct("uncommon", "legendary") - 2.0) < 0.02)
check("poco común epic egg = 3%", abs(_egg_pct("uncommon", "epic") - 3.0) < 0.02)
check("poco común rare egg = 3%", abs(_egg_pct("uncommon", "rare") - 3.0) < 0.02)
check("poco común each green skin = 5% (owner: his exact 5% EACH)",
      all(abs(_skin_pct("uncommon", k) - 5.0) < 0.02 for k in ("lin_forest", "lin_rock", "lin_highlands", "lin_woods", "lin_southplains")))
check("poco común green group = 25% (five x 5%)",
      abs(_pct("uncommon", lambda p: p["type"] == "skin" and seed_data.SKINS.get(p.get("skin"), {}).get("rarity") == "Uncommon") - 25.0) < 0.05)
check("poco común epic group = 5% (Albino + Tiger)",
      abs((_skin_pct("uncommon", "lin_albino") + _skin_pct("uncommon", "lin_tiger")) - 5.0) < 0.05)
check("poco común Albino rarer than Tiger (owner: keep Albino rarer)",
      _skin_pct("uncommon", "lin_albino") < _skin_pct("uncommon", "lin_tiger"))
check("poco común Obsidian (Legendary) = 1%", abs(_skin_pct("uncommon", "lin_obsidian") - 1.0) < 0.02)
check("poco común glitch family = 1% (shared across all 9)",
      abs(_pct("uncommon", lambda p: p["type"] == "glitch") - 1.0) < 0.02)
check("poco común ALL catalog glitch skins present (family split, count follows catalog)",
      sorted(p["glitch"] for p in _pool("uncommon") if p["type"] == "glitch") == _CATALOG_IDS)

print("[amount roll]  (mirror of server.py _grant_case_reward range-reward helper)")


def rolled_amount(lo, hi, roll):
    span = hi - lo + 1
    return lo + min(span - 1, int(roll * span))


check("roll 0.0 -> min", rolled_amount(2000, 10000, 0.0) == 2000)
check("roll ~1.0 -> max", rolled_amount(2000, 10000, 0.9999999999) == 10000)
check("roll 0.5 -> midpoint", abs(rolled_amount(2000, 10000, 0.5) - 6000) <= 1)
_oob = 0
for i in range(10001):
    r = i / 10001.0
    v = rolled_amount(2000, 5000, r)
    if not (2000 <= v <= 5000):
        _oob += 1
check("roll formula stays within [lo,hi]", _oob == 0, f"{_oob} out of bounds")
_lo = sum(1 for i in range(10001) if rolled_amount(2000, 10000, i / 10001.0) == 2000)
_hi = sum(1 for i in range(10001) if rolled_amount(2000, 10000, i / 10001.0) == 10000)
check("uniform coverage reaches both edges", _lo > 0 and _hi > 0, f"lo={_lo} hi={_hi}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
