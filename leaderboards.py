"""
Leaderboards — La Isla Nublar. 4 rankings (Overall / Kills / Misiones / Tiempo),
one season per UTC calendar month (mirrors battle_pass so both roll over
together).

Prizes (top 3 of the OVERALL leaderboard, awarded once on season rollover):
  🥇 1st  → 5,000,000 PrimeMeat  +  the "Supernova" glitch skin
  🥈 2nd  → 3,000,000 PrimeMeat  +  the "Supernova" glitch skin
  🥉 3rd  → 1,000,000 PrimeMeat  +  the "Supernova" glitch skin

A COSMETIC RIDES A CURRENCY PRIZE, it never replaces one (owner order
2026-08-16: "add the glitch skin ... to the 1st place leaderboard", an ADD;
widened 2026-08-18 to "supernova for 123 place in leaderboard" -- the whole
podium wears it, and the PrimeMeat ladder is still untouched).
The skin ladder is a SEPARATE table from PRIZE_TABLE on purpose — the two are
paid by two independent per-rank claim markers on the award receipt, so a
crash between them resumes the unpaid half and neither can ever pay twice.

Composite Overall score:
  score = kills*100 + quests*50 + playtime_hours*20

Data lives in `db.leaderboard_stats`, one row per user per season:
  {
    id, user_id, season_id,       # (user_id, season_id) is the logical key
    kills_month, deaths_month,    # PVP kills/deaths from game_telemetry's kill queue
    quests_month,                 # bumped on every successful quest claim
    playtime_seconds_month,       # bumped by the verified passive-payout hook
    score,                        # denormalised composite, recomputed atomically
    updated_at,
  }
All-time counters ride on `db.users` (lb_kills_all / lb_deaths_all /
lb_quests_all / lb_playtime_seconds_all) so they never need cross-season
aggregation.

This module is PURE (stdlib only — no motor/FastAPI) so backend/tests_local can
import and exercise every decision in it without Mongo; server.py owns all I/O.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import glitch_catalog  # stdlib-pure sibling — safe for this module's purity rule

# ─── Rewards (PrimeMeat = the site's `coins`) ───────────────────────────────
PRIZE_TABLE = {1: 5_000_000, 2: 3_000_000, 3: 1_000_000}

# ─── Cosmetic riders (2026-08-16, owner order) ──────────────────────────────
# Rank -> glitch design id granted ON TOP of that rank's PrimeMeat. The whole
# podium wears "Supernova" — the owner's own render-proven payload 2 (pattern 2
# / variation 8), which he handed over as the CustomizerData for this prize.
# A rank absent here simply has no skin; the currency ladder is unchanged.
#
# ★ OWNER ORDER 2026-08-18: "supernova for 123 place in leaderboard". It was
#   rank 1 alone from 2026-08-16. Ranks 2 and 3 cost NO new machinery: the
#   rollover pays per rank behind its own claim marker (`paid_skin_ranks`), so
#   three riders are three independent claims, and a season already mid-flight
#   when this lands keeps paying off its stored receipt exactly as written.
#
# ★ It is granted, never *reserved*: supernova is also a crate drop and the
#   Battle Pass apex rider, so this table is a REWARD SURFACE, not an
#   exclusivity claim. If a rank's id ever needs to be exclusive, that is the
#   design's `bp_exclusive` flag in glitch_catalog (what "constelacion for
#   battlepass only" did to the pink design), never a property of this table.
PRIZE_SKIN_BY_RANK = {1: "supernova", 2: "supernova", 3: "supernova"}


def _validate_prize_skins() -> None:
    """Refuse to import on a prize pointing at a design that does not exist.

    Deliberately NOT `assert` (python -O strips asserts) and deliberately at
    import: a season rollover fires once a month from a background loop, so a
    typo'd id would otherwise sit silent for weeks and then hand the champion
    nothing at all."""
    for rank, gid in PRIZE_SKIN_BY_RANK.items():
        if rank not in PRIZE_TABLE:
            raise RuntimeError(f"[lb] prize skin at rank {rank} has no prize rank")
        if gid not in glitch_catalog.GLITCH_BY_ID:
            raise RuntimeError(f"[lb] prize skin {gid!r} is not in the glitch catalog")


_validate_prize_skins()

# ─── Score weights (Overall) ────────────────────────────────────────────────
WEIGHT_KILL = 100
WEIGHT_QUEST = 50
WEIGHT_PLAYTIME_HOUR = 20

TOP_N = 30  # rows the hub returns per board


def compute_score(kills_month: int, quests_month: int, playtime_seconds_month: int) -> int:
    hours = int(playtime_seconds_month) / 3600.0
    return int(int(kills_month) * WEIGHT_KILL
               + int(quests_month) * WEIGHT_QUEST
               + hours * WEIGHT_PLAYTIME_HOUR)


# ─── Season helpers (UTC calendar month, same convention as battle_pass) ────
def season_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def season_bounds(sid: str) -> tuple[datetime, datetime]:
    y, m = [int(x) for x in sid.split("-")]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return start, end


def previous_season_id(sid: str) -> str:
    y, m = [int(x) for x in sid.split("-")]
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def seconds_remaining(sid: str, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    _, end = season_bounds(sid)
    return max(0, int((end - now).total_seconds()))


# ─── Metric list (matches the frontend tabs) ────────────────────────────────
KIND_TO_FIELD = {
    "overall": "score",
    "kills": "kills_month",
    "quests": "quests_month",
    "playtime": "playtime_seconds_month",
}

VALID_KINDS = list(KIND_TO_FIELD.keys())


def board_sort(kind: str) -> list[tuple[str, int]]:
    """Deterministic sort: metric desc, then user_id asc so ties are stable
    across reads (a tied pair must never swap between refreshes)."""
    return [(KIND_TO_FIELD[kind], -1), ("user_id", 1)]


def rank_filter(kind: str, sid: str, value: int, user_id: str) -> dict:
    """Mongo filter counting rows strictly AHEAD of (value, user_id) under
    board_sort(kind). rank = count(this filter) + 1."""
    field = KIND_TO_FIELD[kind]
    return {
        "season_id": sid,
        "$or": [
            {field: {"$gt": value}},
            {field: value, "user_id": {"$lt": user_id}},
        ],
    }


def display_value(kind: str, row: dict) -> dict:
    """Return {primary, secondary} strings for the leaderboard card."""
    if kind == "kills":
        return {"primary": f"{int(row.get('kills_month') or 0):,}", "secondary": "kills"}
    if kind == "quests":
        return {"primary": f"{int(row.get('quests_month') or 0):,}", "secondary": "misiones"}
    if kind == "playtime":
        secs = int(row.get("playtime_seconds_month") or 0)
        h = secs // 3600
        m = (secs % 3600) // 60
        return {"primary": f"{h}h {m:02d}m", "secondary": "en el servidor"}
    return {"primary": f"{int(row.get('score') or 0):,}", "secondary": "puntos"}


def public_row(kind: str, row: dict, user: Optional[dict], rank: int) -> dict:
    """Wire shape for one ranked row. Personas only — no SteamID64 and no
    internal fields ever leave here; `user_id` is the site's own opaque id and
    is what the frontend uses to mark the viewer's row."""
    user = user or {}
    kills_all = int(user.get("lb_kills_all") or 0)
    deaths_all = int(user.get("lb_deaths_all") or 0)
    return {
        "rank": int(rank),
        "user_id": row.get("user_id"),
        "name": user.get("persona_name") or "Cazador",
        "avatar": user.get("avatar") or None,
        "kills_month": int(row.get("kills_month") or 0),
        "deaths_month": int(row.get("deaths_month") or 0),
        "quests_month": int(row.get("quests_month") or 0),
        "playtime_seconds_month": int(row.get("playtime_seconds_month") or 0),
        "score": int(row.get("score") or 0),
        "kills_all": kills_all,
        "deaths_all": deaths_all,
        "kd_ratio": round(kills_all / max(1, deaths_all), 2),
        "display": display_value(kind, row),
    }


