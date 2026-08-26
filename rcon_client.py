"""Async RCON client for The Isle: Evrima's custom binary protocol.

Protocol:
  - Auth packet:    0x01 + password + 0x00   -> server replies "Password Accepted"
  - Command packet: 0x02 + opcode + params + 0x00
Evrima uses a single short-lived TCP connection per command batch.
"""
import asyncio
import os

RCON_HOST = os.environ.get("RCON_HOST")
RCON_PORT = int(os.environ.get("RCON_PORT", "0") or 0)
RCON_PASSWORD = os.environ.get("RCON_PASSWORD")

# opcodes (verified against a live Evrima server)
OP_ANNOUNCE = 0x10
OP_SERVER_DETAILS = 0x12
OP_UPDATE_PLAYABLES = 0x15
OP_BAN = 0x20
OP_KICK = 0x30
OP_PLAYER_LIST = 0x40
OP_SAVE = 0x50


def is_configured() -> bool:
    return bool(RCON_HOST and RCON_PORT and RCON_PASSWORD)


async def _send(opcode: int, params: bytes = b"", read: bool = True, timeout: float = 6.0) -> bytes:
    """Open a connection, authenticate, run one command and return the raw reply."""
    if not is_configured():
        raise RuntimeError("RCON not configured")
    reader, writer = await asyncio.wait_for(asyncio.open_connection(RCON_HOST, RCON_PORT), timeout=timeout)
    try:
        writer.write(b"\x01" + RCON_PASSWORD.encode() + b"\x00")
        await writer.drain()
        try:
            auth = await asyncio.wait_for(reader.read(256), timeout=timeout)
        except asyncio.TimeoutError:
            auth = b""
        if b"Password Accepted" not in auth:
            raise RuntimeError("RCON auth failed")
        writer.write(b"\x02" + bytes([opcode]) + params + b"\x00")
        await writer.drain()
        if not read:
            await asyncio.sleep(0.2)
            return b""
        data = b""
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=1.5)
                if not chunk:
                    break
                data += chunk
                if len(chunk) < 8192:
                    break
        except asyncio.TimeoutError:
            pass
        return data
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except Exception:
            pass


def _parse_details(raw: bytes) -> dict:
    txt = raw.decode("utf-8", "ignore")
    if "ServerDetails" in txt:
        txt = txt.split("ServerDetails", 1)[1]
    out = {}
    for part in txt.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    def _int(k, d=0):
        try:
            return int(out.get(k, d))
        except (ValueError, TypeError):
            return d
    def _bool(k):
        return str(out.get(k, "")).lower() == "true"
    return {
        "name": out.get("ServerName") or "The Isle: Evrima",
        "map": out.get("ServerMap") or "Gateway",
        "players": _int("ServerCurrentPlayers"),
        "max_players": _int("ServerMaxPlayers", 120) or 120,
        "mutations": _bool("bEnableMutations"),
        "humans": _bool("bEnableHumans"),
        "queue_enabled": _bool("bQueueEnabled"),
        "ai": _bool("bSpawnAI"),
        "password_protected": _bool("bServerPassword"),
    }


def _parse_players(raw: bytes) -> list:
    """Evrima format: 'PlayerList\\n<id1>,<id2>,\\n<name1>,<name2>,'
    Line 1 = header, line 2 = comma-separated platform (Steam64) ids, line 3 = names."""
    txt = raw.decode("utf-8", "ignore")
    lines = [l.strip() for l in txt.split("\n")]
    if lines and lines[0].startswith("PlayerList"):
        lines = lines[1:]
    ids = [x.strip() for x in lines[0].split(",")] if len(lines) >= 1 else []
    names = [x.strip() for x in lines[1].split(",")] if len(lines) >= 2 else []
    ids = [x for x in ids if x]
    names = [x for x in names if x]
    players = []
    for i in range(max(len(ids), len(names))):
        players.append({
            "steam_id": ids[i] if i < len(ids) else None,
            "name": names[i] if i < len(names) else None,
        })
    return players


async def server_details() -> dict:
    return _parse_details(await _send(OP_SERVER_DETAILS))


async def player_list() -> list:
    return _parse_players(await _send(OP_PLAYER_LIST))


async def announce(message: str) -> bool:
    await _send(OP_ANNOUNCE, message.encode("utf-8"), read=False)
    return True


async def save() -> bool:
    await _send(OP_SAVE, read=False)
    return True


async def kick(steam_id) -> str:
    """Kick a connected player by Steam64 id. Evrima kick packet carries ONLY the
    bare Steam64 ascii id (no reason field). Kick affects an ONLINE player only;
    kicking an absent id is a no-op. The reply string is NOT authoritative — callers
    that need proof of removal must re-poll player_list()."""
    sid = str(steam_id or "").strip()
    if not sid:
        raise RuntimeError("kick: empty steam_id")
    raw = await _send(OP_KICK, sid.encode("utf-8"))
    return raw.replace(b"\x00", b"").decode("utf-8", "replace").strip()


async def ban(steam_id) -> str:
    """Ban a player by Steam64 id over RCON. Evrima's RCON ban packet carries ONLY
    the bare Steam64 id — NO duration and NO reason (RCON ban is permanent-only and
    does not reliably pre-block reconnection on a live server). Durable, time-limited
    banning is enforced via the game-native PlayerBans.json file (see native_bans.py);
    this RCON ban is a best-effort in-memory supplement."""
    sid = str(steam_id or "").strip()
    if not sid:
        raise RuntimeError("ban: empty steam_id")
    raw = await _send(OP_BAN, sid.encode("utf-8"))
    return raw.replace(b"\x00", b"").decode("utf-8", "replace").strip()


async def ping() -> dict:
    """Connectivity + details check (used by admin status)."""
    d = await server_details()
    return {"online": True, **d}
