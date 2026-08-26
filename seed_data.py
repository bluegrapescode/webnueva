import glitch_catalog

_DINO_SLUGS = ["trex", "carno", "allo", "trike", "stego", "kentro", "ptera", "raptor", "deino",
               "dilo", "cerato", "troodon", "herrera", "tenonto", "hypsi",
               "pachy", "dryo", "maia", "diablo", "galli", "beipiao", "austro"]
# Caddy serves everything under frontend/public with a year-long immutable cache,
# so a species picture that is REDRAWN under its existing file name stays invisible
# to every browser that already holds the old one. Bumping a slug here changes the
# URL without renaming the file on disk; seed() re-syncs `image` on every backend
# boot, so the store rows and the skin-designer tiles pick the new URL up at the
# next start. Add a slug the first time its art is replaced, then increment.
DINO_ART_VERSION = {
    "austro": 2,   # 2026-08-05: owner's Austroraptor key art replaced the model rip
}


def _art_url(path, slug):
    v = DINO_ART_VERSION.get(slug)
    return f"{path}?v={v}" if v else path


DINO_IMG = {s: _art_url(f"/dinos/{s}.png", s) for s in _DINO_SLUGS}

# Isolated, transparent-background "official model" renders used by the Skin Lab studio preview.
# Served locally from frontend/public/renders (true-alpha PNGs).
DINO_RENDER = {slug: _art_url(f"/renders/{slug}.png", slug) for slug in DINO_IMG.keys()}

# Real 3D models (GLB, CC0 by Quaternius / Poly by Google) for the interactive 3D Skin Studio.
# Mapped by body type to the closest available game-ready model.
_M = lambda n: f"/models/{n}.glb"
DINO_MODEL3D = {
    "trex": _M("trex"), "allo": _M("allo"), "carno": _M("allo"),
    "cerato": _M("cerato"), "deino": _M("trex"),
    "raptor": _M("raptor"), "troodon": _M("raptor"), "austro": _M("raptor"),
    "herrera": _M("raptor"), "dilo": _M("raptor"), "ptera": _M("raptor"),
    "trike": _M("trike"), "diablo": _M("diablo"),
    "stego": _M("stego"), "kentro": _M("stego"),
    "maia": _M("para"), "tenonto": _M("para"), "hypsi": _M("para"), "dryo": _M("para"),
    "pachy": _M("para"), "galli": _M("para"), "beipiao": _M("para"),
}

COIN_NORMAL = "/coins/meat.png"
COIN_VIP = "/coins/amber.png"
LOGO = "/img-mirror/ff5eefbde34b4ff6.png"
HERO_BG = "/img-mirror/3905d022f5d38311.png"

SKIN_IMG = {
    "gold": "/img-mirror/329973a2336e10bd.png",
    "obsidian": "/img-mirror/0f6bd2edbf70d7b1.png",
    "emerald": "/img-mirror/00c8d883640f4622.png",
    "crimson": "/img-mirror/8ed9018e15243705.png",
    "frost": "/img-mirror/0d41ae8d4bc4a3c6.png",
    "toxic": "/img-mirror/bf2aa2524e22c979.png",
    "galaxy": "/img-mirror/94b7dd476ecb6012.png",
}
CASE_IMG = {
    "survivor": "/cases/crate-common.png",
    "vip": "/cases/crate-uncommon.png",
    "skins": "/cases/crate-uncommon.png",
}

