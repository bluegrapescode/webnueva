# -*- coding: utf-8 -*-
"""Curated glitch skin catalog + payload guard for La Isla Nublar crate rewards.

FINAL CONTRACT (2026-08-13, owner-payload anchored — supersedes the 08-08 r6
PI regime; era ledger law: every render verdict is per engine/client build):
  * THE WHOLE CATALOG IS BUILT FROM THE OWNER'S TWO PROVEN PAYLOADS. On the
    post-patch client (game build 24664709 wave, client patched 2026-08-11)
    the owner photographed two skins actually shader-glitching in game and
    handed over their exact CustomizerData. Those two payloads are the ONLY
    render-proven shapes on the current client:
    - "constelacion" == his payload 1 VERBATIM (pattern 3, variation 5,
      channels to -1e11, alpha signature -999/-555/-888/-9999/-777/33000/-99999);
    - "supernova" == his payload 2 VERBATIM (pattern 2, variation 8,
      channels to -1e8, alphas -999/-999889/-99999/-999/-999667/22000/-999).
  * Every other skin is a CHANNEL PERMUTATION of one of those two donor
    structures: per slot, the donor's three colour values are re-ordered to
    carry that skin's named hue (the R3 method — donor magnitudes only,
    nothing invented). Alphas, variation and the donor's whole value set ride
    VERBATIM; each skin keeps its own authored pattern (identity).
  * EMISSION IS VERBATIM. The 08-05 folds (variation->0.0, pattern->0..2,
    the +-999999 rescale) are RETIRED: the 08-11 client patch killed the
    +-999-rail product they protected ("skins are broken... glitch skins",
    2026-08-13) while the owner's raw payloads render. Authored variation and
    pattern now emit as authored; magnitudes pass raw below the anti-garbage
    ceiling. The retired regimes live in git history (25ec05c, fdb325e,
    0229477) — per the era-ledger law, never re-emit them without owner eyes
    on the then-current client.
  * The engine's unset-sentinel family (channels <= -900000 after a restart)
    OVERLAPS these payloads by value. That is fine BY DESIGN: persistence
    rides the stored-recipe lane (skin_last_applied replay + revive-at-
    redeem), never snapshot readbacks. Park/copy/viewer lanes keep their
    poison refusals — a worn catalog skin showing no colour strip on the
    vault page, refusing "Copiar mi skin actual", and rendering as the stock
    look in the 3D viewer are all correct outcomes (the copy refusal also
    stops paid designs being cloned into the free editor).
  * A glitch card is a NAME + COLOUR PROXIMITY, never a picture (fleet order
    2026-08-11). `preview` is retired to "" and design_proximity() feeds the
    card strip; the render files are gone from the repo and the served root.
Fold at EMISSION, never at storage - the table below stays canonical.
The NaN / non-numeric / short-list padding guards below are defensive only and
stay: every caller feeds them the hardcoded table above, never user input.

Glitch commands are written RAW (no sRGB->linear decode, no eps jitter,
no color_space key) — the mod ignores color_space and consumes values as-is;
the sRGB decode in SkinPayloadIn.to_command is a normal-lane-only transform
that would corrupt signed glitch magnitudes.
"""

# RETAINED FOR IMPORT COMPATIBILITY ONLY - no longer an emission bound.
GLITCH_VALUE_CAP = 999.0

# Anti-garbage ceiling only (2026-08-13: raised 999999 -> 1e12 so the owner's
# proven -1e11 channels emit VERBATIM). The wire structs accept +-1e15; this
# bound exists so a mis-authored entry can never emit a JSON-hostile value.
GLITCH_CHANNEL_MAX = 1.0e12

# HISTORICAL (08-08 era): the PI catalog's alpha rails. No longer an authoring
# rule — the 08-11 client patch killed the +-999-rail product; the current
# authoring source is the owner's two proven payloads above.
GLITCH_ALPHA_RAILS = (-999.0, -777.0, -555.0, 999.0)

# Won glitch skins broadcast to the feed (Epic+ rule in _grant_case_reward).
GLITCH_RARITY = "Legendary"


def _p(pattern, body, markings, flank, underbelly, detail1, eyes, male_display,
       *, variation=0.0):
    return {
        "pattern": pattern, "variation": variation,
        "body": body, "markings": markings, "flank": flank,
        "underbelly": underbelly, "detail1": detail1, "eyes": eyes,
        "male_display": male_display,
    }


