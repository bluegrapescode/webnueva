"""Owner-only Discord audit feed for staff actions.

Every admin-panel action that moves value posts a Spanish embed to the private
"REGISTRO OWNER" channels (visible to the server owner accounts only), so the
owner can monitor what the staff team does with the economy tools:

  * currency grants (Monedas de Supervivencia / Amberium) — self-grants are
    flagged loudly and colored red;
  * promotional code lifecycle (created / edited / deleted);
  * inventory wipes (web inventory + glitch skins purged for enforcement).

Unlike the public sanctions wall, the STAFF MEMBER IS NAMED here — that is the
point of the channel. It is still never visible to regular members or staff
(channel permission overwrites), and allowed_mentions stays empty so a
player-controlled persona name can never ping anyone.

Knobs (all optional — the feed degrades to a logged no-op, never an error):
  LIN_STAFF_ECON_CHANNEL_ID   grants channel  (default #registro-economia)
  LIN_STAFF_CODES_CHANNEL_ID  codes channel   (default #registro-codigos)
  DISCORD_BOT_TOKEN           reused from the existing Discord config

Design constraints (same contract as strike_feed):
  * Fire-and-forget: callers use fire_*() which schedules a background task
    and NEVER raises — a Discord outage must not fail an admin action.
  * Env is read per call (never at import) so module import order relative to
    load_dotenv() cannot dark-launch the feature.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("staff_feed")

DEFAULT_ECON_CHANNEL_ID = "1528132042829729923"
DEFAULT_CODES_CHANNEL_ID = "1528132043802808571"
_API = "https://discord.com/api/v10"
_TIMEOUT_S = 8.0

_COLOR_GRANT = 0xE8C766       # gold — grant to another player
_COLOR_SELF_GRANT = 0xE24A4A  # red — staff paying themselves
_COLOR_CODE_NEW = 0x8B5CF6    # violet — new promo code
_COLOR_CODE_EDIT = 0x7C8590   # grey — edits
_COLOR_CODE_DEL = 0x475061    # dark grey — deletions
_COLOR_WIPE = 0xE24A4A       # red — destructive enforcement action

_FOOTER = "Registro del Staff - La Isla Nublar"


def _econ_channel_id() -> str:
    return (os.environ.get("LIN_STAFF_ECON_CHANNEL_ID") or DEFAULT_ECON_CHANNEL_ID).strip()


def _codes_channel_id() -> str:
    return (os.environ.get("LIN_STAFF_CODES_CHANNEL_ID") or DEFAULT_CODES_CHANNEL_ID).strip()


def _token() -> str:
    return (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()


def _clip(text, limit):
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _fmt_amount(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _currency_label(currency: str) -> str:
    return "Amberium" if str(currency) == "vip" else "Monedas de Supervivencia"


def build_grant_embed(staff, target, currency, amount, reason, self_grant) -> dict:
    staff_name = _clip(staff, 80) or "Staff"
    target_name = _clip(target, 80) or "Jugador"
    title = "Auto-concesión de saldo" if self_grant else "Concesión de saldo"
    who = "a sí mismo" if self_grant else f"a **{target_name}**"
    lines = [f"**{staff_name}** otorgó {who}:",
             f"> **{_fmt_amount(amount)}** {_currency_label(currency)}"]
    reason = _clip(reason, 300)
    if reason:
        lines.append(f"> Motivo: {reason}")
    if self_grant:
        lines.append("\nEl miembro del staff se acreditó saldo a su propia cuenta.")
    return {
        "title": title,
        "description": "\n".join(lines),
        "color": _COLOR_SELF_GRANT if self_grant else _COLOR_GRANT,
        "footer": {"text": _FOOTER},
    }


def build_inventory_wipe_embed(staff, target, items_deleted, skins_deleted, self_wipe) -> dict:
    staff_name = _clip(staff, 80) or "Staff"
    target_name = _clip(target, 80) or "Jugador"
    who = "su propio inventario" if self_wipe else f"el inventario de **{target_name}**"
    lines = [f"**{staff_name}** borró {who}:",
             f"> **{_fmt_amount(items_deleted)}** objetos del inventario web",
             f"> **{_fmt_amount(skins_deleted)}** skins glitch",
             "\nMonedas, La Bóveda y el Mercado no fueron modificados."]
    return {"title": "Inventario borrado", "description": "\n".join(lines),
            "color": _COLOR_WIPE, "footer": {"text": _FOOTER}}


def _code_reward_text(reward: dict) -> str:
    r = reward or {}
    parts = []
    try:
        coins = int(r.get("coins") or 0)
        if coins:
            parts.append(f"{_fmt_amount(coins)} Monedas")
    except (TypeError, ValueError):
        pass
    try:
        vip = int(r.get("vip_coins") or 0)
        if vip:
            parts.append(f"{_fmt_amount(vip)} Amberium")
    except (TypeError, ValueError):
        pass
    try:
        spins = int(r.get("spins") or 0)
        if spins:
            parts.append(f"{_fmt_amount(spins)} giros bonus")
    except (TypeError, ValueError):
        pass
    for key in ("item", "item_id", "dino", "skin"):
        if r.get(key):
            parts.append(str(r.get(key)))
    return ", ".join(parts) or "sin recompensa declarada"


def build_code_created_embed(staff, code, reward, max_uses, per_user, active) -> dict:
    staff_name = _clip(staff, 80) or "Staff"
    fields = [
        {"name": "Recompensa", "value": _clip(_code_reward_text(reward), 200), "inline": False},
        {"name": "Usos máximos", "value": str(max_uses if max_uses is not None else "∞"), "inline": True},
        {"name": "Por jugador", "value": str(per_user if per_user is not None else "∞"), "inline": True},
        {"name": "Estado", "value": "Activo" if active else "Inactivo", "inline": True},
    ]
    return {
        "title": "Código promocional creado",
        "description": f"**{staff_name}** creó el código **{_clip(code, 40)}**.",
        "color": _COLOR_CODE_NEW,
        "fields": fields,
        "footer": {"text": _FOOTER},
    }


def build_code_changed_embed(staff, code_label, action, changes) -> dict:
    staff_name = _clip(staff, 80) or "Staff"
    if action == "deleted":
        title, color, verb = "Código promocional eliminado", _COLOR_CODE_DEL, "eliminó"
    else:
        title, color, verb = "Código promocional editado", _COLOR_CODE_EDIT, "editó"
    desc = f"**{staff_name}** {verb} el código **{_clip(code_label, 40)}**."
    ch = "; ".join(f"{k}: {_clip(v, 60)}" for k, v in (changes or {}).items())
    if ch:
        desc += f"\n> Cambios: {_clip(ch, 700)}"
    return {"title": title, "description": desc, "color": color, "footer": {"text": _FOOTER}}


async def _post_embed(channel_id: str, embed: dict):
    """POST one embed. Returns the message id, or None. Never raises: every
    failure mode is contained to a warning log."""
    try:
        if not (_token() and channel_id):
            logger.warning("[staff_feed] disabled (missing DISCORD_BOT_TOKEN or channel id)")
            return None
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as hc:
            r = await hc.post(
                f"{_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {_token()}"},
                json={"embeds": [embed], "allowed_mentions": {"parse": []}},
            )
        if r.status_code >= 300:
            logger.warning("[staff_feed] post failed status=%s body=%s", r.status_code, r.text[:200])
            return None
        mid = (r.json() or {}).get("id")
        logger.info("[staff_feed] posted message=%s title=%s", mid, embed.get("title"))
        return mid
    except Exception as e:  # containment boundary: the feed must never propagate
        logger.warning("[staff_feed] post error %s: %s", type(e).__name__, e)
        return None


def _fire(coro, what: str):
    """Schedule a feed post in the background; swallow every scheduling failure."""
    try:
        asyncio.get_running_loop().create_task(coro)
    except Exception as e:
        coro.close()
        logger.warning("[staff_feed] could not schedule %s post (%s: %s)", what, type(e).__name__, e)


def fire_grant(staff, target, currency, amount, reason, self_grant):
    _fire(_post_embed(_econ_channel_id(),
                      build_grant_embed(staff, target, currency, amount, reason, self_grant)), "grant")


def fire_inventory_wipe(staff, target, items_deleted, skins_deleted, self_wipe=False):
    _fire(_post_embed(_econ_channel_id(),
                      build_inventory_wipe_embed(staff, target, items_deleted, skins_deleted, self_wipe)),
          "inventory-wipe")


def fire_code_created(staff, code, reward, max_uses, per_user, active):
    _fire(_post_embed(_codes_channel_id(),
                      build_code_created_embed(staff, code, reward, max_uses, per_user, active)), "code-created")


def fire_code_updated(staff, code_label, changes):
    _fire(_post_embed(_codes_channel_id(),
                      build_code_changed_embed(staff, code_label, "updated", changes)), "code-updated")


def fire_code_deleted(staff, code_label):
    _fire(_post_embed(_codes_channel_id(),
                      build_code_changed_embed(staff, code_label, "deleted", None)), "code-deleted")
