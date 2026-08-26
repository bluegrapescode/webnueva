# -*- coding: utf-8 -*-
"""Exact-copy sidecar for the skin editor's "Copiar mi skin actual".

Owner report 2026-08-08: "i see the skin when i hatch and grow is perfect but
then when i copy the current skin is different." Root cause: the copy lane
converts the live snapshot into the editor's display gamut (linear->sRGB needs
0..1, alpha 0..1, pattern 0..2) — faithful for skins the editor itself made,
silently re-authoring for glitch-space payloads (channels at hundreds, alpha
rails, out-of-band patterns), which is exactly what a hatched / crate / catalog
glitch skin wears.

Contract:
  * A copy keeps a RAW sidecar: the snapshot floats VERBATIM (7 slots RGBA +
    pattern + variation). Nothing is folded at storage; validation REFUSES
    instead — a stored lie is worse than a refused copy.
  * The sidecar only ever holds SERVER-WITNESSED bytes: the preset save re-reads
    the caller's live snapshot and requires a slot-for-slot match
    (raw_matches_snapshot), so the free save lane can never mint arbitrary
    glitch-space payloads a dino never wore.
  * Exact APPLY builds the command the way the crate glitch lane does — raw
    floats, no sRGB decode, no eps jitter, no color_space key — plus
    preserve_female=True (the live pawn's sex always wins, fail-closed in the
    mod). See glitch_catalog's module docstring: the sRGB decode in
    SkinPayloadIn.to_command is a normal-lane-only transform that would corrupt
    signed glitch magnitudes.
  * Restart-window poison (channel <= -900000 / pattern -8) is REFUSED, never
    copied, never replayed.
  * OWNER GRANT (2026-08-20). The sentinel band OVERLAPS real worn glitch
    magnitudes by value (glitch_catalog's docstring says so), so the poison
    rule also refuses a genuine glitch look a player is wearing right now --
    deliberately, because that refusal is what stops paid catalog designs
    being cloned into the free editor. An OWNER-DIRECTED grant is not a player
    copy: a sidecar carrying `owner_grant: True` skips the sentinel rule ONLY
    (every other bound -- finite, four channels per slot, the 1e12 window, the
    pattern range -- still applies, and the bytes are still server-witnessed
    against the live pawn). The flag is unreachable from the wire: the preset
    routes build the sidecar from RawSkinSidecarIn.model_dump(), which emits
    declared fields only, so no request body can set it. Only an off-box owner
    tool writes it -- tools/lin_save_live_skin.py in theisle-framework.

Pure module: no db, no FastAPI, no game_ipc — server.py wires it to the routes
and tests_local drives it (plus the real routes) directly.
"""
import math

from glitch_catalog import GLITCH_CHANNEL_MAX

SLOT_KEYS = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")

# Same sentinel family the copy lane / SpeciesViewer3D already refuse: a
# snapshot taken between a server restart and the re-apply is garbage.
POISON_CHANNEL = -900000.0
POISON_PATTERN = -8

# An owner-directed grant marks its sidecar with this key. It waives the
# sentinel rule and NOTHING else -- see the module docstring.
OWNER_GRANT_KEY = "owner_grant"

# GLITCH-CREATOR GRANT (2026-08-23: Owner/Streamer/Adult/Elder/Apex). Marks a
# sidecar AUTHORED (or copied) by an account the server itself verified as
# glitch-entitled at save time. Like OWNER_GRANT_KEY it waives the CHANNEL
# sentinel rule only -- but unlike it, an authored pattern -8 stays refused
# (that value is the engine's restart sentinel, never an aesthetic; replaying
# it could poison the restore lane). Unreachable from the wire the same way:
# RawSkinSidecarIn.model_dump() emits declared fields only, so a client body
# carrying glitch_grant is dropped before validation. Only server.py stamps it,
# after its own entitlement check.
GLITCH_GRANT_KEY = "glitch_grant"

CHANNEL_ABS_MAX = float(GLITCH_CHANNEL_MAX)   # single source with the glitch lane
VARIATION_ABS_MAX = float(GLITCH_CHANNEL_MAX)
PATTERN_ABS_MAX = 32                          # replay bound; live catalog is 0..2

# The editor's own apply jitters variation by 0.001..0.01 so the engine's
# struct delta fires; a snapshot within this of zero is editor-representable.
EDITOR_VARIATION_TOL = 0.02
EDITOR_PATTERN_MAX = 2


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_owner_grant(raw):
    """True only for a sidecar an owner tool marked. Anything else — a missing
    key, a truthy string off a hand-edited file, a client body — is False."""
    return isinstance(raw, dict) and raw.get(OWNER_GRANT_KEY) is True


def is_glitch_grant(raw):
    """True only for a sidecar server.py stamped after verifying the saver's
    glitch-creator entitlement. Same literal-True rule as is_owner_grant."""
    return isinstance(raw, dict) and raw.get(GLITCH_GRANT_KEY) is True


