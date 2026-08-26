# -*- coding: utf-8 -*-
"""GEN-Ø progressive zombie infection — the contaminated-facility exposure lane.

Owner spec (La Isla Nublar, 2026-08-20, his words in
theisle-framework/docs/HANDOFF_LIN_GEN0_ZOMBIE_FACILITY_20260820.md):
a player who stays INSIDE a contaminated facility ~30 s gains virus exposure,
with immersive warning banners while inside; each facility adds 25 % to a
Virus Progress Bar shown on the website (0→25→50→75→100); a facility can be
claimed ONCE PER LIFE; at 100 % the mutation is complete and the player
BECOMES A ZOMBIE (owner order 2026-08-21: "ensure if someone hits 100% they
actually turn into a zombie").

THE TRANSFORMATION CONTRACT (2026-08-21, the zombify lane):
  * At 100 % this backend enqueues action "gen0_zombie" {steamid} into the
    monolith's own notify queue. The mod half paints the game's native zombie
    look on the pawn, HOLDS it until the player's next genuine death, and
    appends JSONL events to Saved/gen0_zombie_events.log:
    {"event":"on"|"off","sid":"7656…","reason":"…","ms":N}. It re-emits "on"
    (reason=reack) when asked to zombify an already-held sid, so a lost event
    self-heals through the retry lane below.
  * "on" marks the doc zombie_active (the ack that stops retries) and lifts
    the bar to 100 when it sat lower (a parked zombie redeemed: the park's
    own "off" had reset it). "off" — the zombie died, was parked, or was
    released by an admin — applies the RESET: percent 0, claims cleared,
    complete_at cleared. The infection is CONSUMED by the transformation; the
    zombie's death gives a clean life back and the cycle can restart.
  * Retries: while a doc sits at 100 % un-acked and its player is seen ALIVE
    in the feed, the enqueue repeats every GEN0_ZOMBIFY_RETRY_S. That also
    back-fills everyone who reached 100 % before the mod half armed.
  * Belts for missed events (backend bounce, mod downtime): a death line in
    death_causes.log is NOT a zombie reset any more (2026-08-22: the mod's
    health<=0 latch also fires for a park kill, a safelog and a plain logout
    — 82 of 379 consecutive live death lines were the same life continuing);
    the mod judges the next living pawn itself and writes "off" only for a
    real new life. A NEW LIFE observed here for a zombie_active doc (species
    change / growth fall vs zombie_life_sig) still applies the RESET —
    conservative, judged at the moment it matters, idempotent through the
    zombie_active guard. Death lines keep ratcheting the CLAIM signature.

THE MAP (removed 2026-08-21): the facilities were drawn on the public site
map for a few hours and REMOVED on the owner's order ("players are finding
it easily") — the zones are meant to be discovered in-world. The public
/gen0/facilities geometry endpoint was deleted with it; nothing serves the
polygons any more.

WHERE EACH HALF LIVES (and why):
  * This module POLLS the mod's own ~1 s position feed
    (players_positions.json via game_ipc) on its own 8 s loop — the same
    read-only feed the visit_location quest tracker already polls. It rides
    BESIDE that tracker, it does not duplicate it: quests credit "was at a
    POI today"; this lane needs a 30 s DWELL with hysteresis, which a 45 s
    quest tick cannot see.
  * In-game banners ride the live monolith's own notify queue
    (Saved/notify_commands.json, action "notify_line") — the exact surface
    /prime banners render through (TIPlayerController::ClientShowNotification).
    RCON directmessage is NEVER used: Evrima accepts it and never renders it
    (fleet law, botcore/gamenotify.py).
  * Percent + per-life claims persist in Mongo (collection gen0_state).
    Dwell timers are in-process only: a backend bounce mid-exposure restarts
    that 30 s stay and nothing else.

FRAMEWORK: canonical copy at theisle-framework/webcore/gen0_infection.py
(this file is the LIN deployment of it). Geometry source of record:
theisle-framework/data/zombie_facilities.json — the polygon literals below
were GENERATED from that ledger and each area is re-proven by the test suite
(shoelace vs the ledger's surveyed m²). Never retype a coordinate.

DEFAULTS THAT ARE STANDING IN FOR HIS OPEN CALLS (handoff §6) — every one is
an env knob, none needs a code change to move:
  height    ground plane ±(15 m below .. 45 m above the walked corners)
  reset     the PERCENT persists across deaths; only CLAIMS are per-life
  F1 edge   the ASSUMED outer hull (stated to him for correction)
  share     25 % per facility
  scope     every player (no staff exemption)
  announce  the exposed player only
  language  Spanish, ASCII-safe (the monolith's own banner idiom)
  at 100 %  the gen0_zombie action is enqueued (GEN0_ZOMBIFY knob) — the mod
            half performs the in-world transformation; his 2026-08-21 order
            closed the last open call from handoff §6.8
  cooldown  2 h between facilities (GEN0_COOLDOWN_S; his 2026-08-21 order:
            "far too easy to get") — each credit stamps cooldown_until_ms on
            the doc; until it passes no OTHER facility pays, the site's GEN-Ø
            section counts it down (cooldown_s on /gen0/contamination), and
            the in-world entry banner says so. The stamp is a RATCHET: death,
            new life and the zombie reset all leave it standing (dying to
            skip the wait must never work); junk reads as free and a clock
            jump costs at most one window (cooldown_left_ms).

THE ZOMBIE'S LIFE SIGNATURE IS CAPTURED FROM THE PAWN, NEVER FROM THE RATCHET
(live defect 2026-08-21 16:00Z): the first "on" ack seeded zombie_life_sig from
the doc's stored life_sig - the claim/death ratchet - and for a player whose
percent PERSISTED from an earlier life (the backfill cohort, by design) that
ratchet describes the OLD life, so the new-life belt reset a player seconds
after the mod transformed him. The signature now comes from the sid's most
recent ALIVE positions row (_last_alive); when no row is known at ack time it
is left None and captured on the first alive sighting, and only a captured
(dict) signature can ever arm the belt.

Wiring (server.py):
    gen0_infection.configure(db)
    app.include_router(gen0_infection.build_router(get_current_user), prefix="/api")
    asyncio.create_task(gen0_infection.gen0_tracker_loop())   # on_startup
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException

import game_ipc

logger = logging.getLogger("gen0")

# ─── knobs (env-overridable; shipped values are the safe defaults) ──────────
def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))

GEN0_ENABLED = os.environ.get("GEN0_ENABLED", "1").strip() not in ("0", "false", "no")
DWELL_S = _env_int("GEN0_DWELL_S", 30, 5, 600)            # stay length
RESET_S = _env_int("GEN0_RESET_S", 10, 2, 120)            # hysteresis gap
TICK_S = _env_int("GEN0_TICK_S", 8, 3, 60)                # poll cadence
PCT_PER_FACILITY = _env_int("GEN0_PCT_PER_FACILITY", 25, 1, 100)
# Between-facility cooldown (owner 2026-08-21: "far too easy to get … if
# someone goes to facility one and reaches 25%, then facility 2 wont count
# until 2 hours have past … then repeat"). Every credit stamps the NEXT
# eligible wall-clock moment; until then no OTHER facility can pay. 0 = off.
COOLDOWN_S = _env_int("GEN0_COOLDOWN_S", 7200, 0, 604800)
Z_BELOW_CM = _env_int("GEN0_Z_BELOW_M", 15, 0, 500) * 100
Z_ABOVE_CM = _env_int("GEN0_Z_ABOVE_M", 45, 0, 1000) * 100
BANNERS_ON = os.environ.get("GEN0_BANNERS", "1").strip() not in ("0", "false", "no")
ZOMBIFY_ON = os.environ.get("GEN0_ZOMBIFY", "1").strip() not in ("0", "false", "no")
ZOMBIFY_RETRY_S = _env_int("GEN0_ZOMBIFY_RETRY_S", 120, 30, 3600)
GROWTH_DROP_LIFE = 0.02      # growth falling this far below the life signature = a new life
BANNER_MIN_GAP_S = 6         # per-player floor between banners
DWELL_MAP_MAX = 1024         # hard bound on tracked players (design ceiling 600)
DEATHLOG_MAX_READ = 256 * 1024   # new death-log bytes consumed per tick, at most

_STEAM64_RE = re.compile(r"^7656\d{13}$")

# ─── the four facilities — GENERATED from data/zombie_facilities.json ───────
# Units: UE centimetres, areas.lua frame (X east/west, Y negative = north).
# Every polygon is the ledger's own perimeter order; the test suite re-derives
# each area with the shoelace formula against the ledger's surveyed value.
FACILITIES = (
    {
        "id": "lin_zombie_facility_1",
        "name": "Instalacion Great Lake",
        # ASSUMED outer hull 5->4a->6->4b->7->8 (ledger _boundary, stated to
        # him for correction). Ledger-proven area 17686.7 m2.
        "poly": (
            (77185.98, -97039.99),
            (86319.01, -90773.41),
            (88100.65, -90220.11),
            (89120.24, -91296.75),
            (94865.66, -101804.47),
            (84785.13, -108732.83),
        ),
        "z_min": 38321.22 - Z_BELOW_CM,
        "z_max": 38791.24 + Z_ABOVE_CM,
    },
    {
        "id": "lin_zombie_facility_2",
        "name": "Instalacion Norte",
        # ledger-proven area 10696.4 m2; dead-level built floor
        "poly": (
            (102014.11, -324398.91),
            (102954.11, -314877.76),
            (114433.69, -316441.05),
            (113624.85, -325265.47),
        ),
        "z_min": 22178.35 - Z_BELOW_CM,
        "z_max": 22181.24 + Z_ABOVE_CM,
    },
    {
        "id": "lin_zombie_facility_3",
        "name": "Instalacion Noroeste",
        # ledger-proven area 19376.2 m2; irregular quad, sloping ground
        "poly": (
            (225460.05, -417612.22),
            (219337.77, -423399.69),
            (206900.35, -427518.35),
            (212694.01, -406065.86),
        ),
        "z_min": 27810.2 - Z_BELOW_CM,
        "z_max": 28010.12 + Z_ABOVE_CM,
    },
    {
        "id": "lin_zombie_facility_4",
        "name": "Instalacion Costa Noreste",
        # ledger-proven area 6007.4 m2
        "poly": (
            (479953.09, -262492.4),
            (484648.53, -258808.78),
            (491074.48, -267531.48),
            (486848.19, -270608.79),
        ),
        "z_min": 20917.15 - Z_BELOW_CM,
        "z_max": 20946.31 + Z_ABOVE_CM,
    },
)

# ─── in-game banner copy — Spanish, ASCII-safe (the monolith's own idiom: its
# notify parser captures raw bytes with [^"]*, so accents/emoji stay out the
# same way "InGen: tu ejemplar ya es apto para Prime" keeps them out) ────────
BANNER_ENTRY = "ADVERTENCIA: contaminacion aerea peligrosa detectada"
BANNER_POOL = (
    "Exposicion al virus detectada. Permanece dentro para continuar la infeccion",
    "Actividad genetica desconocida detectada",
    "Los niveles de contaminacion estan aumentando",
)
BANNER_CREDIT = "GEN-0: exposicion completada. Contaminacion del virus: {pct}%"
BANNER_COMPLETE = "GEN-0: MUTACION COMPLETA. Transformacion biologica detectada"
BANNER_COOLDOWN = "GEN-0: patogeno en recarga. Proxima exposicion disponible en {mins} min"

# ─── module state (configure() injects the seams; tests drive them) ─────────
_db = None                       # motor database (gen0_state collection)
_notify_path: Optional[str] = None

# dwell map: sid -> {fid, fac, enter_mono, last_in_mono, banners,
#                    next_banner_mono, claimable}
_dwell: dict[str, dict[str, Any]] = {}
_rng = random.Random()
# death_causes.log tail cursor: {"offset": bytes consumed, "carry": partial line}
_deathlog_path: Optional[str] = None
_deathlog: dict[str, Any] = {"offset": None, "carry": b""}
# gen0_zombie_events.log tail cursor (the mod's transformation record)
_eventlog_path: Optional[str] = None
_eventlog: dict[str, Any] = {"offset": None, "carry": b""}
# zombify retry gate: sid -> monotonic next-try; pruned to currently-eligible
# sids every sweep so it stays bounded by the online 100 % population
_zombify_next: dict[str, float] = {}
# sids seen ALIVE (health>0, sanitized) in the last tracker pass, with their
# rows — the zombify sweep and its new-life belt judge against these
_last_alive: dict[str, dict] = {}
# Fixed-memory striped lock: only completed facility credits and confirmed
# dino switches enter it.  It keeps an in-flight credit from landing after a
# switch reset and resurrecting the old dinosaur's progress.  256 stripes keep
# a 600-player burst to a few Mongo operations per stripe without an unbounded
# per-player lock map.
_state_locks = tuple(asyncio.Lock() for _ in range(256))


def _state_lock(sid: str) -> asyncio.Lock:
    return _state_locks[hash(sid) & 255]


def configure(db, *, notify_path: str | None = None,
              deathlog_path: str | None = None,
              eventlog_path: str | None = None) -> None:
    """Dependency injection, the crash_game/battle_pass pattern: server.py hands
    in the Mongo handle; nothing here imports server."""
    global _db, _notify_path, _deathlog_path, _eventlog_path, _state_locks
    _db = db
    _notify_path = notify_path or os.path.join(game_ipc.SAVED_DIR, "notify_commands.json")
    _deathlog_path = deathlog_path or os.path.join(game_ipc.SAVED_DIR, "death_causes.log")
    _eventlog_path = eventlog_path or os.path.join(game_ipc.SAVED_DIR, "gen0_zombie_events.log")
    _deathlog["offset"] = None
    _deathlog["carry"] = b""
    _eventlog["offset"] = None
    _eventlog["carry"] = b""
    _zombify_next.clear()
    _last_alive.clear()
    # Tests configure the module on fresh event loops; production configures it
    # once.  Rebuilding here avoids carrying a contended lock across loops.
    _state_locks = tuple(asyncio.Lock() for _ in range(256))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── pure geometry ──────────────────────────────────────────────────────────
def point_in_poly(x: float, y: float, poly) -> bool:
    """Ray-cast point-in-polygon. Bounded (one pass over the edges), no trig,
    no sqrt, no allocation; winding-agnostic so it takes any simple polygon —
    facility 3 is not a rectangle and never needs to be. An axis-aligned
    min/max box is deliberately NOT used: every footprint is rotated and a box
    reads ground nobody walked as inside (survey law)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def facility_at(x: float, y: float, z: float) -> Optional[dict]:
    """First facility containing the point, walked in FACILITIES order — the
    footprints do not overlap today, and a deterministic first-match means a
    future overlap could still never double-credit one stay."""
    for fac in FACILITIES:
        if fac["z_min"] <= z <= fac["z_max"] and point_in_poly(x, y, fac["poly"]):
            return fac
    return None


