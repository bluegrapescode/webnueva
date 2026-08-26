# -*- coding: utf-8 -*-
"""The skin command WIRE, with no website dependencies.

★ WHY THIS MODULE EXISTS (2026-08-24, lane `2026-08-24-skinv2overlay`).
:mod:`webcore.skin_apply` owns the fleet's proven wire: the ONE srgb->linear
encode, the rails that keep a channel off exact 0/1, the exact-key variation
snap, the v2 entry field order, and the single-entry channel landing.  It also
imports :mod:`webcore.config`, :mod:`webcore.designs`, :mod:`webcore.botcatalog`
and sqlite3 - none of which exist inside a BESPOKE owner's website bundle
(Fangs and Ferns, German Dominion, Natural Selection and fourteen siblings run
their own FastAPI/aiohttp apps, not webcore).

Two Codex-staged trees answered that by COPYING the wire into each owner
(``C:\\ServerStaging\\gd_skinv2_20260824\\backend\\skin_contract_routes.py`` and
its byte-identical twin already sitting in FnF's own tree).  A copy is the
exact failure the framework exists to prevent, and it had already drifted: the
copies re-implemented the encode, the landing and - worst - a SECOND private
rate budget beside the owner's v1 one.

So the wire is EXTRACTED here rather than duplicated.  This module imports
stdlib and :mod:`webcore.skin_contract` (itself stdlib-only) and NOTHING else,
so it is safe to vendor into any bespoke bundle.  :mod:`webcore.skin_apply`
delegates to it, which is what makes "one implementation" true rather than
aspirational: there is no second copy left to drift.

★ THE ENCODE HAPPENS EXACTLY ONCE.  A value arriving at :func:`encode_linear`
is a raw picker fraction.  A frontend that already encoded, or a second call
here, is the DOUBLE ENCODE that produced the fleet's original "one part of the
body goes dark".
"""
from __future__ import annotations

import json
import math
import os
import random
import threading
from pathlib import Path

import lin_skin_contract as skin_contract

#: The linear wire keeps more places than the retired raw wire did. 4dp is
#: ~1/10000 of the range, which is fine in picker space but crushes the DARK
#: end once the value is encoded (a #0D pick is linear 0.0025, and 4dp
#: quantises it to 25 steps). 6dp costs nothing and keeps the shadow detail.
LINEAR_WIRE_PLACES = 6

#: What a CORRECT row carries: the wire encoded once, stamped so a reader can
#: tell an encoded row from a raw one without guessing.
WIRE_MARKER = "linear"

#: One command entry's hard ceiling on the channel. A v2 entry is ~1.2 kB.
ENTRY_MAX_BYTES = 4096

#: ``variation`` IS NOT A COLOUR FIELD - it is ``CustomizerData.SkinVariation``,
#: the pattern tiling size, and the client REVERSE-MAPS EXACT KEYS
#: (Small=16.0, Medium=8.0, Large=2.0, Medium the game's own default).
#: ★NEVER add the per-apply eps to this field: the jitter exists to make two
#: consecutive colour applies differ, and adding it here destroys the key and
#: takes the pattern detail with it.
VARIATION_KEYS = skin_contract.VARIATION_KEYS
VARIATION_DEFAULT = 8.0
VARIATION_KEY_EPS = skin_contract.VARIATION_EPS

#: The v2 slots, in the order the native reader expects. Re-exported so a
#: vendored adapter reads the contract off one module.
ALL_SLOTS = skin_contract.ALL_SLOTS

#: The per-submit colour jitter band. One draw per command, applied to colour
#: channels only, so two consecutive applies of the SAME colours still mark the
#: pawn dirty and repaint.
EPS_MIN = 1e-4
EPS_MAX = 1e-3


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def srgb_to_linear(value: float) -> float:
    """IEC 61966-2-1, clamped at both ends - the byte-identical donor form.

    The game's CustomizerData slots are ``FLinearColor``, which UE consumes as
    LINEAR by definition, so a raw picker fraction written there renders every
    mid-tone too bright.  This is the wire encode.
    """
    value = clamp01(value)
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def linear_to_srgb(value: float) -> float:
    """Exact inverse of :func:`srgb_to_linear` - the DISPLAY decode, not a heal.

    Its live jobs are rendering a stored value or a palette entry for a picker
    swatch.  Running it over a ``color_space:"linear"`` row BRIGHTENS a row
    that was already right.
    """
    value = clamp01(value)
    if value >= 1.0:
        return 1.0
    if value <= 0.04045 / 12.92:
        return value * 12.92
    return clamp01(1.055 * (value ** (1.0 / 2.4)) - 0.055)