# Universal skins — apply to ANY dinosaur. Each carries its own signature color.
# Common/Uncommon/Rare = natural camo themes (forest, jungle, rock, desert, water).
# Epic/Legendary/Mythic/Apex = vivid neon & premium effects.
SKINS = {
    # --- Common (natural camo) ---
    "forest":    {"name": "Forest Camo",     "rarity": "Common",    "color": "#4f6a3a", "theme": "Forest"},
    "bark":      {"name": "Bark Hide",       "rarity": "Common",    "color": "#7a5a34", "theme": "Jungle"},
    "stone":     {"name": "Stone Grey",      "rarity": "Common",    "color": "#8b8f98", "theme": "Rock"},
    "dune":      {"name": "Desert Dune",     "rarity": "Common",    "color": "#cda869", "theme": "Desert"},
    "moss":      {"name": "Mossback",        "rarity": "Common",    "color": "#6f8f4a", "theme": "Forest"},
    # --- Uncommon (natural camo) ---
    "emerald":   {"name": "Emerald Hide",    "rarity": "Uncommon",  "color": "#22c55e", "theme": "Forest"},
    "jungle":    {"name": "Jungle Canopy",   "rarity": "Uncommon",  "color": "#2f9e44", "theme": "Jungle"},
    "sandstone": {"name": "Sandstone",       "rarity": "Uncommon",  "color": "#d8a24a", "theme": "Desert"},
    "slate":     {"name": "Slate Rock",      "rarity": "Uncommon",  "color": "#6b7a8f", "theme": "Rock"},
    "fern":      {"name": "Fern Green",      "rarity": "Uncommon",  "color": "#5bb450", "theme": "Forest"},
    # --- Rare (natural + cool tones) ---
    "frost":     {"name": "Frostbite",       "rarity": "Rare",      "color": "#5cc8ff", "theme": "Tundra"},
    "obsidian":  {"name": "Obsidian Plates", "rarity": "Rare",      "color": "#5566aa", "theme": "Rock"},
    "canyon":    {"name": "Canyon Red",      "rarity": "Rare",      "color": "#c45a32", "theme": "Desert"},
    "ocean":     {"name": "Ocean Depths",    "rarity": "Rare",      "color": "#1aa3b8", "theme": "Water"},
    "amber":     {"name": "Amber Resin",     "rarity": "Rare",      "color": "#e0962a", "theme": "Jungle"},
    # --- Epic (neon) ---
    "toxic":     {"name": "Toxic Venom",     "rarity": "Epic",      "color": "#aaff00", "theme": "Neon"},
    "crimson":   {"name": "Crimson Ember",   "rarity": "Epic",      "color": "#ff3b3b", "theme": "Neon"},
    "neon":      {"name": "Neon Pulse",      "rarity": "Epic",      "color": "#b026ff", "theme": "Neon"},
    "cyber":     {"name": "Cyber Cyan",      "rarity": "Epic",      "color": "#00f0ff", "theme": "Neon"},
    "magma":     {"name": "Magma Core",      "rarity": "Epic",      "color": "#ff6a1a", "theme": "Neon"},
    # --- Legendary (premium fx) ---
    "gold":      {"name": "Golden Scales",   "rarity": "Legendary", "color": "#f5c542", "theme": "Premium"},
    "galaxy":    {"name": "Galaxy Nebula",   "rarity": "Legendary", "color": "#9a5cff", "theme": "Cosmic"},
    "aurora":    {"name": "Aurora Veil",     "rarity": "Legendary", "color": "#2dffb0", "theme": "Cosmic"},
    "inferno":   {"name": "Inferno King",    "rarity": "Legendary", "color": "#ff5400", "theme": "Premium"},
    "prism":     {"name": "Prismatic",       "rarity": "Legendary", "color": "#ff4dd2", "theme": "Premium"},
    # --- Mythic / Apex (ultra-rare) ---
    "void":      {"name": "Void Walker",     "rarity": "Mythic",    "color": "#d12dff", "theme": "Cosmic"},
    "celestial": {"name": "Celestial Apex",  "rarity": "Apex",      "color": "#ff2d55", "theme": "Cosmic"},
    # --- Custom coded skins (exact Skin Studio designs; in-game colours come from
    #     "code", NOT from the single "color" — "color" is only the card tint).
    #     Uncommon set drops in BOTH crates; Epic/Legendary in the premium crate. ---
    "lin_forest":      {"name": "Forest",       "rarity": "Uncommon",  "color": "#1c3e22", "theme": "Forest",  "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjEsImMiOnsiYm9keSI6IjFjM2UyMmZmIiwibWFya2luZ3MiOiIzNzRlMmVmZiIsImZsYW5rIjoiMzY2MjRjZmYiLCJ1bmRlcmJlbGx5IjoiNjA3MDRjZmYiLCJkZXRhaWwxIjoiMDgwODA4ZmYiLCJtYWxlX2Rpc3BsYXkiOiI0MDIzMjBmZiIsImV5ZXMiOiJmZjAwMDBmZiJ9fQ"},
    "lin_rock":        {"name": "Rock",         "rarity": "Uncommon",  "color": "#484944", "theme": "Rock",    "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjEsImMiOnsiYm9keSI6IjQ4NDk0NGZmIiwibWFya2luZ3MiOiIyZTJmMmNmZiIsImZsYW5rIjoiNmM2YzY2ZmYiLCJ1bmRlcmJlbGx5IjoiODQ4MDc2ZmYiLCJkZXRhaWwxIjoiMGUwZTBlZmYiLCJtYWxlX2Rpc3BsYXkiOiI1ZTFlMTZmZiIsImV5ZXMiOiJkY2I5NDZmZiJ9fQ"},
    "lin_highlands":   {"name": "Highlands",    "rarity": "Uncommon",  "color": "#5c653f", "theme": "Forest",  "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6IjVjNjUzZmZmIiwibWFya2luZ3MiOiIzNjNlMjZmZiIsImZsYW5rIjoiNzY3YTU4ZmYiLCJ1bmRlcmJlbGx5IjoiODQ4MDc2ZmYiLCJkZXRhaWwxIjoiMjAxYzE2ZmYiLCJtYWxlX2Rpc3BsYXkiOiJhYTU1MjBmZiIsImV5ZXMiOiJkY2I5NDZmZiJ9fQ"},
    "lin_woods":       {"name": "Woods",        "rarity": "Uncommon",  "color": "#523a24", "theme": "Jungle",  "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6IjUyM2EyNGZmIiwibWFya2luZ3MiOiIzMDIwMTJmZiIsImZsYW5rIjoiNzA1ODNhZmYiLCJ1bmRlcmJlbGx5IjoiOGU3NjUyZmYiLCJkZXRhaWwxIjoiMjAxYzE2ZmYiLCJtYWxlX2Rpc3BsYXkiOiIwZjBjMGFmZiIsImV5ZXMiOiJkNDljM2FmZiJ9fQ"},
    "lin_southplains": {"name": "South Plains", "rarity": "Uncommon",  "color": "#847452", "theme": "Desert",  "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6Ijg0NzQ1MmZmIiwibWFya2luZ3MiOiI1NDQ0MmVmZiIsImZsYW5rIjoiYTQ5NDZlZmYiLCJ1bmRlcmJlbGx5IjoiOGU3NjUyZmYiLCJkZXRhaWwxIjoiMWExNDBlZmYiLCJtYWxlX2Rpc3BsYXkiOiIwZjBjMGFmZiIsImV5ZXMiOiJlMWI5NGVmZiJ9fQ"},
    "lin_albino":      {"name": "Albino",       "rarity": "Epic",      "color": "#e8dadc", "theme": "Premium", "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6ImU4ZGFkY2ZmIiwibWFya2luZ3MiOiJjZGJjYzBmZiIsImZsYW5rIjoiZjJlNGU2ZmYiLCJ1bmRlcmJlbGx5IjoiZmE5ODllZmYiLCJkZXRhaWwxIjoiYWE5OGFhZmYiLCJtYWxlX2Rpc3BsYXkiOiJmZjUwNmVmZiIsImV5ZXMiOiJlMWI5NGVmZiJ9fQ"},
    "lin_tiger":       {"name": "Tiger",        "rarity": "Epic",      "color": "#d67a2a", "theme": "Desert",  "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6ImQ2N2EyYWZmIiwibWFya2luZ3MiOiIxNjEyMTBmZiIsImZsYW5rIjoiZTg5ODQ0ZmYiLCJ1bmRlcmJlbGx5IjoiZjRlNGJlZmYiLCJkZXRhaWwxIjoiMGEwYTBhZmYiLCJtYWxlX2Rpc3BsYXkiOiJhYTQxMWNmZiIsImV5ZXMiOiJlYmI5MmRmZiJ9fQ"},
    "lin_obsidian":    {"name": "Obsidian",     "rarity": "Legendary", "color": "#14181e", "theme": "Premium", "code": "LIN1-eyJ2IjoxLCJkIjoiVHlyYW5ub3NhdXJ1cyIsInAiOjIsImMiOnsiYm9keSI6IjE0MTgxZWZmIiwibWFya2luZ3MiOiIyZDMwMzdmZiIsImZsYW5rIjoiMjAyNDJjZmYiLCJ1bmRlcmJlbGx5IjoiOGM5MTk2ZmYiLCJkZXRhaWwxIjoiMGEwYTBjZmYiLCJtYWxlX2Rpc3BsYXkiOiJmZmM4N2ZmZiIsImV5ZXMiOiJmZmM4MDBmZiJ9fQ"},
}