# ─── pure row/life logic ────────────────────────────────────────────────────
def sanitize_row(sid: str, row: Any, now_ms: int,
                 row_max_age_s: int = 12) -> Optional[dict]:
    """One positions row -> {x,y,z,health,growth,dino} or None. Refuses a
    non-steam64 key, a non-dict row, non-finite numbers and a stale
    last_updated — the quest tracker's NaN guard plus the read_position_live
    freshness rule, in one place."""
    if not _STEAM64_RE.match(str(sid or "")):
        return None
    if not isinstance(row, dict):
        return None
    # health and growth are REQUIRED, never defaulted: a defaulted 0.0 health
    # reads as a death and a defaulted 0.0 growth reads as a new life — both
    # of which now CLEAR per-life claims, i.e. the generous/exploit direction.
    # A feed hiccup that drops a field must invalidate the row, not reset lives.
    if "health" not in row or "growth" not in row:
        return None
    try:
        x = float(row.get("x")); y = float(row.get("y")); z = float(row.get("z"))
        health = float(row.get("health"))
        growth = float(row.get("growth"))
    except (TypeError, ValueError):
        return None
    for v in (x, y, z, health, growth):
        if v != v or v in (float("inf"), float("-inf")):
            return None
    # last_updated is the row's freshness stamp: absent is tolerated (older
    # feeds), but a PRESENT stamp that cannot be read (junk, inf -> Overflow)
    # invalidates the row — an unreadable stamp must never mean "fresh".
    ts_ms = None
    lu = row.get("last_updated")
    if lu is not None:
        try:
            f = float(lu)
            if f != f or f in (float("inf"), float("-inf")):
                return None
            ts_ms = int(f)
            if ts_ms < 10_000_000_000:  # epoch seconds -> ms
                ts_ms *= 1000
        except (TypeError, ValueError, OverflowError):
            return None
    if ts_ms is not None and (now_ms - ts_ms) > row_max_age_s * 1000:
        return None
    dino = str(row.get("dino") or "")
    return {"x": x, "y": y, "z": z, "health": health, "growth": growth, "dino": dino}