def new_eps(rng: random.Random | None = None) -> float:
    """One jitter draw per submitted command."""
    source = rng if rng is not None else random
    return source.uniform(EPS_MIN, EPS_MAX)


def encode_linear(channel: float, draw: float) -> float:
    """Picker fraction -> ONE srgb->linear encode -> the bounds discipline.

    The bounds live in the LINEAR domain, after the encode: never exactly 0
    (the client's all-zero short-circuit), never at or above 1.

    ★★THE ROUND IS THE LAST STEP, SO IT CAN UNDO THE FOLD (found on LIN,
    2026-08-11).  The fold moves a saturated channel to ``1.0 - draw``, but a
    channel landing within half a 6dp step under ``1.0 - draw`` then ROUNDS
    BACK ONTO EXACTLY 1.0 - the rail the fold exists to keep it off.  Exactly
    1.0 is inside the native reader's 0..1 band so it never glowed, but it
    reads as a NATIVE capture to every provenance grader that treats exact 0/1
    as native.  The rails below are applied to the ROUNDED value, which is the
    only place they cannot be undone.  All 256 8-bit picks stay byte-identical.
    """
    value = srgb_to_linear(clamp01(channel))
    value = value + draw if value <= 1.0 - draw else value - draw
    value = round(clamp01(value), LINEAR_WIRE_PLACES)
    rail = 10.0 ** -LINEAR_WIRE_PLACES
    return min(1.0 - rail, max(rail, value))