# ---------------------------------------------------------------------------
# Official The Isle: Evrima skin JSON codes for every universal skin.
# Each skin's signature colour + theme is expanded into the game's 7 colour
# regions (linear 0-1 RGBA) + PatternIndex/SkinVariation, so equipping a skin
# can be pushed to the player's live in-game dino (and copied to the game).
# ---------------------------------------------------------------------------
def _hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)

def _s2l(c):  # sRGB -> linear
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))

def _scale(rgb, f):
    return tuple(max(0.0, min(1.0, c * f)) for c in rgb)

def _rgba(rgb, a=1.0):
    return {"R": round(_s2l(rgb[0]), 6), "G": round(_s2l(rgb[1]), 6), "B": round(_s2l(rgb[2]), 6), "A": a}

_CREAM = (0.93, 0.90, 0.82)
# theme -> (pattern index 0-3, eye hex or None = use vivid body colour)
_THEME_STYLE = {
    "Forest":  (2, "#d9b23a"), "Jungle": (2, "#c98a2a"), "Rock": (3, "#b8c0cc"),
    "Desert":  (1, "#e0c060"), "Tundra": (3, "#bfe8ff"), "Water": (3, "#2fd0e0"),
    "Neon":    (1, None),      "Premium": (3, None),     "Cosmic": (3, None),
}

def _make_evrima(base_hex, theme, idx):
    base = _hex_rgb(base_hex)
    pat, eye_hex = _THEME_STYLE.get(theme, (2, "#d9b23a"))
    flank = _scale(base, 0.78)
    underbelly = _mix(base, _CREAM, 0.7)
    markings = _scale(base, 0.32)
    detail = _scale(base, 0.22)
    if theme in ("Neon", "Premium", "Cosmic"):
        male_display = _scale(base, 1.35)
        eyes = base
    else:
        male_display = _mix(base, _CREAM, 0.35)
        eyes = _hex_rgb(eye_hex) if eye_hex else base
    return {
        "bIsFemale": False,
        "SkinVariation": idx % 9,
        "PatternIndex": pat,
        "MaleDisplayColor": _rgba(male_display),
        "MarkingsColor": _rgba(markings),
        "BodyColor": _rgba(base),
        "FlankColor": _rgba(flank),
        "UnderbellyColor": _rgba(underbelly),
        "Detail1Color": _rgba(detail),
        "EyesColor": _rgba(eyes),
    }

# ---------------------------------------------------------------------------
# Coded skins — universal skins whose exact 7 colour regions come straight from
# a Skin Studio "LIN1-..." share code (each region set independently) instead of
# being auto-derived from one signature colour. Decoding is crash-contained: a
# malformed code NEVER breaks import — the skin falls back to single-colour
# derivation so the backend always boots.
#
#   code JSON: {"v":1,"d":<dino>,"p":<pattern 0-3>,
#               "c":{body,markings,flank,underbelly,detail1,male_display,eyes}}
#               with each region an RRGGBBAA sRGB hex string.
#
# A coded skin gets BOTH:
#   • "evrima" — 7 regions as LINEAR RGBA (same shape _make_evrima emits) for web
#                display / the Live-Dino card; every existing reader is unchanged.
#   • "srgb"   — 7 regions as sRGB 0-1 + pattern, for the IN-GAME apply lane which
#                sends sRGB and does ONE sRGB->linear decode. (Feeding the already
#                linear "evrima" through that lane would double-decode = far too
#                dark, so the two colour spaces are kept separate.)
# ---------------------------------------------------------------------------
import base64 as _base64
import json as _json
import re as _re
import logging as _logging

_CODE_REGION_TO_EVRIMA = {
    "body": "BodyColor", "flank": "FlankColor", "underbelly": "UnderbellyColor",
    "markings": "MarkingsColor", "detail1": "Detail1Color",
    "male_display": "MaleDisplayColor", "eyes": "EyesColor",
}

def parse_skin_code(code):
    """Decode a 'LIN1-...' skin share code to {'pattern': int, 'c': {region:(r,g,b) sRGB 0-1}}.
    Tolerates the 'LIN1-' prefix, wrapped/whitespaced pastes and missing base64 padding.
    Raises on genuinely bad input so the caller can choose a fallback."""
    raw = code.split("-", 1)[1] if "-" in code else code
    raw = _re.sub(r"[^A-Za-z0-9_+/=-]", "", raw)          # strip whitespace/newlines from wrapped codes
    raw += "=" * (-len(raw) % 4)                          # restore base64 padding
    try:
        data = _json.loads(_base64.urlsafe_b64decode(raw))
    except Exception:
        data = _json.loads(_base64.b64decode(raw))
    regions = {k: _hex_rgb(v[:6]) for k, v in data["c"].items()}   # sRGB 0-1, drop the alpha byte
    return {"pattern": max(0, min(3, int(data.get("p", 0)))), "c": regions}

def _evrima_from_code(parsed):
    ev = {"bIsFemale": False, "SkinVariation": 0, "PatternIndex": parsed["pattern"]}
    for _region, _ekey in _CODE_REGION_TO_EVRIMA.items():
        ev[_ekey] = _rgba(parsed["c"][_region])           # sRGB -> linear (for display)
    return ev