GLITCH_SKINS = [
    # void-prism-base ("el glitch original") REMOVED by owner order
    # 2026-08-08 ("remove ... red void prism the original one"); granted rows
    # were deleted from db.reward_skins (backup rmskins_20260808).
    {
        "id": "void-prism-gold", "name": "Void Prism · Gold",
        "subtitle": "Destello solar — amarillo fundido",
        "accent_hex": "#d6b257", "category": "prism",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family RG (r=v1 g=v2 per slot).
        "payload": _p(2,
                      [-777777777.0, -999999888.0, -99999999999.0, -999.0],
                      [-77777.0, -6666666.0, -88888888.0, -555.0],
                      [68.0, 27.0, 1.0, -888.0],
                      [-9000.0, -9500.0, -9500.0, -9999.0],
                      [-7777777.0, -888888888.0, -999999999.0, -777.0],
                      [10.5, 10.1, 1.0, 33000.0],
                      [10.0, 10.0, -900.0, -99999.0], variation=5.0),
    },
    {
        "id": "void-prism-blue", "name": "Void Prism · Blue",
        "subtitle": "Vetas de cobalto frío, brillo profundo en el flanco",
        "accent_hex": "#5794d6", "category": "prism",
        "preview": "",
        # 2026-08-13: donor B (payload 2), family RB (b=v1 r=v2 per slot).
        "payload": _p(2,
                      [-9999999.0, -9999999.0, -999999.0, -999.0],
                      [-999999.0, -9999999.0, -9999.0, -999889.0],
                      [25.0, 4.0, 25.0, -99999.0],
                      [-9999999.0, -99999999.0, -999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [60.0, -999999.0, 255.0, 22000.0],
                      [1019.0, -9999998.0, 1987.0, -999.0], variation=8.0),
    },
    {
        "id": "void-prism-green", "name": "Void Prism · Green",
        "subtitle": "Pulso verde tóxico sobre negro fósil",
        "accent_hex": "#85d657", "category": "prism",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family G (g=v1 per slot).
        "payload": _p(2,
                      [-999999888.0, -777777777.0, -99999999999.0, -999.0],
                      [-6666666.0, -77777.0, -88888888.0, -555.0],
                      [27.0, 68.0, 1.0, -888.0],
                      [-9500.0, -9000.0, -9500.0, -9999.0],
                      [-888888888.0, -7777777.0, -999999999.0, -777.0],
                      [10.1, 10.5, 1.0, 33000.0],
                      [10.0, 10.0, -900.0, -99999.0], variation=5.0),
    },
    {
        "id": "cobalt-void", "name": "Cobalt Void",
        "subtitle": "Terror de aguas profundas — azul eléctrico saturado",
        "accent_hex": "#3c6cd4", "category": "void",
        "preview": "",
        # 2026-08-13: donor B (payload 2), family B (b=v1 g=v2 per slot).
        "payload": _p(2,
                      [-9999999.0, -9999999.0, -999999.0, -999.0],
                      [-9999999.0, -999999.0, -9999.0, -999889.0],
                      [4.0, 25.0, 25.0, -99999.0],
                      [-99999999.0, -9999999.0, -999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [-999999.0, 60.0, 255.0, 22000.0],
                      [-9999998.0, 1019.0, 1987.0, -999.0], variation=8.0),
    },
    {
        "id": "blue-void", "name": "Blue Void",
        "subtitle": "Cintas de hielo recorriendo el lomo",
        "accent_hex": "#7ec0e8", "category": "void",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family B (b=v1 g=v2 per slot).
        "payload": _p(2,
                      [-99999999999.0, -999999888.0, -777777777.0, -999.0],
                      [-88888888.0, -6666666.0, -77777.0, -555.0],
                      [1.0, 27.0, 68.0, -888.0],
                      [-9500.0, -9500.0, -9000.0, -9999.0],
                      [-999999999.0, -888888888.0, -7777777.0, -777.0],
                      [1.0, 10.1, 10.5, 33000.0],
                      [-900.0, 10.0, 10.0, -99999.0], variation=5.0),
    },
    {
        "id": "red-void", "name": "Red Void",
        "subtitle": "Brotes de calor — carmesí sobre silueta de brea",
        "accent_hex": "#d65757", "category": "void",
        "preview": "",
        # 2026-08-13: donor B (payload 2), family R (r=v1 b=v2 per slot).
        "payload": _p(2,
                      [-999999.0, -9999999.0, -9999999.0, -999.0],
                      [-9999.0, -9999999.0, -999999.0, -999889.0],
                      [25.0, 4.0, 25.0, -99999.0],
                      [-999999.0, -99999999.0, -9999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [255.0, -999999.0, 60.0, 22000.0],
                      [1987.0, -9999998.0, 1019.0, -999.0], variation=8.0),
    },
    {
        "id": "orchid-void", "name": "Orchid Void",
        "subtitle": "Floración violeta suave — pesado en el display",
        "accent_hex": "#c057d6", "category": "void",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family RB (b=v1 r=v2 per slot).
        "payload": _p(0,
                      [-999999888.0, -99999999999.0, -777777777.0, -999.0],
                      [-6666666.0, -88888888.0, -77777.0, -555.0],
                      [27.0, 1.0, 68.0, -888.0],
                      [-9500.0, -9500.0, -9000.0, -9999.0],
                      [-888888888.0, -999999999.0, -7777777.0, -777.0],
                      [10.1, 1.0, 10.5, 33000.0],
                      [10.0, -900.0, 10.0, -99999.0], variation=5.0),
    },
    {
        "id": "black-cyan", "name": "Black Cyan",
        "subtitle": "Explorador sutil — cuerpo de tinta con hilos cian",
        "accent_hex": "#57d6c8", "category": "solid",
        "preview": "",
        # 2026-08-13: donor B (payload 2), family GB (g=v1 b=v2 per slot).
        "payload": _p(0,
                      [-9999999.0, -999999.0, -9999999.0, -999.0],
                      [-9999999.0, -9999.0, -999999.0, -999889.0],
                      [4.0, 25.0, 25.0, -99999.0],
                      [-99999999.0, -999999.0, -9999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [-999999.0, 255.0, 60.0, 22000.0],
                      [-9999998.0, 1987.0, 1019.0, -999.0], variation=8.0),
    },
    {
        # 2026-08-08 owner order ("just add it"); 2026-08-13 re-authored onto
        # the proven donor structure, scarlet channels leading.
        "id": "the-devil", "name": "The Devil",
        "subtitle": "Garra escarlata — rojo infernal sobre negro",
        "accent_hex": "#e04b3a", "category": "solid",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family R (r=v1 b=v2 per slot).
        "payload": _p(0,
                      [-777777777.0, -99999999999.0, -999999888.0, -999.0],
                      [-77777.0, -88888888.0, -6666666.0, -555.0],
                      [68.0, 1.0, 27.0, -888.0],
                      [-9000.0, -9500.0, -9500.0, -9999.0],
                      [-7777777.0, -999999999.0, -888888888.0, -777.0],
                      [10.5, 1.0, 10.1, 33000.0],
                      [10.0, -900.0, 10.0, -99999.0], variation=5.0),
    },
    {
        # 2026-08-13 owner order: his payload 2 BYTE-VERBATIM — the render-
        # proven reference for donor B (his screenshot: red/blue/white bursts
        # on a black Tyrannosaurus). 2026-08-16 (owner order, his CustomizerData
        # re-sent verbatim): this is the SEASON LEADERBOARD 1º-place prize
        # (leaderboards.PRIZE_SKIN_BY_RANK) and the premium level-100 apex
        # rider (battle_pass.APEX_BONUS_SKIN); it left the level-20 cell.
        "id": "supernova", "name": "Supernova",
        "subtitle": "Estallido estelar — rojo, azul y blanco sobre negro",
        "accent_hex": "#e0566e", "category": "cosmos",
        "preview": "",
        "payload": _p(2,
                      [-999999.0, -9999999.0, -9999999.0, -999.0],
                      [-9999999.0, -999999.0, -9999.0, -999889.0],
                      [25.0, 4.0, 25.0, -99999.0],
                      [-999999.0, -99999999.0, -9999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [255.0, -999999.0, 60.0, 22000.0],
                      [-9999998.0, 1987.0, 1019.0, -999.0], variation=8.0),
    },
]

# ---------------------------------------------------------------------------
# Battle Pass exclusives (season skins, NEVER crate drops).
#
# ★ THEY LIVE IN THEIR OWN LIST ON PURPOSE. seed_data.py:269 builds the crate
# id pool as `[g["id"] for g in GLITCH_SKINS]` and CRATE_DROPS carries a
# ("glitch", "any", 1.0) wildcard on the Uncommon Crate that shares its weight
# across EVERY id in that list -- appending Battle Pass skins to GLITCH_SKINS
# would have silently put them in a 25.000 PrimeMeat crate the day they
# shipped. GLITCH_BY_ID still carries them, so build_glitch_command(), the
# reward view and the /api/rewards/skins apply lane all work on them
# unchanged; only the crate pool cannot see them.
#
# ★ The 2026-08-13 additions (constelacion / supernova) are DELIBERATELY in
# GLITCH_SKINS: the owner ordered them into "battle pass, crates, etc", so
# both were crate-droppable AND granted by Battle Pass cells — the
# bp_exclusive flag marks exclusivity per skin, not per grant surface.
#
# 2026-08-18 owner order ("constelacion for battlepass only") ENDED that
# for constelacion: it now lives in THIS list and is won on the pass and
# nowhere else. supernova stays dual-surface (crate + the level-100 apex
# rider) AND is the 1/2/3 prize on both leaderboards -- one word in
# GLITCH_SKINS/BP_SKINS moves either half.
BP_SKINS = [
    # bp_s_alba ("Cazador del Alba") REMOVED by owner order 2026-08-08
    # (near-duplicate of the-devil); its regular level-35 cell is retired
    # (battle_pass.REG_RETIRED_LEVELS) and granted rows were deleted.
    # bp_s_jungla ("Sombra de Jungla") REMOVED by owner order 2026-08-08; its
    # regular level-65 cell is retired (battle_pass.REG_RETIRED_LEVELS) and
    # granted rows were deleted (backup rmskins_20260808).
    # bp_s_ambar ("Ambar Fosil") REMOVED by owner order 2026-08-08; its
    # regular level-95 cell is retired (battle_pass.REG_RETIRED_LEVELS) and
    # granted rows were deleted.
    # bp_s_sol ("Sol de Medianoche") REMOVED by owner order 2026-08-08: after
    # the catalog rebuilds its look duplicated another skin. Its premium
    # level-20 cell was retired and is re-opened 2026-08-13 for "supernova"
    # (a GLITCH_SKINS member — see the note above).
    {
        "id": "bp_s_vacio", "name": "Vacío Primigenio",
        "subtitle": "Exclusiva del Pase de Batalla",
        "accent_hex": "#1f8f9c", "category": "battlepass",
        "bp_exclusive": True, "bp_rarity": "Legendary",
        "preview": "",
        # 2026-08-13: donor A (payload 1), family GB (g=v1 b=v2 per slot).
        "payload": _p(1,
                      [-99999999999.0, -777777777.0, -999999888.0, -999.0],
                      [-88888888.0, -77777.0, -6666666.0, -555.0],
                      [1.0, 68.0, 27.0, -888.0],
                      [-9500.0, -9000.0, -9500.0, -9999.0],
                      [-999999999.0, -7777777.0, -888888888.0, -777.0],
                      [1.0, 10.5, 10.1, 33000.0],
                      [-900.0, 10.0, 10.0, -99999.0], variation=5.0),
    },
    {
        # Added for the v2 row model (2026-08-07): the premium row carries THREE
        # legendary cells (20/55/90) and Corona del Rey is reserved for the
        # level-100 Tyrannosaurus, so a seventh exclusive keeps every cell
        # granting a DISTINCT skin instead of one cell paying a duplicate.
        # OWED: the owner has not named this one; "Eclipse de Sangre" is a
        # placeholder in the same Spanish set.
        "id": "bp_s_eclipse", "name": "Eclipse de Sangre",
        "subtitle": "Exclusiva del Pase de Batalla",
        "accent_hex": "#b4272e", "category": "battlepass",
        "bp_exclusive": True, "bp_rarity": "Legendary",
        "preview": "",
        # 2026-08-13: donor B (payload 2), family RG (r=v1 g=v2 per slot).
        "payload": _p(0,
                      [-999999.0, -9999999.0, -9999999.0, -999.0],
                      [-9999.0, -999999.0, -9999999.0, -999889.0],
                      [25.0, 25.0, 4.0, -99999.0],
                      [-999999.0, -9999999.0, -99999999.0, -999.0],
                      [-999999.0, -999999.0, -999999.0, -999667.0],
                      [255.0, 60.0, -999999.0, 22000.0],
                      [1987.0, 1019.0, -9999998.0, -999.0], variation=8.0),
    },
    {
        # 2026-08-13 owner order ("lets add these two skins to battle pass,
        # crates, etc"): his payload 1 BYTE-VERBATIM -- the render-proven
        # reference for donor A (his screenshot: pink-white starfield
        # sparkle on black, shot at night). Since the 2026-08-16 swap it is
        # the premium level-20 cell (battle_pass.PRE_SKIN_BY_LEVEL) -- the
        # owner's "add the pink glitter in BP".
        #
        # 2026-08-18 owner order ("constelacion for battlepass only"): MOVED
        # out of GLITCH_SKINS into THIS list, which is what makes "only"
        # true -- crate membership IS the list split (seed_data enumerates
        # GLITCH_SKINS), and `bp_exclusive` pins crate_eligible() False as
        # the second, agreeing gate. The id, name, subtitle, accent,
        # category and payload are BYTE-IDENTICAL to the crate-era entry:
        # nothing about how the skin looks or applies changed, only where
        # it can be won. Copies already granted from a crate keep working
        # untouched -- GLITCH_BY_ID resolves this list too.
        "id": "constelacion", "name": "Constelación",
        "subtitle": "Polvo de estrellas — destellos rosa y blanco sobre negro absoluto",
        "accent_hex": "#e8a8d8", "category": "cosmos",
        "bp_exclusive": True, "bp_rarity": "Legendary",
        "preview": "",
        "payload": _p(3,
                      [-999999888.0, -99999999999.0, -777777777.0, -999.0],
                      [-88888888.0, -77777.0, -6666666.0, -555.0],
                      [68.0, 1.0, 27.0, -888.0],
                      [-9500.0, -9500.0, -9000.0, -9999.0],
                      [-888888888.0, -7777777.0, -999999999.0, -777.0],
                      [10.1, 1.0, 10.5, 33000.0],
                      [10.0, -900.0, 10.0, -99999.0], variation=5.0),
    },
    # bp_s_corona ("Corona del Rey") REMOVED by owner order 2026-08-08; the
    # premium level-100 apex claim carries "supernova" as its skin rider
    # since 2026-08-16 (owner order — see battle_pass.APEX_BONUS_SKIN).
]

BP_SKIN_BY_ID = {g["id"]: g for g in BP_SKINS}

# Crate pools read GLITCH_SKINS (see the BP_SKINS note); everything that
# RESOLVES an id -- build_glitch_command, _reward_view, the apply lane, the
# Battle Pass grant -- reads GLITCH_BY_ID, which carries both families.
# ---------------------------------------------------------------------------
# Creator Program exclusive (2026-08-17, owner order: a glitch skin "only for
# creator system", unlocked at `skin_target` validated referrals).
#
# â SAME ISOLATION AS BP_SKINS: seed_data builds the crate id pool from
# GLITCH_SKINS alone, so this list can never leak into a crate; bp_exclusive
# additionally pins crate_eligible() False, and Battle Pass cells name their
# ids explicitly, so it can never join the pass. The ONLY grant surface is the
# Creator Program milestone in server.py (`_cp_validate_and_reward`).
CREATOR_SKINS = [
    {
        "id": "leyenda-creador", "name": "Leyenda del Creador",
        "subtitle": "Exclusiva del Programa de Creadores â el pico de la manada",
        "accent_hex": "#d4af37", "category": "creator",
        "bp_exclusive": True, "creator_exclusive": True,
        "preview": "",
        # 2026-08-17: donor A (payload 1), family REVERSE (per slot v3,v2,v1 â
        # the one re-ordering no other donor-A skin wears; body differs from all
        # six donor-A entries). Alphas, variation and the donor's whole value
        # set ride VERBATIM (R3 method â donor magnitudes only).
        "payload": _p(1,
                      [-777777777.0, -99999999999.0, -999999888.0, -999.0],
                      [-6666666.0, -77777.0, -88888888.0, -555.0],
                      [27.0, 1.0, 68.0, -888.0],
                      [-9000.0, -9500.0, -9500.0, -9999.0],
                      [-999999999.0, -7777777.0, -888888888.0, -777.0],
                      [10.5, 1.0, 10.1, 33000.0],
                      [10.0, -900.0, 10.0, -99999.0], variation=5.0),
    },
]

CREATOR_SKIN_BY_ID = {g["id"]: g for g in CREATOR_SKINS}

GLITCH_BY_ID = {g["id"]: g for g in (GLITCH_SKINS + BP_SKINS + CREATOR_SKINS)}


def crate_eligible(glitch_id) -> bool:
    """True when a crate may drop this id. Battle Pass exclusives never can --
    they are earned on the pass track and nowhere else."""
    g = GLITCH_BY_ID.get(glitch_id)
    return bool(g) and not g.get("bp_exclusive")


_SLOT_KEYS = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")


def normalize_glitch_variation(value):
    """Emission passes the AUTHORED variation VERBATIM (2026-08-13).

    The 08-05 always-0.0 fold is retired: the owner's two render-proven
    payloads carry variation 5 and 8 on the post-08-11 client, while the
    folded catalog stopped glitching ("skins are broken"). Junk, non-finite
    or ceiling-breaking values fold to 0.0 — defensive only, the curated
    table never carries them."""
    try:
        v = float(0.0 if value is None else value)
    except (TypeError, ValueError):
        return 0.0
    if v != v or _is_inf(v) or abs(v) > GLITCH_CHANNEL_MAX:
        return 0.0
    return v


def clamp_glitch_pattern(value):
    """Emission passes the AUTHORED pattern VERBATIM (2026-08-13).

    The 08-05 fold-to-0..2 is retired with the variation fold (same evidence:
    the owner's proven payload 1 carries pattern 3 and renders). Junk or a
    negative folds to 0; a defensive 0..15 bound stays because a wild index
    on a species with a short pattern table makes the client drop the whole
    skin silently — the picker override lane (0..2) is unchanged and refuses
    rather than folds."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    if v < 0:
        return 0
    if v > 15:
        return 0
    return v


def _is_inf(v):
    """Defensive only - the curated table holds no infinities - but a RAW lane
    must never emit a value json.dumps(allow_nan=False) refuses, which is how
    Starlette renders every response."""
    return v == float("inf") or v == float("-inf")


# Measured per-species pattern-table sizes on build 24664709 (client cook,
# DT_SkinDataList read 2026-08-17 with IsleSkinWeb tools/extract_patterns
# --skindump; positive control passed: 22 rows, Tyrannosaurus 5; every entry
# carries Adult+Juvenile+Hatchling textures, so growth stage never shrinks a
# table). An index AT or BEYOND the species' table size makes the client
# SILENTLY DROP THE WHOLE SKIN (measured fleet law) — the owner burned five
# constelacion uses on a Ceratosaurus (3 layouts) watching exactly that.
# Indexes are 0-based: count 3 = valid layouts 0..2.
# RE-MEASURE ON EVERY PATCH DAY — counts grew on 24542870 and can grow again.
SPECIES_PATTERN_COUNTS = {
    "Allosaurus": 4, "Austroraptor": 4, "Beipiaosaurus": 3, "Carnotaurus": 4,
    "Ceratosaurus": 3, "Deinosuchus": 3, "Diabloceratops": 3,
    "Dilophosaurus": 3, "Dryosaurus": 3, "Gallimimus": 3, "Herrerasaurus": 5,
    "Hypsilophodon": 3, "Kentrosaurus": 3, "Maiasaura": 3, "Omniraptor": 6,
    "Pachycephalosaurus": 5, "Pteranodon": 3, "Stegosaurus": 4,
    "Tenontosaurus": 3, "Triceratops": 6, "Troodon": 3, "Tyrannosaurus": 5,
}


def _species_of(dino_class):
    """'BP_Ceratosaurus_C' -> 'Ceratosaurus' (a bare species name passes
    through unchanged)."""
    s = str(dino_class or "")
    if s.startswith("BP_"):
        s = s[3:]
    if s.endswith("_C"):
        s = s[:-2]
    return s


def pattern_for_class(authored, dino_class):
    """The authored layout, folded INTO the target species' measured pattern
    table when — and only when — the table positively says that index does
    not exist there (fold target = the species' highest layout, the nearest
    one that renders; the colour slots and variation are never touched, so
    the design stays the owner's bytes). An UNKNOWN species keeps the
    authored value untouched: the fold rides positive knowledge, never
    absence — an unmeasured class must not silently repaint a proven design.
    Player picks (0..2) sit inside every measured table and never reach
    this."""
    count = SPECIES_PATTERN_COUNTS.get(_species_of(dino_class))
    if count is None or authored < count:
        return authored
    return count - 1


def normalize_glitch_rgba(values):
    raw = list(values or [])
    while len(raw) < 4:
        raw.append(1.0)
    try:
        r, g, b, a = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 1.0]
    if r != r or g != g or b != b or a != a:  # NaN guard
        return [0.0, 0.0, 0.0, 1.0]
    if _is_inf(r) or _is_inf(g) or _is_inf(b):
        r, g, b = 0.0, 0.0, 0.0
    if _is_inf(a):
        a = 1.0
    # Anti-garbage ceiling only (module docstring): the whole catalog sits
    # below +-1e12 and passes VERBATIM. RGB triples above rescale
    # PROPORTIONALLY - never per-channel - so an over-ceiling hue keeps its
    # ratios; alpha clamps SIGN-PRESERVING on its own and NEVER folds with
    # the colours.
    peak = max(abs(r), abs(g), abs(b))
    if peak > GLITCH_CHANNEL_MAX:
        scale = GLITCH_CHANNEL_MAX / peak
        r, g, b = r * scale, g * scale, b * scale
    if a > GLITCH_CHANNEL_MAX:
        a = GLITCH_CHANNEL_MAX
    elif a < -GLITCH_CHANNEL_MAX:
        a = -GLITCH_CHANNEL_MAX
    return [r, g, b, a]


def build_glitch_command(glitch_id, actor_name, dino_class, steam_id, female,
                         pattern_override=None):
    """Engine-guarded skin command for a curated glitch skin. `female` MUST be
    the dino's live sex from the snapshot (the mod WRITES this field — passing
    a stale/default value flips the dino's sex on apply).

    `pattern_override` is the player's picked layout (0..2). The engine's
    pattern index decides WHICH body regions each colour slot paints, so one
    design reads as several looks per species. None keeps the authored layout
    (which may sit outside 0..2 — constelacion is authored at 3, render-proven)
    folded into the TARGET species' measured pattern table (2026-08-17:
    an out-of-table index makes the client silently drop the WHOLE skin, so
    layout 3 on a 3-layout species ships as layout 2 instead of shipping as
    nothing). An out-of-domain pick is REFUSED (None), never folded — a
    player must not receive a layout nobody chose."""
    g = GLITCH_BY_ID.get(glitch_id)
    if not g:
        return None
    p = g["payload"]
    if pattern_override is None:
        applied_pattern = pattern_for_class(
            clamp_glitch_pattern(p["pattern"]), dino_class)
    else:
        if (not isinstance(pattern_override, int)
                or isinstance(pattern_override, bool)
                or not 0 <= pattern_override <= 2):
            return None
        applied_pattern = pattern_override
    cmd = {
        "actor_name": actor_name, "class": dino_class, "steamid": steam_id,
        "female": bool(female),
        "variation": normalize_glitch_variation(p.get("variation")),
        "pattern": applied_pattern,
        "skin_code": "",
    }
    for k in _SLOT_KEYS:
        cmd[k] = normalize_glitch_rgba(p[k])
    return cmd


def _prox_hex(rgb):
    """One slot's colour proximity: negative reads black, above one reads
    full, inside 0..1 passes through (the fleet fold, 2026-08-11). The fold is
    NOT the recipe — -0.8, -200 and -1e11 all read #000000, so the strip can
    never be read back into the paid payload."""
    out = []
    for v in rgb[:3]:
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        if f != f or f < 0.0:
            f = 0.0
        elif f > 1.0:
            f = 1.0
        out.append(int(f * 255 + 0.5))
    return "#%02x%02x%02x" % tuple(out)


def design_proximity(g):
    """Seven slot hexes in ENGINE order + the accent — the whole public face
    of a glitch design (a card is its NAME and its COLOUR PROXIMITY; no
    picture, on any surface, ever — fleet order 2026-08-11)."""
    p = g.get("payload") or {}
    return {
        "accent": g.get("accent_hex") or "#7CA842",
        "strip": [_prox_hex(p.get(k) or []) for k in _SLOT_KEYS],
    }


def public_view(g):
    """Catalog entry shape shared with the frontend (no payload). `image` is
    retired to "" (glitch render pictures are gone fleet-wide, 2026-08-11);
    the card renders `proximity` instead."""
    prox = design_proximity(g)
    return {
        "glitch_id": g["id"], "name": g["name"], "subtitle": g["subtitle"],
        "accent_hex": g["accent_hex"], "category": g["category"],
        "rarity": GLITCH_RARITY, "image": "",
        "proximity": prox["strip"], "accent": prox["accent"],
    }
