# -*- coding: utf-8 -*-
"""Versioned Evrima skin contract and positive writer-capability gate.

The game-table manifest is immutable process input.  It is read once, checked
against the small shape this backend depends on, and then served byte-for-byte.
No request scans PAK output or walks the asset tree.

Contract v1 is deliberately *not* implemented here: the seven-slot validators
in :mod:`webcore.designs` and :mod:`webcore.skin_apply` remain its frozen wire.
This module owns only explicit ``contract_version: 2`` recipes and the runtime
proof that the active game writer can consume them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from functools import lru_cache
from pathlib import Path


SCHEMA_VERSION = 2
BASE_SLOTS = ("body", "markings", "flank", "underbelly", "detail1", "eyes",
              "male_display")
ADVANCED_SLOTS = ("teeth", "mouth", "claws")
ALL_SLOTS = BASE_SLOTS + ADVANCED_SLOTS
VARIATION_KEYS = (2.0, 8.0, 16.0)
VARIATION_EPS = 1e-6

WRITER_CAPABILITY_LEAF = "skin_contract_capabilities.json"
V2_COMMAND_LEAF = "skin_commands_v2.json"
V2_ALIVE_LEAF = "skin_contract_v2_alive.json"
WRITER_CAPABILITY_MAX_BYTES = 16 * 1024
# The continuously refreshed alive beacon owns liveness.  A capability is a
# boot-scoped declaration, not a heartbeat: once a proven writer publishes it,
# forcing another disk write every few seconds would add permanent background
# I/O on every game box for no safety gain.  This window is therefore used for
# the alive feed and for future-clock rejection only.  Exact boot equality
# makes a capability from any prior process unusable.
WRITER_CAPABILITY_MAX_AGE_SECONDS = 90.0
_WRITERS = frozenset(("lua", "cpp", "c++", "native"))
_BOOT_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")

_ROOT = Path(__file__).resolve().parents[1]

#: ★ WHERE THE SIDECAR LIVES IS THE BUNDLE'S BUSINESS, NOT THIS MODULE'S
#: (2026-08-24, the bespoke-owner wave).  A webcore owner keeps
#: ``skincontract/skin_capabilities.v2.json`` one level above this file and the
#: default below finds it.  A BESPOKE owner vendors this module into their own
#: backend at a depth we do not control, while their web root - the only place
#: the sidecar can live, since it is a DISK file beside the sealed bundle, not
#: inside it - sits somewhere else entirely.  Without this the vendored module
#: resolves to a path that does not exist and every such owner answers
#: ``no_manifest`` forever.  Absence is still a named state, never a crash.
_MANIFEST_ENV = "SKIN_CAPABILITIES_V2_PATH"
_manifest_override = os.environ.get(_MANIFEST_ENV, "").strip()
#: Deliberately a plain module global, not a function: the suite monkeypatches
#: this name to exercise the absent and malformed manifest branches.
MANIFEST_PATH = (Path(_manifest_override) if _manifest_override
                 else _ROOT / "skincontract" / "skin_capabilities.v2.json")


def contract_version(recipe) -> int | None:
    """Return 1/2, or ``None`` for an explicitly malformed/unknown version.

    Missing is v1.  That default is the compatibility boundary: old rows,
    old callers and old JSON remain seven-slot recipes without migration.
    """
    if not isinstance(recipe, dict):
        return None
    value = recipe.get("contract_version", 1)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value in (1, SCHEMA_VERSION) else None


def is_v2(recipe) -> bool:
    return contract_version(recipe) == SCHEMA_VERSION


@lru_cache(maxsize=1)
def _manifest_bundle() -> tuple[bytes, dict, str]:
    # ★ COERCED, and the reason is a 500 this module exists to prevent
    # (2026-08-24, Primal Instinct's gate).  ``MANIFEST_PATH`` is documented as
    # a Path, but a BESPOKE owner's adapter sets it by hand to point at their
    # own web root, and a plain string there raises ``AttributeError`` in here
    # - which surfaces as an unhandled 500 on the studio page rather than the
    # named ``no_manifest`` state.  Absence is a state; a spelling is not a
    # crash.
    raw = Path(MANIFEST_PATH).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    _validate_manifest(data)
    etag = '"sha256-%s"' % hashlib.sha256(raw).hexdigest()
    return raw, data, etag


def _validate_manifest(data) -> None:
    """Fail startup/use loudly if the generated source is not our contract."""
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("skin manifest schema mismatch")
    build = data.get("build")
    if not isinstance(build, str) or not build.isdigit() or len(build) > 32:
        raise ValueError("skin manifest build is invalid")
    species = data.get("species")
    if not isinstance(species, dict) or not species:
        raise ValueError("skin manifest has no species")

    patterns_seen = themes_seen = 0
    theme_indexes: set[int] = set()
    for name, row in species.items():
        if not isinstance(name, str) or not name or not isinstance(row, dict):
            raise ValueError("skin manifest species row is invalid")
        patterns = row.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError("skin manifest pattern list is invalid")
        indexes = []
        for pattern in patterns:
            if not isinstance(pattern, dict):
                raise ValueError("skin manifest pattern row is invalid")
            index = pattern.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError("skin manifest pattern index is invalid")
            if index in indexes:
                raise ValueError("skin manifest pattern index is duplicated")
            indexes.append(index)
            themes = pattern.get("themes")
            if not isinstance(themes, list) or not themes:
                raise ValueError("skin manifest theme list is invalid")
            local = set()
            for theme in themes:
                if not isinstance(theme, dict):
                    raise ValueError("skin manifest theme row is invalid")
                theme_index = theme.get("index")
                if (isinstance(theme_index, bool)
                        or not isinstance(theme_index, int)
                        or theme_index < 0 or theme_index in local):
                    raise ValueError("skin manifest theme index is invalid")
                local.add(theme_index)
                theme_indexes.add(theme_index)
                themes_seen += 1
                slots = theme.get("supported_slots")
                if not isinstance(slots, list):
                    raise ValueError("skin manifest supported slots are invalid")
                for slot in slots:
                    if (not isinstance(slot, dict)
                            or slot.get("slot") not in ALL_SLOTS):
                        raise ValueError("skin manifest names an unknown slot")
        if row.get("pattern_count") != len(patterns):
            raise ValueError("skin manifest pattern count disagrees")
        patterns_seen += len(patterns)

    counts = data.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("skin manifest counts are missing")
    if counts.get("species") != len(species):
        raise ValueError("skin manifest species count disagrees")
    if counts.get("patterns") != patterns_seen:
        raise ValueError("skin manifest pattern total disagrees")
    if counts.get("themes") != themes_seen:
        raise ValueError("skin manifest theme total disagrees")
    if 0 not in theme_indexes:
        raise ValueError("skin manifest has no default theme")


def manifest_bytes() -> bytes:
    return _manifest_bundle()[0]


def manifest() -> dict:
    """The checked, process-cached manifest. Treat the returned dict read-only."""
    return _manifest_bundle()[1]


def manifest_etag() -> str:
    return _manifest_bundle()[2]


def game_build() -> str:
    return str(manifest()["build"])


def _species_pattern_theme(species: str, pattern, theme):
    species_row = manifest()["species"].get(species)
    if not isinstance(species_row, dict):
        return None, "bad_species"
    if isinstance(pattern, bool) or not isinstance(pattern, int):
        return None, "bad_pattern"
    patterns = species_row.get("patterns") or []
    if pattern < 0:
        return None, "bad_pattern"
    pattern_row = next((row for row in patterns
                        if isinstance(row, dict) and row.get("index") == pattern),
                       None)
    if pattern_row is None:
        return None, "bad_pattern"
    if isinstance(theme, bool) or not isinstance(theme, int):
        return None, "bad_theme"
    for theme_row in pattern_row.get("themes") or ():
        if theme_row.get("index") == theme:
            return theme_row, "ok"
    return None, "bad_theme"


def _rgba(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        return None
    out = []
    for component in value[:3]:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            return None
        number = float(component)
        if not math.isfinite(number) or not (0.0 <= number <= 1.0):
            return None
        out.append(round(number, 5))
    out.append(1.0)
    return out


def validate_recipe_v2(species, raw) -> dict | None:
    """Validate and rebuild one explicit v2 recipe; never repairs or guesses."""
    if (not isinstance(species, str) or not isinstance(raw, dict)
            or contract_version(raw) != SCHEMA_VERSION
            or raw.get("glitch") is True):
        return None

    pattern = raw.get("pattern")
    theme = raw.get("theme")
    _theme_row, reason = _species_pattern_theme(species, pattern, theme)
    if reason != "ok":
        return None

    out: dict = {"contract_version": SCHEMA_VERSION}
    for slot in ALL_SLOTS:
        rgba = _rgba(raw.get(slot))
        if rgba is None:
            return None
        out[slot] = rgba

    variation = raw.get("variation")
    if isinstance(variation, bool) or not isinstance(variation, (int, float)):
        return None
    number = float(variation)
    if not math.isfinite(number):
        return None
    for key in VARIATION_KEYS:
        if abs(number - key) <= VARIATION_EPS:
            out["pattern"] = pattern
            out["variation"] = key
            out["theme"] = theme
            return out
    return None


def writer_capability_path(channel_path: Path) -> Path:
    return Path(channel_path).with_name(WRITER_CAPABILITY_LEAF)


def _build_or_blank() -> str:
    # AN OWNER WITH NO SKIN MANIFEST IS A STATE, NOT A CRASH (2026-08-24, NAD
    # Evrima ship): the DISABLED verdict itself read game_build() ->
    # read_bytes() on an absent skin_capabilities.v2.json, so every signed-out
    # visitor to /studio got a 500 from a feature this owner does not run. Only
    # ABSENCE is tolerated here - a present-but-invalid manifest still fails
    # loudly through manifest()'s validator.
    try:
        return game_build()
    except FileNotFoundError:
        return ""


def _disabled(reason: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "enabled": False,
            "build": _build_or_blank(), "slots": [], "themes": [],
            "reason": reason}


def disabled_capability(reason: str) -> dict:
    """Public total fallback for callers whose runtime paths are unconfigured."""
    return _disabled(str(reason or "unavailable"))


def _read_small_json(path: Path) -> tuple[dict | None, float | None]:
    try:
        target = Path(path)
        # Bind the metadata and bytes to one open handle.  A capability writer
        # lands by rename; separate ``stat`` and ``read_bytes`` path lookups can
        # otherwise pair the old file's age with the new file's declaration.
        with target.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if (before.st_size <= 0
                    or before.st_size > WRITER_CAPABILITY_MAX_BYTES):
                return None, None
            raw = handle.read(WRITER_CAPABILITY_MAX_BYTES + 1)
            after = os.fstat(handle.fileno())
        if (len(raw) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns):
            return None, None
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return None, None
    return (data, float(after.st_mtime)) if isinstance(data, dict) else (None, None)


def active_boot_id(alive_path: Path, *, now: float | None = None,
                   max_age: float = WRITER_CAPABILITY_MAX_AGE_SECONDS
                   ) -> str | None:
    """The fresh game boot token from the standard alive feed, or no proof."""
    data, mtime = _read_small_json(alive_path)
    if data is None or mtime is None:
        return None
    stamp = data.get("ts_ms")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        return None
    stamp = float(stamp) / 1000.0
    if not math.isfinite(stamp):
        return None
    current = time.time() if now is None else float(now)
    if not math.isfinite(current):
        return None
    ages = (current - stamp, current - mtime)
    # Check each clock independently.  ``max(ages)`` would let a current mtime
    # hide a forged future JSON timestamp (and vice versa).
    if any(age > float(max_age) or age < -float(max_age) for age in ages):
        return None
    for key in ("boot_id", "game_boot_id", "process_boot_id"):
        value = data.get(key)
        if isinstance(value, str):
            token = value.strip()
            if _BOOT_RE.fullmatch(token):
                return token
    return None


def _evaluate_capability(data: dict, mtime: float, expected: str | None,
                         current: float, max_age: float,
                         expected_owner_key: str | None
                         ) -> tuple[dict, str | None]:
    if not math.isfinite(current):
        return _disabled("invalid_clock"), None
    version = data.get("contract_version", data.get("schema_version"))
    if version != SCHEMA_VERSION:
        return _disabled("wrong_writer_schema"), None
    writer = data.get("writer")
    if not isinstance(writer, str) or writer.strip().lower() not in _WRITERS:
        return _disabled("unsupported_writer"), None
    consumer = data.get("consumer")
    if (not isinstance(consumer, str)
            or consumer.strip().lower() not in _WRITERS
            or consumer.strip().lower() != writer.strip().lower()):
        return _disabled("unsupported_consumer"), None
    # An old consumer may poll the legacy command file on the same owner.  V2
    # is armed only when the declaring writer owns a distinct, fixed leaf that
    # a legacy C++/Lua poller cannot steal and partially parse.
    if data.get("command_file") != V2_COMMAND_LEAF:
        return _disabled("wrong_writer_channel"), None
    owner_key = data.get("owner_key")
    expected_owner = (expected_owner_key.strip().lower()
                      if isinstance(expected_owner_key, str) else "")
    if not expected_owner:
        return _disabled("no_expected_owner"), None
    if (not isinstance(owner_key, str) or not owner_key.strip()
            or len(owner_key.strip()) > 128
            or owner_key.strip().lower() != expected_owner):
        return _disabled("wrong_owner"), None
    build = data.get("game_build", data.get("build"))
    # 2026-08-24 (Cretaceous Isle, the first live capability of the wave): this
    # branch is reached only by a REAL capability, and game_build() raised
    # FileNotFoundError on a box whose web root has no skin_capabilities.v2.json
    # (a sealed code payload never carried the sidecar) - a 500 on the studio
    # the instant the game proved itself. Absence is a state, named.
    expected_build = _build_or_blank()
    if not expected_build:
        return _disabled("no_manifest"), None
    if isinstance(build, bool) or str(build or "") != expected_build:
        return _disabled("wrong_build"), None

    boot = data.get("boot_id")
    if not isinstance(boot, str) or not _BOOT_RE.fullmatch(boot.strip()):
        return _disabled("missing_writer_boot"), None
    if not isinstance(expected, str) or not _BOOT_RE.fullmatch(expected.strip()):
        return _disabled("no_active_boot"), None
    if boot.strip() != expected.strip():
        return _disabled("wrong_boot"), None

    stamp = data.get("updated_at")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        return _disabled("missing_writer_timestamp"), None
    stamp = float(stamp)
    if not math.isfinite(stamp):
        return _disabled("missing_writer_timestamp"), None
    ages = (current - stamp, current - mtime)
    if any(age < -float(max_age) for age in ages):
        return _disabled("writer_clock_ahead"), None
    # Deliberately no old-age expiry here.  The fresh alive file above proves
    # this exact boot is still ticking, while ``boot == expected`` proves these
    # bytes came from that boot.  Expiring this file would turn a static
    # declaration into a write-amplifying heartbeat.

    slots = data.get("slots")
    if (not isinstance(slots, list) or any(not isinstance(v, str) for v in slots)
            or len(slots) != len(set(slots)) or set(slots) != set(ALL_SLOTS)):
        return _disabled("incomplete_writer_slots"), None
    themes = data.get("themes")
    if (not isinstance(themes, list) or not themes
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                   for v in themes)
            or len(themes) != len(set(themes)) or 0 not in themes):
        return _disabled("invalid_writer_themes"), None
    known_themes = {theme["index"]
                    for species in manifest()["species"].values()
                    for pattern in species["patterns"]
                    for theme in pattern["themes"]}
    if any(theme not in known_themes for theme in themes):
        return _disabled("invalid_writer_themes"), None

    return ({"schema_version": SCHEMA_VERSION, "enabled": True,
             "build": game_build(), "slots": list(ALL_SLOTS),
             "themes": sorted(themes), "reason": "ok"}, boot.strip())


def writer_context(capability_path: Path, *, alive_path: Path | None = None,
                   expected_boot_id: str | None = None,
                   expected_owner_key: str | None = None,
                   now: float | None = None,
                   max_age: float = WRITER_CAPABILITY_MAX_AGE_SECONDS
                   ) -> tuple[dict, str | None, Path | None]:
    """One atomic-ish read of the proof -> compact state, boot, v2 queue.

    The returned boot is the exact token read from the capability bytes that
    produced ``enabled: true``.  Callers stamp it into the command so a new
    game boot can never consume a prior boot's queued paint.
    """
    data, mtime = _read_small_json(capability_path)
    if data is None or mtime is None:
        return _disabled("no_writer_capability"), None, None
    current = time.time() if now is None else float(now)
    expected = expected_boot_id
    effective_alive = alive_path
    declared_alive = data.get("alive_file")
    if declared_alive is not None:
        # A companion writer is allowed its own heartbeat, but never an
        # arbitrary path.  The exact fixed sibling leaf prevents a forged
        # capability from making the website read another owner's file while
        # keeping older integrated writers backward-compatible.
        if declared_alive != V2_ALIVE_LEAF:
            return _disabled("wrong_writer_alive"), None, None
        effective_alive = Path(capability_path).with_name(V2_ALIVE_LEAF)
    if expected is None and effective_alive is not None:
        expected = active_boot_id(
            effective_alive, now=current, max_age=max_age)
    state, boot = _evaluate_capability(
        data, mtime, expected, current, float(max_age), expected_owner_key)
    target = (Path(capability_path).with_name(V2_COMMAND_LEAF)
              if state.get("enabled") is True else None)
    return state, boot, target


def effective_capability(capability_path: Path, *, alive_path: Path | None = None,
                         expected_boot_id: str | None = None,
                         expected_owner_key: str | None = None,
                         now: float | None = None,
                         max_age: float = WRITER_CAPABILITY_MAX_AGE_SECONDS
                         ) -> dict:
    """Return the compact, fail-closed v2 gate consumed by the frontend."""
    state, _boot, _target = writer_context(
        capability_path, alive_path=alive_path,
        expected_boot_id=expected_boot_id,
        expected_owner_key=expected_owner_key,
        now=now, max_age=max_age)
    return state


def v2_write_supported(species, recipe, capability: dict) -> bool:
    """All preconditions for a v2 save/apply, without performing a mutation."""
    if not isinstance(capability, dict) or capability.get("enabled") is not True:
        return False
    valid = validate_recipe_v2(species, recipe)
    if valid is None:
        return False
    return valid["theme"] in capability.get("themes", ())


def v2_command_path(capability_path: Path, capability: dict) -> Path | None:
    """The dedicated v2 queue, only after the compact capability says yes."""
    if not isinstance(capability, dict) or capability.get("enabled") is not True:
        return None
    return Path(capability_path).with_name(V2_COMMAND_LEAF)