def _srgb_from_code(parsed):
    return {"pattern": parsed["pattern"],
            "regions": {r: [round(x, 6) for x in rgb] for r, rgb in parsed["c"].items()}}

# Attach the Evrima payload to every skin. Priority: explicit "evrima" > "code" > derived.
# Crash-contained: a bad code logs a warning and falls back to single-colour derivation.
for _i, (_k, _v) in enumerate(SKINS.items()):
    if _v.get("evrima"):
        continue
    _code = _v.get("code")
    if _code:
        try:
            _parsed = parse_skin_code(_code)
            _v["evrima"] = _evrima_from_code(_parsed)
            _v["srgb"] = _srgb_from_code(_parsed)
            continue
        except Exception as _err:
            _logging.getLogger("seed_data").warning(
                "skin %s: bad code, using colour fallback (%s)", _k, _err)
    _v["evrima"] = _make_evrima(_v["color"], _v.get("theme", "Forest"), _i)


RARITY_WEIGHT = {"Common": 32, "Uncommon": 18, "Rare": 9, "Epic": 4.5, "Legendary": 1.8, "Mythic": 0.8, "Apex": 0.4}


def _skins(*rarities):
    return [k for k, v in SKINS.items() if v["rarity"] in rarities]


def _c(amount, rarity, weight):
    return {"type": "coins", "amount": amount, "rarity": rarity, "weight": weight}


def _v(amount, rarity, weight):
    return {"type": "vip", "amount": amount, "rarity": rarity, "weight": weight}


def _s(key, weight=None):
    r = SKINS[key]["rarity"]
    return {"type": "skin", "skin": key, "rarity": r, "weight": weight if weight is not None else RARITY_WEIGHT[r]}


def _gl(gid, weight):
    # Rarity comes from the catalog (Legendary) so glitch wins ride the Epic+
    # feed broadcast; the grant lane in server._grant_case_reward stamps the
    # 25-use counter (LIN_GLITCH_USES_PER_WIN) on every win.
    return {"type": "glitch", "glitch": gid, "rarity": glitch_catalog.GLITCH_RARITY, "weight": weight}


# Ids straight from the catalog — never hand-typed (a typo here would KeyError
# the reward view / grant lane on a win).
#
# ★ TWO GATES, MADE TO AGREE (2026-08-18). Crate membership was list
# membership alone -- GLITCH_SKINS in, BP_SKINS/CREATOR_SKINS out -- while
# `crate_eligible()` answered the same question off the skin's own
# `bp_exclusive` flag. Two sources for one rule is how a skin ends up
# exclusive on one surface and droppable on another; the wildcard now reads
# the flag too, so flagging a design is enough to pull it out of the crate
# no matter which list it sits in. Today this filter removes nothing (the
# 2026-08-18 "battlepass only" order MOVED constelacion into BP_SKINS), and
# that is the point: the two can never silently disagree again.
_GLITCH_IDS = [g["id"] for g in glitch_catalog.GLITCH_SKINS
               if glitch_catalog.crate_eligible(g["id"])]


# Only two crates exist. Both pay out in game (Survival) coins — never VIP/Amberium
# (owner ruling 2026-07-14). Contents = PrimeMeat coins + the owner's coded skins
# + collectible Dino Eggs + glitch skins, at the exact odds set in CRATE_DROPS.
#
# ===========================================================================
# >>> OWNER-EDITABLE CRATE CONTENTS  (edit the percents, commit, push) <<<
# ===========================================================================
# Every drop in a crate is ONE (kind, value, percent) line, and that PERCENT is
# EXACTLY the chance shown on the casino page. Each crate is auto-normalised so
# its lines total 100% (if your numbers don't already add up, everything is
# scaled to fit and a warning is logged — it NEVER crashes). Kinds:
#
#   ("coins",  20000, 40)        -> 40%  of 20.000 PrimeMeat (the "normal" currency)
#   ("skin",   "lin_forest", 5)  -> 5%   of that skin        (keys = SKINS dict above)
#   ("egg",    "legendary", 2)   -> 2%   of a Legendary collectible egg
#                                         (tiers: common/uncommon/rare/epic/legendary)
#   ("glitch", "red-void", 0.1)  -> 0.1% of that ONE glitch skin (ids in glitch_catalog)
#   ("glitch", "any", 2)         -> 2%   shared EQUALLY across EVERY crate-listed
#                                         glitch skin (follows the catalog; 10
#                                         since 2026-08-18, when constelacion left
#                                         the crates for the Battle Pass alone)
#
# An unknown skin key / glitch id / egg tier is skipped with a warning (never a
# crash), so a typo can only ever remove ONE line, never brick a crate.
#
# The owner's Skin Studio designs (what "green / epic / legendary" mean here):
#   Green  (Uncommon): lin_forest  lin_rock  lin_highlands  lin_woods  lin_southplains
#   Epic:              lin_albino ("Albino")   lin_tiger ("Tiger")
#   Legendary:         lin_obsidian ("Obsidian")
# ===========================================================================
CRATE_DROPS = {
    # -- Caja Común (10.000 PrimeMeat) — owner spec 2026-07-23 (v4) ------------
    #    His EXACT coin/skin list + eggs KEPT (owner: "keep the eggs dude ... even
    #    if it means changing 100% to like 150%"). With RAW-% display (see
    #    _build_crate_pools) every line shows its typed % VERBATIM, so 1.500 reads
    #    40.98% WITH the eggs present — the lines total 105.18% ON PURPOSE.
    "common": [
        ("coins", 1500,  40.98),                 # his 40.98%
        ("coins", 5000,  30.0),                  # his 30%
        ("coins", 25000, 25.0),                  # his 25%
        ("egg", "common",   4.0),                # eggs KEPT (owner "keep the eggs")
        ("egg", "uncommon", 1.0),
        ("skin",  "lin_forest",       2.5),      # his ONE green skin (Forest)
        ("skin",  "lin_tiger",        1.25),     # "the other epic"
        ("skin",  "lin_albino",       0.25),     # albino — kept the rarest (owner)
        ("glitch", "void-prism-gold", 0.1),      # his glitch of choice #1
        ("glitch", "black-cyan",      0.1),      # his glitch of choice #2
    ],
    # -- Caja Poco Común (25.000 PrimeMeat) — owner spec 2026-07-23 (v2) --------
    #    Owner "just use the list i gave u" -> EVERY number below is EXACTLY his:
    #    20k 40%, the five greens 5% EACH, epic 5% total (Albino rarer), eggs
    #    2/3/3, legendary+glitch 2% total. His listed drops sum to only 80%, so
    #    the missing 20% is a 5.000-PrimeMeat consolation (the ONLY added line)
    #    so the crate totals 100 and every % he typed renders EXACTLY on-site.
    #    To move that 20% elsewhere (amount / eggs / more 20k), edit THIS line.
    "uncommon": [
        ("coins", 20000, 40.0),                  # his "40% chance 20k"
        ("coins", 5000,  20.0),                  # ADDED: the 20% his list was short (adjustable)
        # collectible eggs (his 2 / 3 / 3)
        ("egg", "legendary", 2.0),
        ("egg", "epic",      3.0),
        ("egg", "rare",      3.0),
        # green skins — his 5% EACH of the five
        ("skin", "lin_forest",      5.0),
        ("skin", "lin_rock",        5.0),
        ("skin", "lin_highlands",   5.0),
        ("skin", "lin_woods",       5.0),
        ("skin", "lin_southplains", 5.0),
        # epic skins — his 5% total, Albino kept rarer than Tiger (~1:5)
        ("skin", "lin_albino", 0.83),
        ("skin", "lin_tiger",  4.17),
        # legendary + glitch — his 2% total: Obsidian 1% + the glitch family 1%
        ("skin", "lin_obsidian", 1.0),
        ("glitch", "any", 1.0),
    ],
}