def is_new_life(sig: Any, row: dict) -> bool:
    """Is this pawn a DIFFERENT life from the stored signature? True on a
    species change or a growth fall below the signature (growth only ever
    rises inside one life). Fails CONSERVATIVE: no signature, or an
    indistinguishable adult-for-adult swap, reads as the same life — a missed
    boundary only delays a re-claim, it can never mint one."""
    if not isinstance(sig, dict):
        return False
    sig_dino = str(sig.get("dino") or "")
    if sig_dino and row["dino"] and sig_dino != row["dino"]:
        return True
    try:
        sig_growth = float(sig.get("growth"))
    except (TypeError, ValueError):
        return False
    if sig_growth != sig_growth:
        return False
    return row["growth"] < (sig_growth - GROWTH_DROP_LIFE)


def cooldown_left_ms(until: Any, now_ms: int) -> int:
    """Remaining between-facility cooldown in ms (0 = free). The stored stamp
    is a wall-clock ratchet written only by credits — a death, a new life or a
    zombie reset never clears it (dying to skip the wait is the exploit
    direction). Absent/junk/non-finite/overflowing reads as FREE (a broken
    stamp must never lock a player out — OverflowError included, the
    sanitize_row precedent). Clock-skew bound (refuted 2026-08-21: clamping
    only the READING left a far-future stamp re-clamping to a full window
    forever = a permanent lockout in 2 h slices): a stamp more than TWO
    windows out is broken — read FREE; inside that, the reading is clamped to
    one window, so a clock stepped back mid-cooldown costs at most two
    windows of real waiting and an absurd stamp costs nothing."""
    if COOLDOWN_S <= 0:
        return 0
    try:
        u = float(until)
    except (TypeError, ValueError, OverflowError):
        return 0
    if u != u or u in (float("inf"), float("-inf")):
        return 0
    win_ms = COOLDOWN_S * 1000
    try:
        left = int(u) - int(now_ms)
    except (OverflowError, ValueError):
        return 0
    if left <= 0:
        return 0
    if left > 2 * win_ms:
        return 0
    return min(left, win_ms)