def variation_key(value) -> float:
    """Snap ``value`` to an EXACT :data:`VARIATION_KEYS` member, else Medium.

    The client reverse-maps SkinVariation by exact key, so this returns the KEY
    OBJECT and never the caller's float - an 8.000000001 from a JSON round-trip
    must go out as 8.0, not as near-8.0.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return VARIATION_DEFAULT
    if not math.isfinite(number):
        return VARIATION_DEFAULT
    for key in VARIATION_KEYS:
        if abs(number - key) <= VARIATION_KEY_EPS:
            return key
    return VARIATION_DEFAULT


def manifest_species_key(raw) -> str:
    """A live blueprint class or a display species -> the MANIFEST's own key.

    ★ THE MANIFEST IS THE AUTHORITY HERE, NOT A NAME TABLE.  A v2 recipe is
    validated against ``manifest()["species"][key]``, so any transform that can
    return a string the manifest does not carry is a refusal waiting to happen
    on a live pawn.  This resolves ONLY to keys that exist, and returns ``""``
    when it cannot - which the caller turns into a named 409, never a guess.

    Handles the three shapes the fleet actually sees: the exact key
    (``Tyrannosaurus``), the live blueprint class (``BP_Tyrannosaurus_C``), and
    a case-folded label.  The framework suite pins this against
    ``botcatalog.asset_species`` for every species in the shipped manifest.
    """
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        species = skin_contract.manifest()["species"]
    except (OSError, ValueError, TypeError, KeyError):
        return ""
    by_fold = {name.casefold(): name for name in species}
    folded = value.casefold()
    if folded in by_fold:
        return by_fold[folded]
    if folded.startswith("bp_"):
        folded = folded[3:]
    if folded.endswith("_c"):
        folded = folded[:-2]
    if folded in by_fold:
        return by_fold[folded]
    # Last resort: the longest manifest key contained in the string. Longest
    # wins so ``BP_Tyrannosaurus_Juvenile_C`` cannot resolve to a shorter
    # species that happens to be a substring of it.
    matches = [name for key, name in by_fold.items() if key in folded]
    return max(matches, key=len) if matches else ""


def new_cmd_id(namespace: str, steam_id: str,
               rng: random.Random | None = None) -> str:
    """Correlation id in the fleet shape: ``<ns>_skinv2_<tail>_<rand>``.

    The prefix is the OWNER's id namespace so two owners' commands can never
    collide even in one feed directory.  ``skinv2`` (not ``skin``) keeps a v2
    correlation id distinguishable in a log that also carries v1 ids.
    """
    source = rng if rng is not None else random
    tag = str(namespace or "web").strip() or "web"
    return "%s_skinv2_%s_%x" % (tag, str(steam_id)[-6:],
                                source.getrandbits(48))


def build_v2_entry(steam_id: str, live_class: str, recipe: dict, cmd_id: str,
                   *, actor_name: str, writer_boot_id: str,
                   eps: float | None = None,
                   rng: random.Random | None = None) -> dict:
    """One validated v2 recipe -> the native reader's field set.

    ``recipe`` MUST already have passed :func:`skin_contract.validate_recipe_v2`
    - this builder CONVERTS, it never validates.

    ★ THE EMISSION ORDER IS DELIBERATE.  No boolean is ever placed where the
    native 20-char value scan could misread it, and ``preserve_female`` is
    LAST.  V2 is exact: the pattern is never folded into a different look, and
    the variation is the snapped key.

    ★ THE BOOT TOKEN IS MANDATORY.  It is the proven token read out of the
    capability bytes that armed this apply, so a game that reboots between the
    queue write and the drain refuses a prior boot's paint instead of wearing
    it.  A missing token is a programming error, not a runtime state.
    """
    if not isinstance(writer_boot_id, str) or not writer_boot_id.strip():
        raise ValueError("v2 entry requires the proven writer boot id")
    if not isinstance(recipe, dict) or not skin_contract.is_v2(recipe):
        raise ValueError("v2 entry requires a validated v2 recipe")
    draw = new_eps(rng) if eps is None else float(eps)

    entry: dict = {"steamid": str(steam_id)}
    if actor_name:
        entry["actor_name"] = str(actor_name)
    entry["cmd_id"] = str(cmd_id)
    entry["class"] = str(live_class or "")
    entry["variation"] = variation_key(recipe.get("variation"))
    entry["contract_version"] = skin_contract.SCHEMA_VERSION
    entry["boot_id"] = writer_boot_id.strip()
    entry["pattern"] = int(recipe["pattern"])
    entry["theme"] = int(recipe["theme"])
    entry["color_space"] = WIRE_MARKER
    for slot in ALL_SLOTS:
        rgba = recipe[slot]
        entry[slot] = [encode_linear(rgba[0], draw),
                       encode_linear(rgba[1], draw),
                       encode_linear(rgba[2], draw),
                       1.0]
    # LAST. See the emission-order note above.
    entry["preserve_female"] = True
    return entry


def append_single_command(channel_path: Path, entry: dict) -> tuple[bool, str]:
    """Land one v2 command without ever reading or merging the queue.

    The companion consumer claims by renaming ``<channel>`` to
    ``<channel>.processing``.  A read/merge/write producer can resurrect bytes
    claimed between its read and its landing, and a batch also defeats the
    consumer's intentionally one-command game-thread budget.  V2 therefore has
    a dedicated single-entry lane: an occupied or actively processed lane is
    ``channel_busy`` and the caller retries.

    All production game boxes are Windows.  ``os.rename`` there is an atomic
    create-if-absent landing and refuses rather than replacing an existing
    destination, so concurrent producers have one winner and no torn file.
    The unique temp is always cleaned after either outcome.
    """
    channel_path = Path(channel_path)
    try:
        body = json.dumps([entry], ensure_ascii=True, separators=(",", ":"))
        encoded = body.encode("utf-8")
    except (TypeError, ValueError):
        return False, "entry_too_large"
    if len(encoded) > ENTRY_MAX_BYTES:
        return False, "entry_too_large"

    processing = channel_path.with_name(channel_path.name + ".processing")
    if channel_path.exists() or processing.exists():
        return False, "channel_busy"
    temp = channel_path.with_name(
        ".%s.web.%d.%x.%x.tmp" % (
            channel_path.name, os.getpid(), threading.get_ident(),
            random.getrandbits(48)))
    try:
        try:
            with temp.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(temp, channel_path)
            return True, "ok"
        except FileExistsError:
            return False, "channel_busy"
        except PermissionError:
            return (False, "channel_busy" if channel_path.exists()
                    or processing.exists() else "write_failed")
        except OSError:
            return False, "write_failed"
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
