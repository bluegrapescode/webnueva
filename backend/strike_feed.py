"""Public Discord feed for the strike/sanctions system.

Every strike issued from the admin panel (and every strike removal) posts a
Spanish embed to the public sanctions channel, in the fleet's public-wall
style: the SANCTIONED PLAYER is named and the consequence + reason are shown,
but the issuing staff member and any platform IDs are never included.

Knobs (all optional -- the feed degrades to a logged no-op, never an error):
  LIN_STRIKES_CHANNEL_ID  target channel id (default: the #sanciones channel
                          the owner designated, 1527387293696921710)
  DISCORD_BOT_TOKEN       reused from the existing Discord role-sync config

Design constraints:
  * Fire-and-forget: callers use fire_*() which schedules a background task
    and NEVER raises -- a Discord outage must not fail a strike.
  * Env is read per call (never at import) so module import order relative to
    load_dotenv() cannot dark-launch the feature.
  * allowed_mentions is always empty: persona names are player-controlled and
    must never ping roles/everyone.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("strike_feed")

DEFAULT_CHANNEL_ID = "1527387293696921710"
_API = "https://discord.com/api/v10"
_TIMEOUT_S = 8.0

# Embed accents follow the site theme: warning gold, timed-ban orange/red,
# permanent crimson, removals neutral grey.
_COLOR_WARN = 0xE8C766
_COLOR_BAN_SHORT = 0xF97316
_COLOR_BAN_LONG = 0xE24A4A
_COLOR_BAN_PERM = 0x7F1D1D
_COLOR_REMOVED = 0x7C8590

_FOOTER = "Sistema de Sanciones - La Isla Nublar"


def _channel_id() -> str:
    return (os.environ.get("LIN_STRIKES_CHANNEL_ID") or DEFAULT_CHANNEL_ID).strip()


def _token() -> str:
    return (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()


def enabled() -> bool:
    return bool(_token() and _channel_id())


def _clip(text, limit):
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def consequence_text(action, ban_permanent, ban_hours) -> str:
    """Spanish consequence line from the enforcement facts."""
    if action != "ban":
        return "Aviso formal y expulsión de la partida"
    if ban_permanent:
        return "Expulsión permanente del servidor"
    try:
        hours = int(ban_hours or 0)
    except (TypeError, ValueError):
        hours = 0
    if hours <= 0:
        return "Suspensión temporal del servidor"
    if hours == 1:
        return "Suspensión de 1 hora"
    if hours % 24 == 0:
        days = hours // 24
        return "Suspensión de 1 día" if days == 1 else f"Suspensión de {days} días"
    return f"Suspensión de {hours} horas"


def _strike_color(action, ban_permanent, ban_hours) -> int:
    if action != "ban":
        return _COLOR_WARN
    if ban_permanent:
        return _COLOR_BAN_PERM
    try:
        hours = int(ban_hours or 0)
    except (TypeError, ValueError):
        hours = 0
    return _COLOR_BAN_LONG if hours > 24 else _COLOR_BAN_SHORT


def build_strike_embed(persona, count, action, ban_permanent, ban_hours, reason, strike_id) -> dict:
    """Public-wall embed: player named, staff and IDs never shown."""
    name = _clip(persona, 80) or "Jugador"
    lines = "\n".join("> " + ln for ln in _clip(reason, 900).splitlines() if ln.strip()) or "> Incumplimiento de las normas"
    label = "sanción activa" if count == 1 else "sanciones activas"
    return {
        "title": f"Sanción registrada - Strike #{count}",
        "description": f"**{name}** ha recibido una sanción del equipo de moderación.\n{lines}",
        "color": _strike_color(action, ban_permanent, ban_hours),
        "fields": [
            {"name": "Consecuencia", "value": consequence_text(action, ban_permanent, ban_hours), "inline": True},
            {"name": "Historial", "value": f"{count} {label}", "inline": True},
        ],
        "footer": {"text": f"{_FOOTER} - folio {_clip(strike_id, 12)}"},
    }


def build_removed_embed(persona, remaining) -> dict:
    name = _clip(persona, 80) or "Jugador"
    label = "sanción activa" if remaining == 1 else "sanciones activas"
    return {
        "title": "Sanción anulada",
        "description": f"Se ha anulado una sanción de **{name}** tras la revisión del caso.",
        "color": _COLOR_REMOVED,
        "fields": [{"name": "Historial", "value": f"{remaining} {label}", "inline": True}],
        "footer": {"text": _FOOTER},
    }


async def _post_embed(embed: dict):
    """POST one embed to the sanctions channel. Returns the message id, or None.
    Never raises: every failure mode is contained to a warning log."""
    try:
        if not enabled():
            logger.warning("[strike_feed] disabled (missing DISCORD_BOT_TOKEN or channel id)")
            return None
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as hc:
            r = await hc.post(
                f"{_API}/channels/{_channel_id()}/messages",
                headers={"Authorization": f"Bot {_token()}"},
                json={"embeds": [embed], "allowed_mentions": {"parse": []}},
            )
        if r.status_code >= 300:
            logger.warning("[strike_feed] post failed status=%s body=%s", r.status_code, r.text[:200])
            return None
        mid = (r.json() or {}).get("id")
        logger.info("[strike_feed] posted message=%s title=%s", mid, embed.get("title"))
        return mid
    except Exception as e:  # containment boundary: the feed must never propagate
        logger.warning("[strike_feed] post error %s: %s", type(e).__name__, e)
        return None


async def post_strike(persona, count, action, ban_permanent, ban_hours, reason, strike_id):
    return await _post_embed(build_strike_embed(persona, count, action, ban_permanent, ban_hours, reason, strike_id))


async def post_strike_removed(persona, remaining):
    return await _post_embed(build_removed_embed(persona, remaining))


def _fire(coro, what: str):
    """Schedule a feed post in the background; swallow every scheduling failure."""
    try:
        asyncio.get_running_loop().create_task(coro)
    except Exception as e:
        coro.close()
        logger.warning("[strike_feed] could not schedule %s post (%s: %s)", what, type(e).__name__, e)


def fire_strike_posted(persona, count, action, ban_permanent, ban_hours, reason, strike_id):
    _fire(post_strike(persona, count, action, ban_permanent, ban_hours, reason, strike_id), "strike")


def fire_strike_removed(persona, remaining):
    _fire(post_strike_removed(persona, remaining), "removal")