def validate_raw(raw):
    """(ok, reason) for a raw sidecar dict. Refuses — never folds, never clamps.

    An owner-granted sidecar waives the SENTINEL rules and nothing else. A
    glitch-granted sidecar waives the CHANNEL sentinel only — an authored
    pattern -8 (the engine's restart sentinel) stays refused."""
    if not isinstance(raw, dict):
        return False, "shape"
    owner = is_owner_grant(raw)
    grant = owner or is_glitch_grant(raw)
    pat = raw.get("pattern")
    if not _finite(pat) or int(pat) != pat:
        return False, "pattern"
    pat = int(pat)
    if pat == POISON_PATTERN and not owner:
        return False, "poison_pattern"
    if abs(pat) > PATTERN_ABS_MAX:
        return False, "pattern_range"
    var = raw.get("variation")
    if not _finite(var) or abs(float(var)) > VARIATION_ABS_MAX:
        return False, "variation"
    for k in SLOT_KEYS:
        arr = raw.get(k)
        if not isinstance(arr, (list, tuple)) or len(arr) != 4:
            return False, "slot_%s" % k
        for c in arr:
            if not _finite(c):
                return False, "slot_%s" % k
            if float(c) <= POISON_CHANNEL and not grant:
                return False, "poison_%s" % k
            if abs(float(c)) > CHANNEL_ABS_MAX:
                return False, "range_%s" % k
    return True, ""


def extract_raw(snap, owner_grant=False, glitch_grant=False):
    """Mod snapshot dict -> verbatim raw sidecar, or None when the snapshot
    cannot vouch for an EXACT copy (missing slot, short RGBA, non-finite,
    poison, out-of-window). None means "no sidecar", never a partial one — the
    clamped editor copy still proceeds exactly as before this module existed.

    owner_grant=True stamps the grant flag BEFORE validating, so the sentinel
    band stops being a refusal for that one call — and the stamp rides into the
    returned sidecar, where it is the stored record of WHY those bytes were
    allowed. Player-facing callers never pass it. glitch_grant=True is the
    tier-creator equivalent (server-verified entitlement, channel sentinel
    only) — server.py passes it, never a request body."""
    if not isinstance(snap, dict):
        return None
    raw = {}
    if owner_grant:
        raw[OWNER_GRANT_KEY] = True
    if glitch_grant:
        raw[GLITCH_GRANT_KEY] = True
    try:
        pat = snap.get("pattern")
        raw["pattern"] = int(pat) if _finite(pat) and int(pat) == pat else None
        var = snap.get("variation")
        raw["variation"] = float(var) if _finite(var) else None
        if raw["pattern"] is None or raw["variation"] is None:
            return None
        for k in SLOT_KEYS:
            arr = snap.get(k)
            if not isinstance(arr, (list, tuple)) or len(arr) < 4:
                return None
            vals = []
            for c in arr[:4]:
                if not _finite(c):
                    return None
                vals.append(float(c))
            raw[k] = vals
    except (TypeError, ValueError, OverflowError):
        return None
    ok, _ = validate_raw(raw)
    return raw if ok else None


def is_lossy(raw):
    """True when the editor's display conversion would RE-AUTHOR this payload —
    any channel/alpha outside [0,1], a pattern outside the editor's 0..2, or a
    variation the editor cannot express. False = the clamped copy is already
    faithful and the sidecar is just insurance."""
    if not isinstance(raw, dict):
        return False
    pat = raw.get("pattern")
    if _finite(pat) and not (0 <= int(pat) <= EDITOR_PATTERN_MAX):
        return True
    var = raw.get("variation")
    if _finite(var) and abs(float(var)) > EDITOR_VARIATION_TOL:
        return True
    for k in SLOT_KEYS:
        arr = raw.get(k)
        if isinstance(arr, (list, tuple)):
            for c in arr:
                if _finite(c) and not (0.0 <= float(c) <= 1.0):
                    return True
    return False


def raw_matches_snapshot(raw, snap, rel_tol=1e-6, abs_tol=1e-6):
    """Does the client-supplied sidecar equal the live snapshot slot-for-slot?
    The security boundary of the free save lane: only bytes the server itself
    can witness on the caller's own dino are ever stored. Tolerances cover
    JSON float round-tripping only, never re-authoring."""
    if not isinstance(raw, dict) or not isinstance(snap, dict):
        return False
    # Witness the live snapshot at the SAME grant level the sidecar claims —
    # otherwise an owner-granted glitch payload could never be witnessed at all
    # (extract_raw would refuse the very bytes the pawn is wearing).
    live = extract_raw(snap, owner_grant=is_owner_grant(raw),
                       glitch_grant=is_glitch_grant(raw))
    if live is None:
        return False
    if int(raw.get("pattern")) != live["pattern"]:
        return False
    if not math.isclose(float(raw.get("variation")), live["variation"],
                        rel_tol=rel_tol, abs_tol=abs_tol):
        return False
    for k in SLOT_KEYS:
        a, b = raw.get(k), live[k]
        if len(a) != 4:
            return False
        for x, y in zip(a, b):
            if not math.isclose(float(x), y, rel_tol=rel_tol, abs_tol=abs_tol):
                return False
    return True


def build_exact_command(raw, actor_name, dino_class, steam_id):
    """Verbatim skin command — the glitch-lane shape. NO sRGB decode, NO eps
    jitter, NO color_space key; preserve_female makes the live pawn's sex win
    (fail-closed in the mod). Callers must have validate_raw'd first."""
    cmd = {
        "actor_name": actor_name, "class": dino_class, "steamid": steam_id,
        "female": False, "preserve_female": True,
        "variation": float(raw["variation"]),
        "pattern": int(raw["pattern"]),
        "skin_code": "",
    }
    for k in SLOT_KEYS:
        cmd[k] = [float(c) for c in raw[k]]
    return cmd