# ─── notify_commands.json writer (the /prime popup surface) ─────────────────
def sanitize_banner_text(value: Any) -> str:
    """EXACTLY the framework producer's shaping (botcore/gamenotify.py): the
    monolith scans '{[^{}]+}' and captures '"text":"([^"]*)"' raw, so {}"\\
    fold to lookalikes, control chars fold to a space, non-ASCII is dropped
    (ensure_ascii escapes would render literally), clip last."""
    folded = str(value or "")
    for bad, stand_in in (("{", "("), ("}", ")"), ('"', "'"), ("\\", "/")):
        folded = folded.replace(bad, stand_in)
    folded = re.sub(r"[\x00-\x1f\x7f]", " ", folded)
    kept = "".join(ch for ch in folded if ord(ch) < 0x7F)
    return " ".join(kept.split())[:240]


def _notify_block(sid: str, text: str) -> str:
    return '{"action":"notify_line","steamid":"%s","text":"%s"}' % (
        sid, sanitize_banner_text(text))


_ACTION_NAMES = ("gen0_zombie", "gen0_unzombie")


def _action_block(action: str, sid: str) -> str:
    """A bare {action, steamid} block for the mod's queue (the transformation
    lane). Deliberately NO text and NO first_ms/next_ms/retries — absent beats
    zero (the gamenotify law). Action is a closed set and the sid is folded to
    digits so no caller can ever break the mod's regex parser."""
    if action not in _ACTION_NAMES:
        return ""
    return '{"action":"%s","steamid":"%s"}' % (action, re.sub(r"[^0-9]", "", str(sid)))


NOTIFY_MAX_READ = 1024 * 1024
NOTIFY_MAX_BLOCKS = 4096


def write_notify_blocks(blocks: list[str], path: str | None = None) -> bool:
    """Append banner blocks to the monolith's durable notify queue with the
    SAME claim-merge-write discipline its own FlushNotifyActions uses:
    atomically claim the file by rename (so the mod cannot read a half-write),
    keep every existing {…} block, append ours, write tmp, rename back.
    Deliberately NO first_ms/next_ms/retries fields — absent beats zero
    (an explicit 0 turns the mod's retry TTL into an instant drop; JL law in
    botcore/gamenotify.py). Never raises; a failed write is logged and returns
    False, never a crashed loop, and it must never block a credit.

    KNOWN RESIDUAL (measured by the 2026-08-21 refutation): the mod's own flush
    is NOT atomic (os.remove then os.rename) and clears its pending list
    unconditionally, so any two producers on this file — the mod already races
    itself — can lose one side's batch when their sub-10 ms critical sections
    overlap; at this lane's write rate (a few writes per exposure) that is on
    the order of 1 % of OUR writes, costs one banner batch on one side, and
    never touches a credit (Mongo). Closing it needs a mod-side atomic flush.
    If a claimed read FAILS we put the queue back and write nothing — writing
    ours-only would DELETE the mod's pending banners (a failed write is a
    delete)."""
    p = path or _notify_path
    if not p or not blocks:
        return False
    staging = p + ".web_gen0_staging"
    tmp = p + ".web_gen0_tmp"
    claimed = False
    try:
        items: list[str] = []
        if os.path.lexists(p) and not os.path.isfile(p):
            logger.warning("gen0 notify: queue path is not a regular file, refusing")
            return False
        try:
            os.replace(p, staging)
            claimed = True
        except FileNotFoundError:
            pass
        if claimed:
            try:
                if os.path.getsize(staging) <= NOTIFY_MAX_READ:
                    with open(staging, "r", encoding="utf-8", errors="replace") as f:
                        existing = f.read()
                    items.extend(re.findall(r"\{[^{}]+\}", existing))
                else:
                    logger.warning("gen0 notify: existing queue oversize, dropped (mod parity)")
            except OSError as e:
                # We hold the mod's queue and cannot read it: give it back
                # untouched and write nothing this tick.
                os.replace(staging, p)
                logger.warning(f"gen0 notify: claimed queue unreadable, restored: {e}")
                return False
        items.extend(blocks)
        if len(items) > NOTIFY_MAX_BLOCKS:
            items = items[-NOTIFY_MAX_BLOCKS:]
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("[" + ",".join(items) + "]")
        os.replace(tmp, p)
        if claimed:
            try:
                os.remove(staging)
            except OSError:
                pass
        return True
    except Exception as e:  # noqa: BLE001 — the loop must survive any file fault
        logger.warning(f"gen0 notify write failed: {e}")
        try:
            if claimed and not os.path.exists(p):
                os.replace(staging, p)
        except OSError:
            pass
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


# ─── persistence (Mongo gen0_state; one doc per steam id) ───────────────────
async def _load_doc(sid: str) -> dict:
    doc = await _db.gen0_state.find_one({"steam_id": sid}, {"_id": 0})
    if not isinstance(doc, dict):
        doc = {"steam_id": sid, "percent": 0, "claims": {}, "life_sig": None,
               "complete_at": None, "updated_at": None}
    doc.setdefault("percent", 0)
    doc.setdefault("claims", {})
    doc.setdefault("life_sig", None)
    doc.setdefault("complete_at", None)
    doc.setdefault("cooldown_until_ms", None)
    return doc


async def _credit_facility_locked(sid: str, fac: dict, row: dict,
                                  now_ms: int | None = None) -> Optional[dict]:
    """Apply one completed exposure. Returns {percent, complete, first}; None
    when this facility is already claimed in this life (the once-per-life
    rule); or {"on_cooldown": True, "left_ms": N} — a READ-ONLY refusal —
    while the between-facility cooldown from the LAST credit is still
    running (owner 2026-08-21). A landed credit stamps the next window in the
    SAME write. The claim gate SELF-HEALS a missed death: if the stored life
    signature says this pawn is a different life, every claim clears first —
    so a backend bounce that forgot an in-flight death only ever DELAYS the
    reset to the moment it matters, here."""
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    doc = await _load_doc(sid)
    claims = dict(doc.get("claims") or {})
    if is_new_life(doc.get("life_sig"), row):
        claims = {}
    if fac["id"] in claims:
        # Same life, already claimed — refresh the signature ratchet only.
        await _db.gen0_state.update_one(
            {"steam_id": sid},
            {"$set": {"life_sig": {"dino": row["dino"], "growth": row["growth"]},
                      "updated_at": now_iso()},
             "$setOnInsert": {"steam_id": sid, "percent": doc["percent"],
                              "claims": claims}},
            upsert=True)
        return None
    cd_left = cooldown_left_ms(doc.get("cooldown_until_ms"), now_ms)
    if cd_left > 0:
        # Another facility paid less than one window ago: this one does not
        # count yet. No doc write — the caller keeps the stay alive and
        # retries the moment the clock passes.
        return {"on_cooldown": True, "left_ms": cd_left}
    try:
        pct = int(doc.get("percent") or 0)
    except (TypeError, ValueError):
        pct = 0
    pct = max(0, min(100, pct))
    new_pct = min(100, pct + PCT_PER_FACILITY)
    claims[fac["id"]] = now_iso()
    first_complete = new_pct >= 100 and not doc.get("complete_at")
    update = {"percent": new_pct, "claims": claims,
              "life_sig": {"dino": row["dino"], "growth": row["growth"]},
              "updated_at": now_iso()}
    if COOLDOWN_S > 0:
        update["cooldown_until_ms"] = now_ms + COOLDOWN_S * 1000
    if first_complete:
        update["complete_at"] = now_iso()
    await _db.gen0_state.update_one(
        {"steam_id": sid}, {"$set": update, "$setOnInsert": {"steam_id": sid}},
        upsert=True)
    return {"percent": new_pct, "complete": new_pct >= 100, "first": first_complete}


