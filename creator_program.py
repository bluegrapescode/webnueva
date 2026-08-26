"""
Creator Program — INDEPENDENT of kills / quests / XP / points.
Uses ONLY PrimeMeat (users.coins) and unlocks an exclusive skin at 100 validated referrals.

Rules enforced by this module:
- A user may support ANY number of creators, but each creator's code exactly ONCE
  (unique index on referrals (referred_user_id, creator_id)) - owner order 2026-08-18:
  "users should support anyone with the code but only one time".
- The PLAYER's welcome bonus is paid ONCE per player (their first validated code),
  claimed atomically on users.cp_welcome_paid. The CREATOR is paid for every distinct
  player who supports them. Knob: creator_settings.player_reward_once (default True).
- Rewards are idempotent (status transitions guard against double payout).
- Validation happens automatically when the referred user has a real Steam ID linked
  (steam_id exists AND does NOT start with 'demo_').
- Rewards: creator = configurable (default 50,000), player = creator * multiplier (default 0.5 → 25,000).
- Skin unlocks at N validated referrals (default 100, configurable).
- Monthly stats reset at month boundary; historical data is preserved forever.

Data collections:
- creators                 : one doc per creator user
- referrals                : one doc per referral (unique on referred_user_id)
- creator_settings         : singleton settings doc (id="settings")
- creator_notifications    : notifications for creators
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import re


# ─── Status enums (strings for Mongo simplicity) ────────────────────────────
STATUS_PENDING   = "PENDING"
STATUS_VALIDATED = "VALIDATED"
STATUS_REWARDED  = "REWARDED"
STATUS_CANCELLED = "CANCELLED"

CREATOR_ACTIVE     = "ACTIVE"
CREATOR_SUSPENDED  = "SUSPENDED"

# ─── Default settings (overridable via admin endpoint) ──────────────────────
DEFAULT_CREATOR_REWARD    = 50_000
DEFAULT_PLAYER_MULTIPLIER = 0.5
DEFAULT_SKIN_TARGET       = 100
# The exclusive is a REAL catalog glitch design (glitch_catalog.CREATOR_SKINS,
# id "leyenda-creador") granted through the same reward_skins lane as every
# crate / Battle Pass / leaderboard skin. No image_url on purpose: a glitch
# card is a NAME + COLOUR PROXIMITY, never a picture (fleet order 2026-08-11).
DEFAULT_SKIN = {
    "glitch_id":   "leyenda-creador",
    "name":        "Leyenda del Creador",
    "description": "Skin glitch exclusiva del Programa de Creadores â se desbloquea al alcanzar el objetivo de referidos validados.",
}

# Minimum minutes ON THE ISLAND before a referred account counts (the owner's
# rule is "joins our server", not "opens the website"): playtime_minutes is
# fed by the passive telemetry drain, so a referral only validates once the
# referred player has actually played. Admin-tunable via creator_settings.
DEFAULT_MIN_PLAYTIME_MINUTES = 10

# The player-side welcome bonus is paid ONCE per player, not once per code.
#
# 2026-08-18 the owner opened the program up: a player may support any number of
# creators. The creator half scales with that by design - each distinct player who
# supports them is a real referral and pays a real reward. The PLAYER half does not:
# it is a JOINING bonus, and the qualification behind it (a linked Steam id plus
# minutes played) is a property of the PLAYER, not of the code. Once a player has
# qualified, every further code would validate instantly, so paying per code would
# mint the bonus once per creator on the same ten minutes of play, from nothing.
# Set `player_reward_once: false` in creator settings to pay it on every code.
DEFAULT_PLAYER_REWARD_ONCE = True

# ─── Levels (legacy 4-tier mapping used by the LevelBadge component) ───────
def level_for(referrals: int) -> dict:
    if referrals >= 100: return {"key": "legend",  "label": "LEGEND",  "medal": "👑", "color": "#D4AF37"}
    if referrals >= 50:  return {"key": "elite",   "label": "ELITE",   "medal": "🥇", "color": "#F59E0B"}
    if referrals >= 25:  return {"key": "partner", "label": "PARTNER", "medal": "🥈", "color": "#C0C6D0"}
    return                      {"key": "rookie",  "label": "ROOKIE",  "medal": "🥉", "color": "#CD7F32"}


# ─── Dinosaur growth-stage milestones ──────────────────────────────────────
# Each milestone rewards a one-time PM bonus + a permanent title/badge.
# The "Elder" milestone (100) is what also grants the exclusive skin (kept in sync with skin_target).
MILESTONES = [
    {"key": "juvie",     "threshold": 10,  "bonus":   7_500, "title": "Juvenile Hunter", "medal": "🦎", "color": "#7CA842"},
    {"key": "sub_adult", "threshold": 25,  "bonus":  20_000, "title": "Sub-Adult Alpha", "medal": "🐊", "color": "#22C55E"},
    {"key": "adult",     "threshold": 50,  "bonus":  50_000, "title": "Full Grown",      "medal": "🦕", "color": "#F59E0B"},
    {"key": "elder",     "threshold": 100, "bonus": 150_000, "title": "Elder of the Pack", "medal": "🦴", "color": "#A78BFA"},
    {"key": "apex",      "threshold": 250, "bonus": 500_000, "title": "APEX PREDATOR",   "medal": "👑", "color": "#D4AF37"},
]


def milestones_status(refs: int, reached: Optional[list] = None) -> list:
    """Return the full list of milestones with reached/current/locked state for the UI."""
    reached_set = set(reached or [])
    current_idx = -1
    for i, m in enumerate(MILESTONES):
        if refs >= m["threshold"]:
            current_idx = i
    out = []
    for i, m in enumerate(MILESTONES):
        state = "locked"
        if i <= current_idx or m["key"] in reached_set:
            state = "current" if i == current_idx else "reached"
        out.append({**m, "state": state})
    return out


def current_stage(refs: int) -> Optional[dict]:
    """Return the highest milestone achieved (or None if under Juvie)."""
    cur = None
    for m in MILESTONES:
        if refs >= m["threshold"]:
            cur = m
    return cur


def newly_crossed_milestones(prev_refs: int, new_refs: int) -> list:
    """Return every milestone whose threshold is crossed going from prev_refs → new_refs."""
    return [m for m in MILESTONES if prev_refs < m["threshold"] <= new_refs]


# ─── Time helpers ──────────────────────────────────────────────────────────
def month_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


# ─── Code helpers ──────────────────────────────────────────────────────────
CODE_RE = re.compile(r"^[A-Z0-9_]{3,20}$")


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def is_valid_code(code: str) -> bool:
    return bool(code and CODE_RE.match(code))


# ─── Validation criteria ───────────────────────────────────────────────────
def user_has_real_steam(user: dict) -> bool:
    """Return True if user has a Steam ID that is NOT a demo placeholder."""
    sid = str((user or {}).get("steam_id") or "").strip()
    if not sid:
        return False
    if sid.lower().startswith("demo_"):
        return False
    return True


# ─── Public shape helpers ──────────────────────────────────────────────────
def public_creator(c: dict, user: Optional[dict] = None, rank: Optional[int] = None) -> dict:
    total = int(c.get("total_referrals", 0))
    lv = level_for(total)
    stage = current_stage(total)
    return {
        "id":               c.get("id"),
        "user_id":          c.get("user_id"),
        "code":             c.get("code"),
        "status":           c.get("status") or CREATOR_ACTIVE,
        "display_name":     c.get("display_name") or (user or {}).get("persona_name") or "Creator",
        "avatar":           c.get("avatar") or (user or {}).get("avatar") or (user or {}).get("avatar_url"),
        "total_referrals":  total,
        "monthly_referrals": int(c.get("monthly_referrals", 0)),
        "total_prime_meat_earned": int(c.get("total_prime_meat_earned", 0)),
        "monthly_prime_meat_earned": int(c.get("monthly_prime_meat_earned", 0)),
        "exclusive_skin_unlocked": bool(c.get("exclusive_skin_unlocked")),
        "skin_unlocked_at": c.get("skin_unlocked_at"),
        "level":            lv,
        "stage":            stage,
        "stages_reached":   list(c.get("stages_reached") or []),
        "code_visits_total": int(c.get("code_visits_total", 0)),
        "paused_until":     c.get("paused_until"),
        "rank":             rank,
        "created_at":       c.get("created_at"),
    }


def public_referral(r: dict, u: Optional[dict] = None) -> dict:
    return {
        "id":            r.get("id"),
        "referred_name": (u or {}).get("persona_name") or "Hunter",
        "referred_avatar": (u or {}).get("avatar") or (u or {}).get("avatar_url"),
        "status":        r.get("status"),
        "reward_amount": int(r.get("reward_amount", 0)) if r.get("status") == STATUS_REWARDED else None,
        "created_at":    r.get("created_at"),
        "validated_at":  r.get("validated_at"),
        "rewarded_at":   r.get("rewarded_at"),
    }