CASES = [
    {
        "id": "common", "name": "Caja Común",
        "description": "Caja de suministros estándar — PrimeMeat (1.500 / 5.000 / 25.000), huevos coleccionables, una skin verde (Forest), las skins épicas Albino y Tiger, y una pequeña probabilidad de skins glitch.",
        "image": CASE_IMG["survivor"], "price": 10000, "currency": "normal",
        "pool": [],   # built from CRATE_DROPS["common"] by _build_crate_pools() below
    },
    {
        "id": "uncommon", "name": "Caja Poco Común",
        "description": "Caja de suministros premium — 40% de probabilidad de 20.000 PrimeMeat, huevos coleccionables (raro / épico / legendario), las cinco skins verdes, las épicas Albino y Tiger, la legendaria Obsidian y skins glitch.",
        "image": CASE_IMG["skins"], "price": 25000, "currency": "normal",
        "pool": [],   # built from CRATE_DROPS["uncommon"] by _build_crate_pools() below
    },
]


def _fmt_growth(mins):
    h, m = divmod(int(mins), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


# Official The Isle: Evrima vanilla (1x) grow times, in minutes. Non-Evrima species use size-based analogs.
GROWTH_MINUTES = {
    "hypsi": 110, "troodon": 190, "beipiao": 220, "galli": 270, "maia": 325,
    "cerato": 360, "pachy": 360, "tenonto": 360, "herrera": 360, "raptor": 460,
    "trike": 780, "stego": 1383, "kentro": 900, "trex": 2133,
    "dryo": 130, "ptera": 150, "dilo": 300, "carno": 360, "allo": 420,
    "diablo": 480, "deino": 600,
    # Austroraptor is deliberately ABSENT and falls back to the 360 default.
    # Its four growth stage times live in the native class defaults inside the
    # server exe, not in the cooked assets, so there is nothing to read them out
    # of offline. The stage-time properties were located (character-class
    # offsets 0x1E70/0x1E74/0x1E78/0x1E7C) and all 27 species constructors were
    # dumped with their exact stage tables, but the class -> constructor mapping
    # was never proven, so no number is asserted here rather than guessing one
    # that would then be shown to players as fact. Settle it by timing a real
    # Austroraptor in game, or by proving that mapping.
    # NOTE several existing rows above (cerato/pachy/tenonto/herrera/carno) are
    # also exactly 360, i.e. they are this same fallback, not measured values.
}


def dino(slug, name, dtype, diet, rarity, desc, speed, health, weight, damage, growth, abilities, status="Available", featured=False):
    gm = GROWTH_MINUTES.get(slug, 360)
    return {
        "slug": slug, "name": name, "type": dtype, "diet": diet, "rarity": rarity,
        "description": desc, "image": DINO_IMG[slug], "render": DINO_RENDER.get(slug), "model3d": DINO_MODEL3D.get(slug),
        "growth_minutes": gm,
        "stats": {"speed": speed, "health": health, "weight": weight, "damage": damage, "growth_time": _fmt_growth(gm)},
        "abilities": abilities, "status": status, "featured": featured,
    }


DINOSAURS = [
    dino("trex", "Tyrannosaurus Rex", "Carnivore", "Pure Carnivore", "Apex",
         "The undisputed apex predator of The Isle. Immense bite force and devastating presence dominate every biome.",
         62, 100, 13800, 95, "4h 30m",
         ["Bone Crushing Bite", "Intimidation Roar", "Bleed", "Bone Break"], featured=True),
    dino("carno", "Carnotaurus", "Carnivore", "Pure Carnivore", "Rare",
         "A blistering-fast pursuit predator. Built for the chase with powerful horns and relentless stamina.",
         88, 64, 2400, 60, "2h 45m",
         ["Sprint Burst", "Horn Charge", "Bleed", "High Stamina"], featured=True),
    dino("allo", "Allosaurus", "Carnivore", "Pure Carnivore", "Uncommon",
         "A balanced and versatile hunter. Excellent endurance makes it the perfect generalist carnivore.",
         70, 78, 3500, 72, "3h 10m",
         ["Slashing Bite", "Endurance", "Pack Hunter", "Bleed"]),
    dino("dilo", "Dilophosaurus", "Carnivore", "Pure Carnivore", "Uncommon",
         "Agile mid-tier predator famed for its iconic crest and unsettling cry. A deadly ambusher.",
         78, 45, 460, 40, "1h 50m",
         ["Venom Spit", "Ambush", "Agility", "Stealth"]),
    dino("raptor", "Omniraptor", "Carnivore", "Carnivore", "Uncommon",
         "An intelligent feathered pack hunter. Lethal in numbers, with unmatched maneuverability.",
         92, 32, 240, 28, "1h 20m",
         ["Pounce", "Pack Coordination", "Latch", "Quick Recovery"]),
    # Austroraptor, added by Isle build 24542870 (2026-08-04).
    # The two columns that are REAL quantities come from the species' own cooked
    # assets, not from a neighbouring raptor: weight 240 is
    # DT_AustroraptorAttributeCurves row 'Weight' -> ATT_Austroraptor_Weight
    # FloatCurves[0] (final key 0.75 -> 240.0), and damage 32 is its adult
    # effective bite (base 40 x 0.8 AttackPower). The other two are this file's
    # own 0-100 display bars: health 34 places its real 350 max health between
    # Omniraptor (32) and Herrerasaurus (38), and speed 88 places its real 1300
    # sprint between Herrerasaurus (86) and Omniraptor (92). Rarity Uncommon
    # matches the rest of the mid-size carnivore band, and rarity is what sets
    # the VIP price.
    # Abilities are the ones the game actually gives it: a pounce/latch with
    # LatchCarryMultiplier 1.6, real swimming (fast swim 900, oxygen 1000),
    # pack values 16/40, and BleedingMultiplier 3.0.
    dino("austro", "Austroraptor", "Carnivore", "Pure Carnivore", "Uncommon",
         "A tall, long-snouted fisher-raptor. Built for the shoreline: it swims properly, "
         "pounces from the shallows and bleeds larger prey out rather than trading bites.",
         88, 34, 240, 32, "1h 20m",
         ["Pounce", "Latch", "Strong Swimmer", "Bleed"]),
    dino("deino", "Deinosuchus", "Carnivore", "Semi-Aquatic", "Rare",
         "A monstrous ambush crocodilian. Master of the water, dragging unsuspecting prey to the depths.",
         44, 88, 6800, 80, "3h 40m",
         ["Death Roll", "Submerge", "Latch", "Ambush"]),
    dino("trike", "Triceratops", "Herbivore", "Pure Herbivore", "Apex",
         "A heavily armored tank. Three horns and a bony frill turn defense into a brutal counter-offense.",
         52, 96, 9300, 70, "4h 00m",
         ["Horn Gore", "Charge", "Frill Defense", "Knockback"], featured=True),
    dino("stego", "Stegosaurus", "Herbivore", "Pure Herbivore", "Uncommon",
         "Iconic plated grazer with a lethal thagomizer tail capable of crippling even apex predators.",
         48, 84, 5400, 68, "3h 30m",
         ["Tail Swipe", "Plate Armor", "Bleed", "Knockback"]),
    dino("kentro", "Kentrosaurus", "Herbivore", "Pure Herbivore", "Uncommon",
         "A smaller, heavily armored stegosaur bristling with sharp defensive spikes along its back, tail and shoulders. Agile and deadly when cornered.",
         58, 60, 1500, 54, "15h 0m",
         ["Spiked Tail", "Shoulder Spikes", "Bleed", "Knockback"]),
    dino("ptera", "Pteranodon", "Carnivore", "Piscivore", "Uncommon",
         "The eyes of the sky. A soaring flyer that scouts the entire island and snatches fish from the water.",
         96, 22, 120, 18, "1h 10m",
         ["Flight", "Aerial Scout", "Dive", "Land & Takeoff"]),
    dino("cerato", "Ceratosaurus", "Carnivore", "Pure Carnivore", "Rare",
         "A horned mid-tier predator with powerful jaws and a taste for ambush. Equally at home near water.",
         72, 70, 2700, 66, "2h 55m",
         ["Nasal Horn Gore", "Bleed", "Semi-Aquatic", "Ambush"]),
    dino("troodon", "Troodon", "Carnivore", "Carnivore", "Rare",
         "A small, hyper-intelligent nocturnal hunter. Uses venom and pack tactics to bring down far larger prey.",
         84, 28, 90, 24, "1h 05m",
         ["Venom Bite", "Night Vision", "Pack Hunter", "Latch"]),
    dino("herrera", "Herrerasaurus", "Carnivore", "Pure Carnivore", "Uncommon",
         "One of the earliest predators. Lean, fast and aggressive, perfect for hit-and-run hunting.",
         86, 38, 350, 36, "1h 30m",
         ["Quick Bite", "Sprint", "Agility", "Bleed"]),
    dino("tenonto", "Tenontosaurus", "Herbivore", "Pure Herbivore", "Uncommon",
         "A sturdy ornithopod with a powerful tail. Capable of defending itself against most lone predators.",
         62, 72, 2200, 48, "2h 40m",
         ["Tail Whip", "Sprint", "Endurance", "Knockback"]),
    dino("hypsi", "Hypsilophodon", "Herbivore", "Pure Herbivore", "Common",
         "A tiny, nimble grazer. Survival depends entirely on speed, stealth and never being seen.",
         90, 14, 40, 8, "0h 45m",
         ["Burst Sprint", "Hide", "Agility", "Keen Senses"]),
    dino("pachy", "Pachycephalosaurus", "Herbivore", "Pure Herbivore", "Uncommon",
         "The dome-headed bruiser. Charges and head-butts deliver staggering knockback to attackers.",
         70, 56, 980, 50, "2h 20m",
         ["Head-Butt Charge", "Knockback", "Stun", "Sprint"]),
    dino("dryo", "Dryosaurus", "Herbivore", "Pure Herbivore", "Common",
         "The smallest and fastest grazer on the island. A blur of motion built purely for escape.",
         95, 12, 35, 6, "0h 40m",
         ["Top Speed", "Evasive Dodge", "Keen Senses", "Hide"]),
    dino("maia", "Maiasaura", "Herbivore", "Pure Herbivore", "Uncommon",
         "A social hadrosaur and devoted parent. Thrives in herds, sharing safety in numbers.",
         64, 74, 3000, 46, "2h 50m",
         ["Tail Slap", "Herd Bond", "Endurance", "Loud Call"]),
    dino("diablo", "Diabloceratops", "Herbivore", "Pure Herbivore", "Rare",
         "A fierce ceratopsian with two devilish frill horns. Smaller than Trike but every bit as deadly.",
         58, 80, 4200, 60, "3h 15m",
         ["Horn Gore", "Charge", "Frill Defense", "Knockback"]),
    dino("galli", "Gallimimus", "Omnivore", "Omnivore", "Common",
         "A speedy ostrich-mimic. Omnivorous and skittish, it relies on blistering speed to stay alive.",
         93, 26, 440, 18, "1h 15m",
         ["Top Speed", "Evasive Dodge", "Forage", "Keen Senses"]),
    dino("beipiao", "Beipiaosaurus", "Omnivore", "Omnivore", "Uncommon",
         "A fuzzy feathered therizinosaur. Omnivore with long claws for foraging and surprisingly capable defense.",
         60, 48, 760, 34, "2h 05m",
         ["Claw Swipe", "Forage", "Threat Display", "Agility"]),
]

# Rarity-balanced BASIC VIP prices for dino purchases (Prime tier = 3x at checkout).
RARITY_VIP_PRICE = {"Apex": 3000, "Rare": 1500, "Uncommon": 800, "Common": 400}


def _dino_store_items():
    items = []
    for d in DINOSAURS:
        items.append({
            "name": f"{d['name']} Slot",
            "description": f"Unlock the {d['name']} ({d['diet']}). {d['description']}",
            "category": "Dinosaurs",
            "price": RARITY_VIP_PRICE.get(d["rarity"], 800),
            "currency": "vip",
            "rarity": d["rarity"],
            "image": DINO_IMG[d["slug"]],
            "dino_slug": d["slug"],
            "featured": d.get("featured", False),
        })
    return items


# Every official Evrima dino is purchasable (Basic/Prime tiers handled at checkout).
DINO_STORE_ITEMS = _dino_store_items()

STORE_ITEMS = [
    {"name": "Golden Scales Skin", "description": "Exclusive shimmering golden scale skin for any carnivore.", "category": "Skins", "price": 150, "currency": "vip", "rarity": "Legendary", "image": DINO_IMG["allo"], "featured": True},
    {"name": "Obsidian Hide Skin", "description": "Dark volcanic skin pattern with ember glow.", "category": "Skins", "price": 90, "currency": "vip", "rarity": "Epic", "image": DINO_IMG["deino"], "featured": False},
    {"name": "Priority Queue Pass", "description": "Skip the line and join the server instantly for 30 days.", "category": "Perks", "price": 50, "currency": "vip", "rarity": "Epic", "image": DINO_IMG["ptera"], "featured": True},
    {"name": "Nest Protection (7d)", "description": "Protect your nest from raids for 7 days.", "category": "Perks", "price": 600, "currency": "normal", "rarity": "Rare", "image": DINO_IMG["stego"], "featured": False},
    {"name": "XP Booster x2 (24h)", "description": "Double your growth & currency gains for 24 hours.", "category": "Boosters", "price": 300, "currency": "normal", "rarity": "Uncommon", "image": DINO_IMG["dilo"], "featured": False},
    {"name": "Uncommon Crate", "description": "Caja de suministros premium — 40% de probabilidad de 20.000 PrimeMeat, huevos coleccionables (raro / épico / legendario), las cinco skins verdes, las épicas Albino y Tiger, la legendaria Obsidian y skins glitch.", "category": "Crates", "price": 25000, "currency": "normal", "rarity": "Rare", "image": CASE_IMG["skins"], "featured": True},
    {"name": "Common Crate", "description": "Caja de suministros estándar — PrimeMeat (1.500 / 5.000 / 25.000), huevos coleccionables, una skin verde (Forest), las skins épicas Albino y Tiger, y una pequeña probabilidad de skins glitch.", "category": "Crates", "price": 10000, "currency": "normal", "rarity": "Uncommon", "image": CASE_IMG["survivor"], "featured": False},
    {"name": "Custom Roar Pack", "description": "Unlock a set of custom vocalization sounds.", "category": "Perks", "price": 70, "currency": "vip", "rarity": "Epic", "image": DINO_IMG["trex"], "featured": False},
]

NEWS = [
    {"title": "¡Llegó la actualización Hordetide!", "category": "Actualización", "body": "El último parche de Evrima trae nuevas mecánicas, cambios de balance y mejor comportamiento de la IA. Inicia sesión para experimentar el sistema de migración renovado.", "image": HERO_BG},
    {"title": "Fin de semana de XP Doble", "category": "Evento", "body": "Gana el doble de moneda normal y crecimiento durante todo el fin de semana. La caza nunca fue tan gratificante.", "image": DINO_IMG["carno"]},
    {"title": "Nuevas Skins VIP disponibles", "category": "Tienda", "body": "Tres skins legendarias acaban de llegar a la tienda. Escamas Doradas, Piel de Obsidiana y más esperan a los supervivientes premium.", "image": DINO_IMG["allo"]},
    {"title": "Mantenimiento del servidor completado", "category": "Aviso", "body": "El mantenimiento programado ha finalizado. Se mejoró el rendimiento y se corrigieron varios exploits.", "image": DINO_IMG["deino"]},
]

EVENTS = [
    {"title": "Duelo Ápice", "description": "Torneo PvP organizado por el staff en el valle central. El ganador se lleva 500 Amberium.", "date_label": "Sáb 21:00 UTC", "type": "PvP"},
    {"title": "La Gran Migración", "description": "Los herbívoros se unen en un evento de migración protegida a través del mapa. Sobrevivan juntos.", "date_label": "Dom 18:00 UTC", "type": "Community"},
    {"title": "Noche de Caza", "description": "Solo carnívoros. Visibilidad reducida, recompensas aumentadas. Caza o serás cazado.", "date_label": "Vie 22:00 UTC", "type": "PvE"},
]


# ---------------------------------------------------------------------------
# Build the crate pools from the owner-editable CRATE_DROPS spec above. Each
# (kind, value, percent) line becomes a pool entry carrying BOTH a raw `percent`
# (the typed value, shown on-site VERBATIM by server._case_public — a crate's
# percents may total != 100 by owner design) AND a normalised `weight` (the same
# values scaled to sum 100, which drives the weighted-random draw so exactly one
# reward is picked, proportional to the typed values).
#
# Crash-contained on THREE levels so a bad edit can never brick the import:
#   * per line   - an unknown skin key / glitch id / egg tier, or a malformed
#                  tuple, is skipped with a warning (the rest of the crate builds);
#   * per crate  - any other failure leaves that crate's pool empty + logs;
#   * coin rarity is capped at "Rare" so a frequent coin drop never triggers the
#     Epic+ unboxing feed broadcast (reserved for skins / eggs / glitch).
# ---------------------------------------------------------------------------
_EGG_TIERS = ("common", "uncommon", "rare", "epic", "legendary")


def _coin_rarity(amount):
    # Colour tier only; never Epic+, so coins stay OUT of the Epic+ feed broadcast.
    if amount >= 10000:
        return "Rare"
    if amount >= 2500:
        return "Uncommon"
    return "Common"


def _build_crate_pools():
    _log = _logging.getLogger("seed_data")
    _by_id = {c["id"]: c for c in CASES}
    for _cid, _lines in CRATE_DROPS.items():
        _case = _by_id.get(_cid)
        if _case is None:
            _log.warning("CRATE_DROPS: unknown crate id %r ignored", _cid)
            continue
        try:
            entries = []
            for _line in _lines:
                try:
                    _kind, _value, _pct = _line
                    _pct = max(0.0, float(_pct))
                    if _pct <= 0:
                        continue
                    if _kind == "coins":
                        _amt = int(_value)
                        entries.append(_c(_amt, _coin_rarity(_amt), _pct))
                    elif _kind == "egg":
                        if _value not in _EGG_TIERS:
                            _log.warning("crate %s: unknown egg tier %r skipped", _cid, _value)
                            continue
                        entries.append({"type": "egg", "tier": _value,
                                        "rarity": str(_value).capitalize(), "weight": _pct})
                    elif _kind == "skin":
                        if _value not in SKINS:
                            _log.warning("crate %s: unknown skin key %r skipped", _cid, _value)
                            continue
                        entries.append(_s(_value, _pct))
                    elif _kind == "glitch":
                        if _value == "any":
                            _ids = _GLITCH_IDS or []
                            _n = len(_ids)
                            if _n:
                                for _gid in _ids:
                                    entries.append(_gl(_gid, _pct / _n))
                        elif glitch_catalog.crate_eligible(_value):
                            # crate_eligible, not `in GLITCH_BY_ID`: that map also
                            # carries the Battle Pass exclusives, which must never
                            # be reachable from a crate line (see glitch_catalog
                            # BP_SKINS). The "any" wildcard above is already safe --
                            # _GLITCH_IDS is built from GLITCH_SKINS alone.
                            entries.append(_gl(_value, _pct))
                        else:
                            _log.warning("crate %s: unknown glitch id %r skipped", _cid, _value)
                    else:
                        _log.warning("crate %s: unknown drop kind %r skipped", _cid, _kind)
                except Exception as _line_err:
                    _log.warning("crate %s: bad drop line %r skipped (%s)", _cid, _line, _line_err)
            _tot = sum(e["weight"] for e in entries)
            if _tot <= 0:
                _log.warning("crate %s: no valid drops - pool left empty", _cid)
                _case["pool"] = []
                continue
            # RAW-% DISPLAY: each line's on-site odds are its typed percent VERBATIM
            # (the `percent` field, read by server._case_public), so a crate's lines
            # may total != 100 ON PURPOSE (owner 2026-07-23: "keep the eggs ... even
            # if it means changing 100% to like 150%"). The weighted-random DRAW still
            # uses a normalised `weight` (a proper distribution that sums to 100) so
            # exactly ONE reward is picked, proportional to the typed values.
            for e in entries:
                e["percent"] = round(e["weight"], 4)   # raw typed % -> shown verbatim on-site
            _scale = 100.0 / _tot
            for e in entries:
                e["weight"] = e["weight"] * _scale     # normalised weight -> drives the draw
            _case["pool"] = entries
        except Exception as _err:
            _log.warning("crate %s: CRATE_DROPS build failed, pool left empty (%s)", _cid, _err)
            _case["pool"] = []


_build_crate_pools()


# ---------------------------------------------------------------------------
# Dinosaur population system (Evrima-style per-server species caps).
# ---------------------------------------------------------------------------
POP_CAP = {
    "trex": 16, "allo": 24, "cerato": 40, "carno": 40, "dilo": 40, "raptor": 60,
    "deino": 80, "herrera": 32, "troodon": 60,
    # Austroraptor: the mid-size carnivore band every comparable predator here
    # uses (cerato/carno/dilo 40). This is a server policy number, not a game
    # one - the game defines no population cap.
    "austro": 40,
    "trike": 32, "stego": 40, "kentro": 40, "diablo": 32, "tenonto": 40, "pachy": 40, "maia": 60,
    "hypsi": 120, "dryo": 120, "beipiao": 80, "galli": 120, "ptera": 160,
}
# Apex species that are inherently population-limited.
POP_APEX = {"trex", "allo", "spino", "deino", "trike"}

POP_SERVERS = [
    {"id": "AU1", "label": "AU #1"}, {"id": "EU1", "label": "EU#1"}, {"id": "EU2", "label": "EU#2"},
    {"id": "NA1", "label": "NA #1"}, {"id": "NA2", "label": "NA #2"}, {"id": "NA3", "label": "NA #3"},
]