async def _credit_facility(sid: str, fac: dict, row: dict,
                           now_ms: int | None = None) -> Optional[dict]:
    async with _state_lock(sid):
        return await _credit_facility_locked(sid, fac, row, now_ms)


# ─── the mod's own JSONL records (death_causes.log / gen0_zombie_events.log) ─
def _tail_new_rows(p: Optional[str], cursor: dict[str, Any],
                   label: str) -> list[dict]:
    """Shared JSONL tail. First call starts at END of file (history is never
    replayed); each later call consumes only NEW bytes, capped per tick; a
    truncated or rotated file restarts from 0; a partial last line waits in
    `carry` for its newline. Returns parsed dict rows only (bad JSON and
    non-dict lines are skipped, one bad line never stops the tail). Sync,
    bounded, never raises."""
    out: list[dict] = []
    if not p:
        return out
    try:
        size = os.path.getsize(p)
    except OSError:
        return out
    try:
        off = cursor["offset"]
        if off is None or off > size:
            # first sight (start at the end) or truncation/rotation (restart)
            cursor["offset"] = size if off is None else 0
            cursor["carry"] = b""
            if off is None:
                return out
            off = 0
        if size == off:
            return out
        with open(p, "rb") as f:
            f.seek(off)
            chunk = f.read(min(size - off, DEATHLOG_MAX_READ))
        cursor["offset"] = off + len(chunk)
        buf = cursor["carry"] + chunk
        lines = buf.split(b"\n")
        cursor["carry"] = lines.pop()  # partial last line waits for its end
        import json as _json
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = _json.loads(ln.decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001 — one bad line never stops the tail
                continue
            if isinstance(d, dict):
                out.append(d)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"gen0 {label} read: {e}")
    return out


def _read_new_deaths(path: str | None = None) -> list[dict]:
    """New death_causes.log lines (JSONL, one line per GENUINE death:
    ClassifyDeathCause fires on the first health<=0 that is NOT a restore
    transient — the mod's own record keeper, so the judge reads the same
    stream). Validated rows only."""
    out: list[dict] = []
    for d in _tail_new_rows(path or _deathlog_path, _deathlog, "deathlog"):
        sid = str(d.get("sid") or "").strip()
        if not _STEAM64_RE.match(sid):
            continue
        try:
            growth = float(d.get("growth"))
        except (TypeError, ValueError):
            continue
        if growth != growth:
            continue
        out.append({"sid": sid, "dino": str(d.get("dino") or ""), "growth": growth})
    return out


def _read_new_events(path: str | None = None) -> list[dict]:
    """New gen0_zombie_events.log lines — the mod half's transformation record:
    {"event":"on"|"off","sid":…,"reason":…}. Validated rows only; an unknown
    event name or a non-steam64 sid is dropped, never applied."""
    out: list[dict] = []
    for d in _tail_new_rows(path or _eventlog_path, _eventlog, "eventlog"):
        sid = str(d.get("sid") or "").strip()
        ev = str(d.get("event") or "").strip()
        if ev not in ("on", "off") or not _STEAM64_RE.match(sid):
            continue
        out.append({"event": ev, "sid": sid, "reason": str(d.get("reason") or "")})
    return out


async def _deathlog_tick() -> None:
    """Apply new death lines: a death ENDS any stay and RATCHETS the stored life
    signature to the growth AT DEATH. It does NOT clear claims — the claim gate
    judges a new life against that signature, so: a respawn at spawn growth
    reads as a new life (claims clear), while a park→redeem of the SAME dino
    (same species, growth intact) stays one life and cannot re-farm. No upsert:
    a player with no gen0 doc gains nothing by dying.

    NOT a zombie reset (2026-08-22 park/relog survival): this line is written
    on the mod's health<=0 latch, which a park kill, a safelog and a plain
    logout all reach — resetting here dropped a walking zombie's bar to 0
    and let the cycle re-farm. The mod judges the NEXT living pawn (species
    / growth) and writes "off" only for a real new life; the sweep's own
    new-life belt is the web-side backstop."""
    deaths = await asyncio.to_thread(_read_new_deaths)
    for d in deaths:
        try:
            _dwell.pop(d["sid"], None)
            res = await _db.gen0_state.update_one(
                {"steam_id": d["sid"]},
                {"$set": {"life_sig": {"dino": d["dino"], "growth": d["growth"]},
                          "updated_at": now_iso()}})
            if getattr(res, "modified_count", 0):
                logger.info(f"gen0 death recorded sid={d['sid']} dino={d['dino']} "
                            f"growth={d['growth']:.3f}")
        except Exception as e:  # noqa: BLE001 — next line still applies
            logger.warning(f"gen0 death apply {d['sid']}: {e}")


# ─── the transformation state machine (web half) ────────────────────────────
def _sig_of(row: Any) -> Optional[dict]:
    """Life signature of a sanitized positions row, or None for no row."""
    if not isinstance(row, dict):
        return None
    return {"dino": row.get("dino") or "", "growth": row.get("growth")}