# ─── Atomic bump (Mongo update pipeline, built pure so tests can pin it) ────
_BUMPABLE = ("kills_month", "deaths_month", "quests_month", "playtime_seconds_month")


def bump_pipeline(inc: dict, row_id: str, now_iso: str) -> list:
    """Update pipeline that adds `inc` deltas and recomputes `score` in the
    SAME atomic update, so a lost race can never leave score stale. Works for
    upsert-inserts too ($ifNull covers the missing-field first write).
    `inc` keys must be in _BUMPABLE; non-positive-int deltas are refused here
    (the dangerous direction — a negative bump could mint rank)."""
    fields = {}
    for k in _BUMPABLE:
        d = inc.get(k, 0)
        if d:
            if not isinstance(d, int) or d < 0:
                raise ValueError(f"bad bump {k}={d!r}")
            fields[k] = {"$add": [{"$ifNull": [f"${k}", 0]}, int(d)]}
        else:
            fields[k] = {"$ifNull": [f"${k}", 0]}
    unknown = set(inc) - set(_BUMPABLE)
    if unknown:
        raise ValueError(f"unknown bump fields {sorted(unknown)}")
    return [{"$set": {
        **fields,
        "id": {"$ifNull": ["$id", row_id]},
        "score": {"$toInt": {"$add": [
            {"$multiply": [fields["kills_month"], WEIGHT_KILL]},
            {"$multiply": [fields["quests_month"], WEIGHT_QUEST]},
            {"$multiply": [{"$divide": [fields["playtime_seconds_month"], 3600]}, WEIGHT_PLAYTIME_HOUR]},
        ]}},
        "updated_at": now_iso,
    }}]


