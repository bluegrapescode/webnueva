"""Public Discord feed for Multiplier Events.

When an admin publishes a multiplier event, a Spanish embed lands in the
events channel so players hear about it without opening the site. Same design
constraints as strike_feed.py:

  * Fire-and-forget: fire_event_published() schedules a background task and
    NEVER raises — a Discord outage must not fail the admin's publish.
  * Env read per call (never at import) so module import order relative to
    load_dotenv() cannot dark-launch the feature.
  * allowed_mentions is always empty; titles/descriptions are admin-controlled
    but must never ping roles/everyone.

Knobs (feed is a logged no-op until BOTH are present):
  LIN_EVENTS_CHANNEL_ID  target channel id (no default — the owner picks one)
  DISCORD_BOT_TOKEN      reused from the existing Discord config
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("event_feed")

_API = "https://discord.com/api/v10"
_TIMEOUT_S = 8.0
_COLOR_EVENT = 0x34D399  # site emerald accent
_FOOTER = "Eventos - La Isla Nublar"


def _channel_id() -> str:
    return (os.environ.get("LIN_EVENTS_CHANNEL_ID") or "").strip()


def _token() -> str:
    return (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()


def enabled() -> bool:
    return bool(_token() and _channel_id())


def _clip(text, limit):
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _fmt_window_hours(hours) -> str:
    try:
        h = int(hours)
    except (TypeError, ValueError):
        return ""
    if h <= 0:
        return ""
    if h % 168 == 0:
        w = h // 168
        return "1 semana" if w == 1 else f"{w} semanas"
    if h % 24 == 0:
        d = h // 24
        return "1 día" if d == 1 else f"{d} días"
    return "1 hora" if h == 1 else f"{h} horas"


def build_published_embed(event: dict, duration_hours) -> dict:
    """Embed payload for a freshly published multiplier event. Pure — unit-testable."""
    ev = event or {}
    species = str(ev.get("species") or "").strip() or "—"
    try:
        mult = int(ev.get("multiplier") or 0)
    except (TypeError, ValueError):
        mult = 0
    fields = [
        {"name": "Especie", "value": _clip(species, 1024), "inline": True},
        {"name": "Multiplicador", "value": f"x{mult} PrimeMeat", "inline": True},
    ]
    window = _fmt_window_hours(duration_hours)
    if window:
        fields.append({"name": "Duración", "value": window, "inline": True})
    embed = {
        "title": _clip(f"Nuevo evento: {ev.get('title') or f'Día de {species}'}", 256),
        "description": _clip(
            f"Todo el PrimeMeat que ganes jugando como {species} se multiplica x{mult} mientras dure el evento.", 2048),
        "color": _COLOR_EVENT,
        "fields": fields,
        "footer": {"text": f"{_FOOTER} — laislanublar.net/quests"},
    }
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


async def _post(payload: dict):
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as hc:
            r = await hc.post(f"{_API}/channels/{_channel_id()}/messages",
                              headers={"Authorization": f"Bot {_token()}"}, json=payload)
            if r.status_code >= 300:
                logger.warning(f"[event_feed] Discord post failed {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[event_feed] Discord post error: {e}")


def fire_event_published(event: dict, duration_hours):
    """Schedule the publish announcement. Never raises; no-op when unconfigured."""
    if not enabled():
        logger.info("[event_feed] announce skipped (channel/token not configured)")
        return
    try:
        payload = build_published_embed(event, duration_hours)
        asyncio.get_running_loop().create_task(_post(payload))
    except Exception as e:
        logger.warning(f"[event_feed] announce scheduling failed: {e}")