async def _zombie_on(sid: str, reason: str = "") -> None:
    """The mod acked a transformation ('on' event): mark the doc zombie_active
    and freeze the life signature the zombie is living — taken from the pawn's
    most recent ALIVE row, NEVER from the stored life_sig ratchet (which, for a
    persisted-percent player, describes the life that earned the bar, not the
    one being transformed). No row known yet → None; the sweep captures it on
    the first alive sighting. Idempotent (an active doc is left alone, so
    duplicate/reack events cost one read); NO upsert — an event for a sid with
    no gen0 doc mints nothing.

    PARK SURVIVAL (2026-08-22): a parked zombie's redeem re-arms the mod hold
    and acks "on" (reason=restore) — by then this doc was reset to 0 by the
    park's own "off". A walking zombie IS 100 %: lift the bar back when it
    sits lower so the panel locks and the sweep's new-life belt watches the
    doc again. Only the mod writes "on", so the lift can never be forged.
    A RESTORE ack never seeds the signature from the last pass: that row can
    still be the animal the player walked BEFORE the redeem (a species
    change one tick later would read as a new life and reset the zombie it
    just re-armed); the sweep captures the redeemed pawn on its first alive
    sighting instead."""
    doc = await _db.gen0_state.find_one({"steam_id": sid}, {"_id": 0})
    if not isinstance(doc, dict) or doc.get("zombie_active"):
        return
    sig = None if reason == "restore" else _sig_of(_last_alive.get(sid))
    upd: dict[str, Any] = {"zombie_active": True, "zombie_at": now_iso(),
                           "zombie_life_sig": sig, "updated_at": now_iso()}
    try:
        pct = int(doc.get("percent") or 0)
    except (TypeError, ValueError):
        pct = 0
    lifted = pct < 100
    if lifted:
        upd["percent"] = 100
        if not doc.get("complete_at"):
            upd["complete_at"] = now_iso()
    await _db.gen0_state.update_one({"steam_id": sid}, {"$set": upd})
    _zombify_next.pop(sid, None)
    logger.info(f"gen0 zombie ON sid={sid} reason={reason or '-'} "
                f"sig={'captured' if sig else 'pending'}"
                f"{' bar_lifted_from=' + str(pct) if lifted else ''}")


async def _zombie_reset(sid: str, reason: str) -> bool:
    """The zombie's death consumed the infection: percent back to 0, claims and
    the completion stamp cleared, the hold flag dropped — the next life is
    clean and the cycle can restart. The zombie_active filter is IN the query,
    so the reset applies exactly once no matter how many signals describe the
    same boundary (mod 'off' event — death/command/expired — or the sweep's
    new-life belt). Park uses reset_for_dino_switch because it is authoritative
    even when the earlier active acknowledgement was missed."""
    res = await _db.gen0_state.update_one(
        {"steam_id": sid, "zombie_active": True},
        {"$set": {"percent": 0, "claims": {}, "complete_at": None,
                  "zombie_active": False, "zombie_reset_at": now_iso(),
                  "updated_at": now_iso()}})
    if getattr(res, "modified_count", 0):
        _zombify_next.pop(sid, None)
        logger.info(f"gen0 zombie RESET sid={sid} reason={reason}")
        return True
    return False


async def reset_for_dino_switch(sid: str, reason: str = "park") -> bool:
    """Reset GEN-0 at an authoritative dinosaur-switch boundary.

    This deliberately does not require ``zombie_active``.  The mod's ``on``
    acknowledgement and its later ``off`` event are a lossy JSONL lane; if the
    backend missed ``on``, the old active-only reset was a no-op and the 100%
    bar infected the next, unrelated dinosaur.  A confirmed park is stronger
    evidence than that flag, so it clears progress, claims, and both life
    signatures while preserving the anti-skip facility cooldown.

    No state document is minted, and an already-clean document is a true no-op.
    That makes retries and the independent mod ``off:park`` fallback safe.
    """
    sid = str(sid or "").strip()
    if not _STEAM64_RE.fullmatch(sid):
        return False
    # Never let a new pawn inherit a previous pawn's in-memory stay or alive
    # signature, even when Mongo is temporarily unavailable.
    _dwell.pop(sid, None)
    _last_alive.pop(sid, None)
    _zombify_next.pop(sid, None)
    async with _state_lock(sid):
        return await _reset_for_dino_switch_locked(sid, reason)


async def _reset_for_dino_switch_locked(sid: str, reason: str) -> bool:
    doc = await _db.gen0_state.find_one({"steam_id": sid}, {"_id": 0})
    if not isinstance(doc, dict):
        return False
    try:
        pct = int(doc.get("percent") or 0)
        percent_dirty = pct != 0
    except (TypeError, ValueError, OverflowError):
        pct = 0
        percent_dirty = True
    dirty = (percent_dirty or bool(doc.get("claims")) or
             doc.get("complete_at") is not None or
             bool(doc.get("zombie_active")) or
             doc.get("life_sig") is not None or
             doc.get("zombie_life_sig") is not None)
    if not dirty:
        return False
    stamp = now_iso()
    res = await _db.gen0_state.update_one(
        {"steam_id": sid},
        {"$set": {"percent": 0, "claims": {}, "complete_at": None,
                  "life_sig": None, "zombie_active": False,
                  "zombie_at": None, "zombie_life_sig": None,
                  "zombie_reset_at": stamp,
                  "dino_switch_reset_at": stamp, "updated_at": stamp}})
    if getattr(res, "modified_count", 0):
        _zombify_next.pop(sid, None)
        logger.info(f"gen0 dino-switch RESET sid={sid} reason={reason or '-'}")
        return True
    return False


async def _events_tick() -> None:
    """Apply the mod half's transformation events. One bad apply never stops
    the rest; the readers validated shape already."""
    events = await asyncio.to_thread(_read_new_events)
    for ev in events:
        try:
            if ev["event"] == "on":
                await _zombie_on(ev["sid"], ev.get("reason") or "")
            else:
                reason = ev.get("reason") or "-"
                if reason == "park":
                    # Backup for the direct reset in vault._run_park.  Unlike
                    # death/expiry, park is an authoritative dino switch even
                    # when the earlier zombie-on acknowledgement was missed.
                    await reset_for_dino_switch(ev["sid"], "off:park")
                else:
                    await _zombie_reset(ev["sid"], "off:" + reason)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"gen0 event apply {ev.get('sid')}: {e}")