def seed_pipeline(seed: dict, row_id: str, now_iso: str) -> list:
    """Backfill pipeline: raise each field to AT LEAST `seed` ($max semantics),
    never lowering live-accrued values — re-running the backfill is therefore
    idempotent and can never double-count. Score recomputed atomically."""
    fields = {}
    for k in _BUMPABLE:
        s = int(seed.get(k, 0) or 0)
        if s < 0:
            raise ValueError(f"bad seed {k}={s!r}")
        fields[k] = {"$max": [{"$ifNull": [f"${k}", 0]}, s]}
    return [{"$set": {
        **fields,
        "id": {"$ifNull": ["$id", row_id]},
        "score": {"$toInt": {"$add": [
            {"$multiply": [fields["kills_month"], WEIGHT_KILL]},
            {"$multiply": [fields["quests_month"], WEIGHT_QUEST]},
            {"$multiply": [{"$divide": [fields["playtime_seconds_month"], 3600]}, WEIGHT_PLAYTIME_HOUR]},
        ]}},
        "updated_at": now_iso,
    }}]


# ─── Backfill parsers (transactions → measured playtime) ────────────────────
# _credit_playtime writes "PrimeMeat por tiempo de juego (Nx)" (optionally
# "… · <event> x2" appended); N = paid 240s cycles of VERIFIED in-game time.
_RX_PLAYTIME_TX = re.compile(r"^PrimeMeat por tiempo de juego \((\d+)x\)")


def playtime_tx_cycles(description: str) -> int:
    """Paid cycle count from a passive-payout transaction label, 0 if the label
    is not one (never raises — backfill must survive any historical row)."""
    m = _RX_PLAYTIME_TX.match(str(description or ""))
    if not m:
        return 0
    try:
        n = int(m.group(1))
    except ValueError:
        return 0
    return n if 0 < n < 100_000 else 0


# ─── Season rollover awards ─────────────────────────────────────────────────
def plan_awards(top_rows: list) -> list[dict]:
    """[{rank, user_id, prize, skin}] for the top rows of a FINISHED season's
    overall board. Rows must already be sorted by board_sort('overall');
    zero-score rows never win a prize; fewer than 3 scorers = fewer prizes
    (never raises). `skin` is None on a rank with no cosmetic rider — the key is
    ALWAYS present so a receipt written by an older build and one written by
    this build read the same way at payout time."""
    out = []
    for i, row in enumerate(list(top_rows)[:3]):
        rank = i + 1
        if int((row or {}).get("score") or 0) <= 0:
            break
        uid = (row or {}).get("user_id")
        if not uid:
            continue
        out.append({"rank": rank, "user_id": uid, "prize": PRIZE_TABLE[rank],
                    "skin": PRIZE_SKIN_BY_RANK.get(rank)})
    return out


def award_tx_label(sid: str, rank: int) -> str:
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")
    return f"{medal} Premio Clasificación {sid} — {rank}º lugar".strip()


def award_skin_source(sid: str, rank: int) -> str:
    """`source` stamped on the granted reward_skins row — the same sentence the
    player sees on the card in their inventory, so a skin's provenance is
    readable without cross-referencing a transaction."""
    return f"Clasificación {sid} — {rank}º lugar"


def prize_skin_cards() -> dict:
    """{rank_str: card} for the public hub — the PUBLIC view of each prize
    skin: name, subtitle, accent and colour-proximity strip.

    A glitch card is a NAME + COLOUR PROXIMITY, never a picture (fleet order
    2026-08-11) and never a payload: `public_view` forces `image` to "" and
    emits proximity hexes that fold every negative channel to #000000, so the
    paid recipe cannot be read back off this wire by a signed-out visitor."""
    out = {}
    for rank, gid in PRIZE_SKIN_BY_RANK.items():
        g = glitch_catalog.GLITCH_BY_ID.get(gid)
        if not g:  # unreachable past _validate_prize_skins; fail soft, not 500
            continue
        out[str(rank)] = glitch_catalog.public_view(g)
    return out