async def _zombify_sweep(now_mono: float | None = None) -> list[str]:
    """One bounded pass over the docs at 100 % whose players are ONLINE AND
    ALIVE right now (the last tracker pass's sanitized rows):
      * zombie_active + a NEW life observed (species change or growth fall vs
        zombie_life_sig) → the zombie died while we weren't looking → RESET.
      * not yet acked → enqueue gen0_zombie, at most once per
        GEN0_ZOMBIFY_RETRY_S per sid — this back-fills everyone who hit 100 %
        before the mod half armed, and self-heals a lost ack (the mod re-emits
        'on' for an already-held sid). Returns the action blocks so they ride
        the SAME notify write as this tick's banners (one file op per tick).
    The retry map is pruned to currently-eligible sids, so it stays bounded."""
    if not _last_alive:
        return []
    now_mono = time.monotonic() if now_mono is None else now_mono
    try:
        cursor = _db.gen0_state.find(
            {"steam_id": {"$in": list(_last_alive.keys())},
             "percent": {"$gte": 100}},
            {"_id": 0, "steam_id": 1, "percent": 1,
             "zombie_active": 1, "zombie_life_sig": 1})
        docs = await cursor.to_list(length=2048)
    except Exception as e:  # noqa: BLE001 — Mongo down: quiet tick, retry next
        logger.warning(f"gen0 zombify query: {e}")
        return []
    blocks: list[str] = []
    eligible: set[str] = set()
    for doc in docs or []:
        try:
            sid = str(doc.get("steam_id") or "")
            row = _last_alive.get(sid)
            if row is None:
                continue
            if doc.get("zombie_active"):
                sig = doc.get("zombie_life_sig")
                if not isinstance(sig, dict):
                    # Ack landed before any row was known: THIS sighting is the
                    # zombie's life. Capture it; never judge on this pass.
                    await _db.gen0_state.update_one(
                        {"steam_id": sid, "zombie_active": True},
                        {"$set": {"zombie_life_sig": _sig_of(row),
                                  "updated_at": now_iso()}})
                    logger.info(f"gen0 zombie sig captured sid={sid}")
                    continue
                if is_new_life(sig, row):
                    await _zombie_reset(sid, "new_life")
                continue
            if not ZOMBIFY_ON:
                continue
            eligible.add(sid)
            nxt = _zombify_next.get(sid)
            if nxt is not None and now_mono < nxt:
                continue
            _zombify_next[sid] = now_mono + ZOMBIFY_RETRY_S
            blocks.append(_action_block("gen0_zombie", sid))
            logger.info(f"gen0 zombify enqueued sid={sid} reason=backfill")
        except Exception as e:  # noqa: BLE001 — one bad doc never kills the pass
            logger.warning(f"gen0 zombify doc fault: {e}")
    for sid in list(_zombify_next.keys()):
        if sid not in eligible:
            _zombify_next.pop(sid, None)
    return blocks


# ─── the tracker tick ───────────────────────────────────────────────────────
async def _tracker_tick(now_mono: float | None = None,
                        now_ms: int | None = None) -> list[str]:
    """One pass: read fresh positions, advance every dwell, credit completed
    exposures, and return the banner blocks to deliver (the caller writes them
    in ONE file operation). Every per-player fault is contained row-locally.
    now_mono paces dwell; now_ms is the WALL clock the persisted
    between-facility cooldown is judged against (both injectable for tests)."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    banners: list[str] = []
    _last_alive.clear()
    positions = await asyncio.to_thread(game_ipc.read_players_positions_fresh, 15)
    if not isinstance(positions, dict):
        # Server down / feed frozen: no dwell progress (and an empty alive map
        # keeps the zombify sweep quiet), and stays older than RESET_S will
        # prune themselves on the next live pass.
        return banners
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    seen: set[str] = set()

    for key, raw in positions.items():
        try:
            sid = ""
            if isinstance(raw, dict):
                sid = str(raw.get("steamid") or "").strip()
            if not sid:
                sid = str(key or "").strip()
            row = sanitize_row(sid, raw, now_ms)
            if row is None:
                continue
            seen.add(sid)
            state = _dwell.get(sid)

            # health<=0 in the feed ends any stay and NOTHING ELSE: the mod
            # publishes health<=0 rows for LIVING pawns too (restore grace up to
            # 120 s, entomb transients — lineage main.full L18208-18262), so
            # it is never a death signal here. Deaths come from the mod's own
            # death_causes.log (see _deathlog_tick).
            if row["health"] <= 0.0:
                if state is not None:
                    _dwell.pop(sid, None)
                continue
            if len(_last_alive) < DWELL_MAP_MAX:
                _last_alive[sid] = row       # cleared every pass: online+alive only

            fac = facility_at(row["x"], row["y"], row["z"])

            if state is not None and fac is not None and state["fid"] != fac["id"]:
                # Walked from one facility straight into another: the old stay
                # ends, a new one starts. One dwell per player at a time — no
                # stay can ever pay twice.
                state = None
                _dwell.pop(sid, None)

            if state is None:
                if fac is None:
                    continue
                if len(_dwell) >= DWELL_MAP_MAX:
                    continue  # hard bound; next tick catches them
                doc = await _load_doc(sid)
                try:
                    complete = int(doc.get("percent") or 0) >= 100
                except (TypeError, ValueError):
                    complete = False
                claims = doc.get("claims") or {}
                already = fac["id"] in claims and not is_new_life(doc.get("life_sig"),
                                                                  row)
                # A fully mutated player still gets a (silent) dwell record so
                # the doc is read ONCE per visit, not once per tick.
                cd_left = cooldown_left_ms(doc.get("cooldown_until_ms"), now_ms)
                _dwell[sid] = state = {
                    "fid": fac["id"], "fac": fac,
                    "enter_mono": now_mono, "last_in_mono": now_mono,
                    "banners": 0, "next_banner_mono": now_mono + BANNER_MIN_GAP_S,
                    "claimable": (not already) and (not complete),
                    # wall-clock moment this stay may credit (0 = free now)
                    "cd_until_ms": (now_ms + cd_left) if cd_left > 0 else 0,
                }
                if state["claimable"] and BANNERS_ON:
                    if cd_left > 0:
                        # In cooldown the honest banner is the countdown, not
                        # the "stay to get infected" invitation.
                        banners.append(_notify_block(sid, BANNER_COOLDOWN.format(
                            mins=max(1, (cd_left + 59_999) // 60_000))))
                    else:
                        banners.append(_notify_block(sid, BANNER_ENTRY))
                continue

            if fac is None:
                # Outside: hysteresis — a gap shorter than RESET_S keeps the
                # stay (campguard's load-bearing rule: stepping out for a
                # second must not restart the 30 s); longer prunes it.
                if (now_mono - state["last_in_mono"]) > RESET_S:
                    _dwell.pop(sid, None)
                continue

            state["last_in_mono"] = now_mono
            elapsed = now_mono - state["enter_mono"]

            if not state["claimable"]:
                continue  # once-per-life: silent ground until the next life

            if elapsed < DWELL_S:
                if (BANNERS_ON and state["banners"] < 2
                        and now_mono >= state["next_banner_mono"]
                        and now_ms >= state.get("cd_until_ms", 0)):
                    # In cooldown the pool lines ("stay inside to continue the
                    # infection") would be a lie — the entry countdown banner
                    # already told the truth.
                    banners.append(_notify_block(sid, _rng.choice(BANNER_POOL)))
                    state["banners"] += 1
                    state["next_banner_mono"] = now_mono + max(
                        BANNER_MIN_GAP_S, DWELL_S / 3.0)
                continue

            if now_ms < state.get("cd_until_ms", 0):
                # Dwell satisfied but the between-facility cooldown is still
                # running: HOLD the stay (no doc I/O, claimable stays up) so a
                # player camping through expiry pays the moment it passes —
                # never forced to leave and re-enter.
                continue

            # Exposure complete — credit exactly once. A Mongo fault leaves
            # `claimable` standing so the next tick retries; success latches it
            # off, and the claims map makes a repeat a no-op either way.
            try:
                result = await _credit_facility(sid, state["fac"], row, now_ms)
            except Exception as e:  # noqa: BLE001 — Mongo hiccup: retry next tick
                logger.warning(f"gen0 credit retry {sid}: {e}")
                continue
            if isinstance(result, dict) and result.get("on_cooldown"):
                # Authoritative refusal (the doc's clock outran our entry
                # read): adopt it and keep the stay claimable.
                state["cd_until_ms"] = now_ms + int(result.get("left_ms") or 0)
                continue
            state["claimable"] = False
            if result is None:
                continue  # raced an existing claim — no credit, no banner
            if BANNERS_ON:
                banners.append(_notify_block(
                    sid, BANNER_CREDIT.format(pct=result["percent"])))
                if result["first"]:
                    banners.append(_notify_block(sid, BANNER_COMPLETE))
            if result["complete"] and ZOMBIFY_ON:
                # The bar just completed: the transformation is owed NOW —
                # same batch as the MUTACION COMPLETA banner. The retry gate
                # is stamped so the sweep repeats it only if the ack never
                # arrives.
                banners.append(_action_block("gen0_zombie", sid))
                _zombify_next[sid] = now_mono + ZOMBIFY_RETRY_S
                logger.info(f"gen0 zombify enqueued sid={sid} reason=complete")
            logger.info(f"gen0 credit sid={sid} fac={state['fid']} "
                        f"pct={result['percent']} complete={result['complete']}")
        except Exception as e:  # noqa: BLE001 — one bad row never kills the pass
            logger.warning(f"gen0 row fault: {e}")

    # Players gone from the feed entirely: prune once their absence outlives
    # the hysteresis window (logout mid-exposure, crash, server restart).
    for sid in list(_dwell.keys()):
        if sid not in seen and (now_mono - _dwell[sid]["last_in_mono"]) > RESET_S:
            _dwell.pop(sid, None)

    return banners


async def gen0_tracker_loop() -> None:
    """Background loop, guarded like every other backend loop — one bad tick
    (missing file, transient Mongo fault) never kills it."""
    if not GEN0_ENABLED:
        logger.info("gen0 tracker DISABLED (GEN0_ENABLED=0)")
        return
    logger.info(f"gen0 tracker ARMED facilities={len(FACILITIES)} dwell_s={DWELL_S} "
                f"tick_s={TICK_S} pct_per={PCT_PER_FACILITY} banners={BANNERS_ON} "
                f"cooldown_s={COOLDOWN_S}")
    logger.info(f"gen0 zombify {'ARMED' if ZOMBIFY_ON else 'DISABLED'} "
                f"retry_s={ZOMBIFY_RETRY_S} events={os.path.basename(_eventlog_path or 'gen0_zombie_events.log')}")
    while True:
        try:
            await _deathlog_tick()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"gen0 deathlog tick: {e}")
        try:
            await _events_tick()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"gen0 events tick: {e}")
        try:
            banners = await _tracker_tick()
            try:
                banners.extend(await _zombify_sweep())
            except Exception as e:  # noqa: BLE001
                logger.warning(f"gen0 zombify sweep: {e}")
            if banners:
                await asyncio.to_thread(write_notify_blocks, banners)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"gen0 tracker tick: {e}")
        await asyncio.sleep(TICK_S)


# ─── the website endpoints ──────────────────────────────────────────────────
# /gen0/facilities (public geometry for the site map) existed for a few hours
# on 2026-08-21 and was REMOVED the same day on the owner's order ("players
# are finding it easily"): nothing may serve the polygons any more — the
# zones are found in-world. The literals above stay module-private, judged
# only by the tracker.
def build_router(current_user_dep: Callable) -> APIRouter:
    """The real routes, with the auth dependency handed in (battle_pass's
    configure pattern — nothing here imports server.py)."""
    r = APIRouter()

    @r.get("/gen0/contamination")
    async def gen0_contamination(user=Depends(current_user_dep)):
        sid = str((user or {}).get("steam_id") or "").strip()
        if not _STEAM64_RE.match(sid):
            # Signed in but Steam not linked: an honest empty bar, never a 500.
            return {"percent": 0, "complete": False, "linked": False,
                    "claims": {}, "facilities_total": len(FACILITIES),
                    "cooldown_s": 0, "cooldown_total_s": COOLDOWN_S,
                    "updated_at": None}
        try:
            doc = await _load_doc(sid)
        except Exception as e:  # noqa: BLE001 — Mongo down: a named 503, not a 500
            logger.warning(f"gen0 contamination read {sid}: {e}")
            raise HTTPException(status_code=503, detail="gen0 no disponible")
        try:
            pct = max(0, min(100, int(doc.get("percent") or 0)))
        except (TypeError, ValueError):
            pct = 0
        # Seconds until the next facility can pay (the site's countdown;
        # ceiling so the timer never reads 0 while the gate still refuses).
        # Belt: a display field must never be able to 500 the endpoint.
        try:
            cd_ms = cooldown_left_ms(doc.get("cooldown_until_ms"),
                                     int(time.time() * 1000))
        except Exception:  # noqa: BLE001
            cd_ms = 0
        return {"percent": pct, "complete": bool(doc.get("complete_at")),
                "linked": True, "claims": doc.get("claims") or {},
                "facilities_total": len(FACILITIES),
                "cooldown_s": (cd_ms + 999) // 1000,
                "cooldown_total_s": COOLDOWN_S,
                "updated_at": doc.get("updated_at")}

    return r
