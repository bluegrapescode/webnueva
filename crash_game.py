"""Dino Crash -- multiplayer crash-style casino game, played entirely over WebSocket.

Design (one job per piece, so each part is easy to read and test in isolation):
  - ConnectionManager: tracks authenticated sockets and delivers messages. Knows
    nothing about crash-game rules.
  - generate_crash_point / multiplier_at: pure math, no I/O -- the only two
    formulas in the whole game, so they are trivial to unit test.
  - _handle_bet / _handle_cashout: validate and settle exactly one player action.
  - split_jackpot / _settle_jackpot: the Moon Pool. JACKPOT_RATE of every bet
    feeds a persistent pool; when a round ends, everyone who cashed out at
    JACKPOT_MULTIPLIER or better splits the whole pool in proportion to their
    stake and the pool restarts at zero. No qualifying cashout means the pool
    simply rolls over into the next round.
  - run_crash_loop: the round phase machine (betting -> running -> crashed),
    forever.
  - crash_socket: the WebSocket endpoint itself -- just auth, register, push the
    initial snapshot, then dispatch incoming messages. No game rules live here.

Wire protocol (every frame is one JSON object with a "type"):
  Client -> server
    {"type": "auth", "token": "<jwt>"}            must be the FIRST message
    {"type": "bet", "amount": int, "auto_cashout": float|null}
    {"type": "cashout"}
  Server -> client
    "state"                                          sent once, right after auth succeeds
    "phase_betting" / "phase_running" / "tick" / "phase_crashed"   broadcast to everyone
    "bet_placed" / "user_cashout"                                  broadcast to everyone
    "jackpot"                                        broadcast when the Moon Pool is won;
                                                     re-sent to each winner alone with
                                                     their own "won" share and "coins"
    "bet_ack" / "cashout_ack" / "error"              sent ONLY to the socket it answers

A dropped connection simply reconnects and re-authenticates -- the fresh "state"
push on reconnect IS the resync mechanism, so no REST endpoint is needed
alongside this for the frontend to recover from a lost socket.

This module deliberately does not import anything from server.py (and server.py
must not import from it either besides `router` and `run_crash_loop`) to avoid a
circular import; the Mongo handle and JWT secret are handed in once via
configure(), the same dependency-injection pattern vault.py uses for its event
loop (see vault.set_loop).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pymongo import ReturnDocument

logger = logging.getLogger("laislanublar.crash")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MIN_BET = 100
MAX_BET = 1_000_000
GROWTH_RATE = 0.10          # multiplier(t) = e^(GROWTH_RATE * t)
# Broadcast cadence: this is a per-connected-client websocket send
TICK_SECONDS = 0.2
BETTING_SECONDS = 6
ROUND_COOLDOWN_SECONDS = 3
JACKPOT_MIN_PAYOUT = 1      # a pool below one whole coin rolls over instead of paying
AUTH_TIMEOUT_SECONDS = 10
HISTORY_LIMIT = 24
JWT_ALGO = "HS256"
LEDGER_RETENTION_DAYS = 7   # how long a settled crash bet stays in casino_bets
LEDGER_TRIM_EVERY = 500     # rounds between retention sweeps (~3h at 180 rounds/h)


def _env_num(name, default, lo, cast):
    """Read one economy dial from the environment, falling back to the shipped
    default on anything unusable. A dial is never allowed below `lo`: an operator
    typo must not be able to hand the game away, and a missing variable (a rebuilt
    box, a lost .env) must land on the shipped value, not on zero."""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = cast(str(raw).strip())
    except (TypeError, ValueError):
        logger.error("[crash] %s=%r is not a number, using %s", name, raw, default)
        return default
    if value < lo:
        logger.error("[crash] %s=%s is below the floor %s, using %s", name, value, lo, default)
        return default
    return value


# ---------------------------------------------------------------------------
# The house edge, in one place
# ---------------------------------------------------------------------------
# Exactly one round in BUST_ONE_IN busts instantly at 1.00x. That instant bust is
# the ONLY thing that earns the house anything: every other round pays the true
# fair multiplier, so the edge is precisely 1/BUST_ONE_IN of everything wagered,
# whatever cash-out target a player picks. 33 (3.03%) was the shipped value until
# 2026-08-19; the owner's call that day was to bring Crash into line with the
# site's card game, which measured +12.06% all-time over 24,806 hands.
BUST_ONE_IN = _env_num("CRASH_BUST_ONE_IN", 7, 2, int)

# Share of every stake that feeds the Moon Pool.
# THIS IS A SLICE OF THE HOUSE'S OWN EDGE, NOT AN EXTRA CHARGE ON THE PLAYER.
# Nothing is deducted from a stake or a payout, so every coin the pool ever pays
# is a coin this game creates. It only balances because the house takes MORE than
# it feeds in. From 2026-07-29 to 2026-08-19 it did not: the rate was 0.05 against
# a 1/33 = 0.0303 edge, so Crash MINTED 1.97% of everything wagered -- a measured
# 108,078,421 CC in 21 days, 6% of the whole economy. See _assert_house_wins().
JACKPOT_RATE = _env_num("CRASH_JACKPOT_RATE", 0.02, 0.0, float)

# Cash out at this multiplier or better to take the pool.
JACKPOT_MULTIPLIER = _env_num("CRASH_JACKPOT_MULTIPLIER", 100.0, 1.01, float)


def house_edge():
    """Share of every stake the base game keeps, before the Moon Pool is fed."""
    return 1.0 / BUST_ONE_IN


def net_house_edge():
    """What the house actually keeps once the Moon Pool has been fed. Negative
    means the game creates coins out of nothing, forever, and no amount of play
    volume fixes it -- more play makes it worse."""
    return house_edge() - JACKPOT_RATE


def economics_line() -> str:
    """The one string that answers "is the house ahead?" without anyone having to
    read this file. Built here rather than formatted at each call site so the log
    and any future status surface cannot drift apart."""
    return ("[crash] house edge 1 in %s = %.2f%% | moon pool %.2f%% of stakes at %sx+ "
            "| NET TO HOUSE %.2f%% of turnover"
            % (BUST_ONE_IN, 100.0 * house_edge(), 100.0 * JACKPOT_RATE,
               JACKPOT_MULTIPLIER, 100.0 * net_house_edge()))


def _assert_house_wins():
    """Clamp the Moon Pool rate so it can never exceed the house edge again.

    Called at import and again from configure(), so a bad environment variable on
    a box nobody is watching cannot silently re-open the coin printer. Clamping
    rather than raising is deliberate: a casino dial that refuses to boot takes
    the whole website down with it, and a game that pays a smaller pool is always
    the safer failure."""
    global JACKPOT_RATE
    edge = house_edge()
    if JACKPOT_RATE >= edge:
        safe = round(edge / 2.0, 6)
        logger.error(
            "[crash] moon pool rate %.4f >= house edge %.4f -- the game would MINT coins. "
            "Clamped to %.4f. Check CRASH_JACKPOT_RATE / CRASH_BUST_ONE_IN.",
            JACKPOT_RATE, edge, safe)
        JACKPOT_RATE = safe


_assert_house_wins()

router = APIRouter()

# Injected once at app startup via configure() -- see module docstring.
_db = None
_jwt_secret = "devsecret"
# Website-ban gate (2026-08-17): this websocket decodes the session JWT on its
# own, so it is the SECOND place a token becomes a user. server.py hands it the
# same check its get_current_user runs (webban.check) so a banned account is
# refused here too. Optional: a host that never sets it keeps the old behaviour.
_ban_check = None


def configure(db, jwt_secret: str, *, ban_check=None) -> None:
    global _db, _jwt_secret, _ban_check
    _db = db
    _jwt_secret = jwt_secret
    _ban_check = ban_check
    # Re-run against whatever the environment actually holds at startup, and say
    # the resulting economics out loud once, so a boot log answers "is the house
    # ahead?" without anyone having to read this file.
    _assert_house_wins()
    # Emitted here for any caller whose logging is already up (the gates are), and
    # AGAIN from run_crash_loop for the host app -- see the note there.
    logger.info("%s", economics_line())


class Incoming:
    AUTH = "auth"
    BET = "bet"
    CASHOUT = "cashout"


class Outgoing:
    STATE = "state"
    PHASE_BETTING = "phase_betting"
    PHASE_RUNNING = "phase_running"
    TICK = "tick"
    PHASE_CRASHED = "phase_crashed"
    BET_PLACED = "bet_placed"
    USER_CASHOUT = "user_cashout"
    JACKPOT = "jackpot"
    BET_ACK = "bet_ack"
    CASHOUT_ACK = "cashout_ack"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Pure helpers -- no I/O, safe to unit test on their own
# ---------------------------------------------------------------------------
def generate_crash_point(server_seed: str, client_seed: str, nonce: int,
                         *, bust_one_in: Optional[int] = None) -> float:
    """Provably-fair crash point. Fixed house edge: 1 round in BUST_ONE_IN busts
    at 1.00x, and that instant bust IS the entire house edge -- every other round
    pays the honest fair curve, so the same edge applies at whatever cash-out
    target a player picks. `bust_one_in` overrides the live dial, for tests."""
    divisor = int(BUST_ONE_IN if bust_one_in is None else bust_one_in)
    if divisor < 2:  # 1 would bust every round; 0 would raise ZeroDivisionError
        divisor = 2
    digest = hmac.new(server_seed.encode(), f"{client_seed}:{nonce}".encode(), hashlib.sha256).hexdigest()
    roll = int(digest[:13], 16)
    if roll % divisor == 0:
        return 1.00
    ceiling = 2 ** 52
    point = (100 * ceiling - roll) / (ceiling - roll) / 100
    return max(1.00, round(point, 2))


def multiplier_at(elapsed_seconds: float) -> float:
    return round(math.exp(GROWTH_RATE * max(0.0, elapsed_seconds)), 2)


def qualifies_for_jackpot(bet: dict) -> bool:
    """A bet wins a share of the Moon Pool if it actually cashed out at or above
    JACKPOT_MULTIPLIER. `cashed_at` is None for anyone still flying when the
    round busted, so a lost bet can never qualify however large it was."""
    cashed_at = bet.get("cashed_at")
    return cashed_at is not None and float(cashed_at) >= JACKPOT_MULTIPLIER


def split_jackpot(pool: int, winners: list[dict]) -> list[int]:
    """Split `pool` whole coins across `winners` in proportion to their stakes.

    Coins are integers, so proportional shares almost never divide evenly; the
    rounding remainder goes to the largest stake. The returned shares therefore
    sum to EXACTLY `pool` -- the house never pays out more than it claimed, and
    never quietly keeps a few coins back either.
    """
    if pool <= 0 or not winners:
        return [0] * len(winners)
    stakes = [max(0, int(w.get("amount") or 0)) for w in winners]
    total = sum(stakes)
    if total <= 0:  # every winner staked nothing (cannot happen: MIN_BET > 0)
        return [0] * len(winners)
    shares = [pool * stake // total for stake in stakes]
    biggest = max(range(len(stakes)), key=lambda i: stakes[i])
    shares[biggest] += pool - sum(shares)
    return shares


# ---------------------------------------------------------------------------
# Connections -- bookkeeping only, no game rules
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self._user_by_socket: dict[WebSocket, str] = {}
        self._sockets_by_user: dict[str, set[WebSocket]] = {}

    def register(self, websocket: WebSocket, user_id: str) -> None:
        self._user_by_socket[websocket] = user_id
        self._sockets_by_user.setdefault(user_id, set()).add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        user_id = self._user_by_socket.pop(websocket, None)
        sockets = self._sockets_by_user.get(user_id, set()) if user_id else set()
        sockets.discard(websocket)
        if user_id and not sockets:
            self._sockets_by_user.pop(user_id, None)

    async def send(self, websocket: WebSocket, message: dict) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            self.unregister(websocket)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        for websocket in list(self._sockets_by_user.get(user_id, ())):
            await self.send(websocket, message)

    async def broadcast(self, message: dict) -> None:
        for websocket in list(self._user_by_socket):
            await self.send(websocket, message)


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Round persistence -- a single "current" document holds the live round
# ---------------------------------------------------------------------------
async def _get_round() -> Optional[dict]:
    return await _db.crash_round.find_one({"id": "current"}, {"_id": 0})


async def _get_jackpot() -> float:
    meta = await _db.crash_meta.find_one({"id": "meta"}, {"_id": 0})
    return float((meta or {}).get("jackpot", 0.0))


async def _bump_jackpot(amount: float) -> float:
    updated = await _db.crash_meta.find_one_and_update(
        {"id": "meta"}, {"$inc": {"jackpot": amount}}, upsert=True, return_document=ReturnDocument.AFTER)
    return float((updated or {}).get("jackpot", amount))


async def _claim_jackpot() -> float:
    """Take the entire pool and leave it at zero, in one atomic step, returning
    what was taken. Reading then zeroing would drop any bet's contribution that
    landed between the two calls; a $set-to-0 that returns the BEFORE image puts
    every coin either in the amount we claim or in the fresh pool -- never in
    both, never in neither."""
    before = await _db.crash_meta.find_one_and_update(
        {"id": "meta"}, {"$set": {"jackpot": 0.0}}, upsert=True,
        return_document=ReturnDocument.BEFORE)
    return float((before or {}).get("jackpot", 0.0) or 0.0)


async def _get_last_win() -> Optional[dict]:
    meta = await _db.crash_meta.find_one({"id": "meta"}, {"_id": 0})
    return (meta or {}).get("last_win") or None


async def _get_history(limit: int = HISTORY_LIMIT) -> list[dict]:
    return await _db.crash_history.find({}, {"_id": 0}).sort("round_no", -1).to_list(limit)


async def _deduct_coins(user_id: str, amount: int) -> Optional[int]:
    updated = await _db.users.find_one_and_update(
        {"id": user_id, "coins": {"$gte": amount}},
        {"$inc": {"coins": -amount}},
        return_document=ReturnDocument.AFTER,
    )
    return int(updated["coins"]) if updated else None


async def _add_coins(user_id: str, amount: int) -> Optional[int]:
    """Credit `amount` and return the new balance, or None if there was no such
    user row to credit. None is a real failure, never "balance zero": a caller
    that cannot tell the two apart would report a payout it never made."""
    updated = await _db.users.find_one_and_update(
        {"id": user_id}, {"$inc": {"coins": amount}}, return_document=ReturnDocument.AFTER)
    if not updated:
        logger.error("[crash] credit of %s lost: no user row id=%s", amount, user_id)
        return None
    return int(updated["coins"])


async def _record_bet(bet: dict, payout: int, multiplier: float, result: str,
                      *, kind: str = "round") -> None:
    """Write one settled crash bet into `casino_bets`, the same shape and field
    names every other game on the site uses (`bet` / `payout` / `net`), so a crash
    play finally shows in the player's own history and stats -- and so this game's
    true take is measurable instead of having to be inferred from the pool.

    Crash has never written this ledger. That is exactly why the Moon Pool could
    mint 108M CC over three weeks with nothing able to see it. The write is
    fire-and-forget and fully contained on purpose: an audit trail must never be
    able to break, delay or unwind the payout it is only describing.

    A Moon Pool share rides in as kind="moon_pool" with bet 0 -- it is a payout
    from this game with no stake behind it, and recording it that way is what
    keeps "wagered vs paid" honest."""
    stake = int(bet.get("amount") or 0) if kind == "round" else 0
    try:
        await _db.casino_bets.insert_one({
            "id": uuid.uuid4().hex,
            "user_id": bet.get("user_id"),
            "user_name": bet.get("name"),
            "avatar": bet.get("avatar"),
            "game": "crash",
            "kind": kind,
            "bet": stake,
            "payout": int(payout),
            "net": int(payout) - stake,
            "multiplier": round(float(multiplier or 0), 2),
            "result": result,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:  # noqa: BLE001
        logger.exception("[crash] ledger row failed user=%s payout=%s", bet.get("user_id"), payout)


async def _trim_ledger() -> None:
    """Keep the crash half of `casino_bets` bounded. Crash settles far more bets
    than the click-per-hand games -- roughly 180 rounds an hour, every hour -- so
    without this the shared collection grows without limit. Filtered to this game
    alone: the other games' history is not ours to delete."""
    cutoff = datetime.now(timezone.utc).timestamp() - LEDGER_RETENTION_DAYS * 86400
    iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
    try:
        result = await _db.casino_bets.delete_many({"game": "crash", "created_at": {"$lt": iso}})
        if result.deleted_count:
            logger.info("[crash] ledger trim removed %s rows older than %s days",
                        result.deleted_count, LEDGER_RETENTION_DAYS)
    except Exception:  # noqa: BLE001
        logger.exception("[crash] ledger trim failed")


def _public_round_view(round_doc: dict) -> dict:
    """Strip the still-secret server_seed; the crash point is hidden until crashed."""
    view = {k: v for k, v in round_doc.items() if k != "server_seed"}
    if view.get("phase") != "crashed":
        view.pop("crash_point", None)
    return view


# ---------------------------------------------------------------------------
# Client actions
# ---------------------------------------------------------------------------
async def _handle_bet(websocket: WebSocket, user: dict, payload: dict) -> None:
    if RETIRED:
        # Unreachable through the gated socket; kept as the unit-level wall so
        # no future caller can take a stake from a game that no longer runs.
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": _RETIRED_MSG})
        return
    try:
        amount = int(payload.get("amount"))
    except (TypeError, ValueError):
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Monto de apuesta invalido"})
        return
    if not (MIN_BET <= amount <= MAX_BET):
        await manager.send(websocket, {"type": Outgoing.ERROR,
                                       "message": f"La apuesta debe estar entre {MIN_BET} y {MAX_BET}"})
        return
    auto_cashout = payload.get("auto_cashout")
    try:
        auto_cashout = float(auto_cashout) if auto_cashout is not None else None
    except (TypeError, ValueError):
        auto_cashout = None
    if auto_cashout is not None and auto_cashout < 1.01:
        auto_cashout = None

    round_doc = await _get_round()
    if not round_doc or round_doc.get("phase") != "betting":
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Las apuestas estan cerradas"})
        return
    if any(b["user_id"] == user["id"] for b in round_doc.get("bets", [])):
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Ya apostaste en esta ronda"})
        return

    new_balance = await _deduct_coins(user["id"], amount)
    if new_balance is None:
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Saldo insuficiente"})
        return

    bet = {
        "user_id": user["id"], "name": user.get("persona_name") or "Survivor",
        "avatar": user.get("avatar"), "amount": amount, "auto_cashout": auto_cashout,
        "cashed_at": None, "payout": 0,
    }
    # Atomic: only succeeds if the phase is still "betting" and this user hasn't
    # already bet -- closes the same race the two checks above can't fully rule out.
    updated = await _db.crash_round.find_one_and_update(
        {"id": "current", "phase": "betting", "bets.user_id": {"$ne": user["id"]}},
        {"$push": {"bets": bet}},
    )
    if not updated:
        await _add_coins(user["id"], amount)  # refund -- the bet never landed
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "No se pudo procesar la apuesta"})
        return

    jackpot = await _bump_jackpot(amount * JACKPOT_RATE)
    # The jackpot rides on bet_placed instead of its own message type -- one bet
    # can only ever change the pool by that bet's own cut, so any client already
    # tracking bets can just fold this number in with no extra event to listen for.
    await manager.broadcast({"type": Outgoing.BET_PLACED, "bet": bet, "jackpot": jackpot})
    await manager.send(websocket, {"type": Outgoing.BET_ACK, "user_id": user["id"], "amount": amount,
                                   "auto_cashout": auto_cashout, "coins": new_balance})


async def _pay_cashout(user_id: str, multiplier: float, bet_amount: int) -> Optional[int]:
    """Atomically mark one bet cashed-out at `multiplier` and pay it. Returns the
    new coin balance, or None if there was nothing left to settle (already cashed
    out, or the round moved on under us)."""
    payout = int(bet_amount * multiplier)
    result = await _db.crash_round.update_one(
        {"id": "current", "phase": "running",
         "bets": {"$elemMatch": {"user_id": user_id, "cashed_at": None}}},
        {"$set": {"bets.$.cashed_at": multiplier, "bets.$.payout": payout}},
    )
    if result.modified_count == 0:
        return None
    balance = await _add_coins(user_id, payout)
    if balance is None:
        # The bet is already marked cashed, so there is nothing to unwind and no
        # retry that could help; _add_coins has logged the lost credit. Report it
        # as "nothing to settle" so the player is told something went wrong
        # rather than being shown a payout that never reached their balance.
        logger.error("[crash] cashout settled but not credited user=%s payout=%s", user_id, payout)
        return None
    return balance


async def _handle_cashout(websocket: WebSocket, user: dict) -> None:
    round_doc = await _get_round()
    if not round_doc or round_doc.get("phase") != "running":
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "La ronda no esta en juego"})
        return
    bet = next((b for b in round_doc.get("bets", []) if b["user_id"] == user["id"]), None)
    if not bet or bet.get("cashed_at") is not None:
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "No tienes una apuesta activa"})
        return

    elapsed = time.time() - round_doc["running_started_at"]
    current_mult = multiplier_at(elapsed)
    if current_mult >= round_doc["crash_point"]:
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Demasiado tarde, la nave revento"})
        return

    new_balance = await _pay_cashout(user["id"], current_mult, bet["amount"])
    if new_balance is None:
        await manager.send(websocket, {"type": Outgoing.ERROR, "message": "Ya cobraste esta ronda"})
        return

    payout = int(bet["amount"] * current_mult)
    await _record_bet(bet, payout, current_mult, "win")
    await manager.broadcast({"type": Outgoing.USER_CASHOUT, "user_id": user["id"],
                             "multiplier": current_mult, "payout": payout})
    await manager.send(websocket, {"type": Outgoing.CASHOUT_ACK, "multiplier": current_mult,
                                   "payout": payout, "coins": new_balance})


async def _settle_reached_auto_cashouts(threshold: float, *, strict: bool) -> None:
    """Pay every un-cashed auto-cashout bet whose target has been reached.

    strict=False (every tick while running): target <= threshold -- the live
    multiplier has caught up to the player's target.
    strict=True (once, right as the round crashes): target < threshold -- with
    TICK_SECONDS no longer tiny, a target can sit strictly between two discrete
    tick samples that straddle crash_point, and would otherwise never be paid
    even though the real continuous curve did pass through it. Any target below
    crash_point genuinely happened on that continuous curve, so it still wins,
    exactly like a normal auto-cashout would have.
    """
    round_doc = await _get_round()
    for bet in (round_doc or {}).get("bets", []):
        target = bet.get("auto_cashout")
        if bet.get("cashed_at") is not None or not target:
            continue
        reached = target < threshold if strict else target <= threshold
        if not reached:
            continue
        new_balance = await _pay_cashout(bet["user_id"], target, bet["amount"])
        if new_balance is None:
            continue
        payout = int(bet["amount"] * target)
        await _record_bet(bet, payout, target, "win")
        await manager.broadcast({"type": Outgoing.USER_CASHOUT, "user_id": bet["user_id"],
                                 "multiplier": target, "payout": payout})
        await manager.send_to_user(bet["user_id"], {"type": Outgoing.CASHOUT_ACK, "multiplier": target,
                                                    "payout": payout, "coins": new_balance})


# ---------------------------------------------------------------------------
# Moon Pool settlement
# ---------------------------------------------------------------------------
async def _settle_jackpot(round_no: int, round_doc: dict) -> Optional[dict]:
    """Pay the Moon Pool to everyone in this round who cashed out at
    JACKPOT_MULTIPLIER or better. Returns the win record, or None when nobody
    qualified (the pool is left untouched and rolls over).

    Call this exactly once per round, behind the running -> crashed latch in
    _finish_round: it claims the pool destructively, so a second call for the
    same round would pay a second time out of the next round's pool.
    """
    winners = [b for b in (round_doc.get("bets") or []) if qualifies_for_jackpot(b)]
    if not winners:
        return None

    claimed = await _claim_jackpot()
    pool = int(claimed)
    # Sub-coin dust cannot be paid in whole coins -- hand it straight back so it
    # keeps accruing instead of being rounded out of the pool every win.
    if claimed - pool > 0:
        await _bump_jackpot(claimed - pool)
    if pool < JACKPOT_MIN_PAYOUT:
        if pool > 0:
            await _bump_jackpot(pool)
        return None

    shares = split_jackpot(pool, winners)
    paid: list[dict] = []
    unpaid = 0
    for winner, share in zip(winners, shares):
        if share <= 0:
            continue
        try:
            balance = await _add_coins(winner["user_id"], share)
        except Exception:
            logger.exception("[crash] moon pool credit raised round=%s user=%s share=%s",
                             round_no, winner.get("user_id"), share)
            balance = None
        if balance is None:
            # Claimed but not delivered: return this share to the pool. The house
            # never keeps coins it took from the pool and failed to hand over.
            unpaid += share
            continue
        paid.append({"user_id": winner["user_id"], "name": winner.get("name"),
                     "avatar": winner.get("avatar"), "amount": winner.get("amount"),
                     "cashed_at": winner.get("cashed_at"), "share": share})
        await _record_bet(winner, share, JACKPOT_MULTIPLIER, "win", kind="moon_pool")
        # Their own share and new balance only -- the pool's new value rides on
        # the broadcast below, which is the single authority on that number.
        await manager.send_to_user(winner["user_id"], {
            "type": Outgoing.JACKPOT, "round_no": round_no, "won": share,
            "coins": balance, "multiplier": JACKPOT_MULTIPLIER,
        })
    if unpaid:
        await _bump_jackpot(unpaid)
        logger.error("[crash] moon pool round=%s returned %s undelivered coins to the pool",
                     round_no, unpaid)
    if not paid:
        return None

    win = {"round_no": round_no, "amount": pool - unpaid, "ts": time.time(),
           "multiplier": JACKPOT_MULTIPLIER,
           "winners": [{"name": p["name"], "share": p["share"], "cashed_at": p["cashed_at"]}
                       for p in paid]}
    await _db.crash_meta.update_one({"id": "meta"}, {"$set": {"last_win": win}}, upsert=True)
    await _db.crash_jackpot_wins.insert_one(dict(win))
    logger.info("[crash] moon pool WON round=%s amount=%s winners=%s at %sx+",
                round_no, win["amount"], [p["name"] for p in paid], JACKPOT_MULTIPLIER)
    await manager.broadcast({"type": Outgoing.JACKPOT, "round_no": round_no,
                             "jackpot": await _get_jackpot(), "won_total": win["amount"],
                             "winners": paid, "multiplier": JACKPOT_MULTIPLIER})
    return win


# ---------------------------------------------------------------------------
# Round phase machine
# ---------------------------------------------------------------------------
async def _start_betting_phase(round_no: int) -> dict:
    server_seed = secrets.token_hex(16)
    server_hash = hashlib.sha256(server_seed.encode()).hexdigest()
    client_seed = "public"  # fixed and public: crash_point is reproducible once server_seed leaks
    crash_point = generate_crash_point(server_seed, client_seed, round_no)
    now = time.time()
    round_doc = {
        "id": "current", "round_no": round_no, "phase": "betting",
        "server_seed": server_seed, "server_hash": server_hash, "client_seed": client_seed,
        "crash_point": crash_point, "bets": [],
        "betting_ends_at": now + BETTING_SECONDS, "running_started_at": None,
    }
    await _db.crash_round.replace_one({"id": "current"}, round_doc, upsert=True)
    await manager.broadcast({
        "type": Outgoing.PHASE_BETTING, "round_no": round_no, "server_hash": server_hash,
        "betting_seconds": BETTING_SECONDS, "betting_ends_at": round_doc["betting_ends_at"],
        # Once a round: the pool's authoritative value. A client that missed a
        # bet_placed or a jackpot event re-syncs here instead of drifting all
        # session on a number it only ever accumulated locally.
        "jackpot": await _get_jackpot(),
    })
    return round_doc


async def _start_running_phase() -> float:
    running_started_at = time.time()
    await _db.crash_round.update_one(
        {"id": "current"}, {"$set": {"phase": "running", "running_started_at": running_started_at}})
    await manager.broadcast({"type": Outgoing.PHASE_RUNNING, "running_started_at": running_started_at})
    return running_started_at


async def _fly_until_crash(running_started_at: float, crash_point: float) -> None:
    """Tick every TICK_SECONDS until the multiplier would reach crash_point, resolving
    auto-cashouts along the way. Breaks BEFORE broadcasting a tick that would reach or
    exceed crash_point, so the crashed event's crash_point is always the true final
    number the client ever needs to freeze on -- no tick can ever overshoot it."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        elapsed = time.time() - running_started_at
        current_mult = multiplier_at(elapsed)
        if current_mult >= crash_point:
            # Catch any auto-cashout target the coarser tick sampling stepped
            # over on this final stretch -- see _settle_reached_auto_cashouts.
            await _settle_reached_auto_cashouts(crash_point, strict=True)
            return
        await manager.broadcast({"type": Outgoing.TICK, "multiplier": current_mult, "elapsed": elapsed})
        await _settle_reached_auto_cashouts(current_mult, strict=False)


async def _finish_round(round_no: int, crash_point: float) -> None:
    # One-shot latch: only the running -> crashed transition settles this round.
    # find_one_and_update returns the document only if IT made the flip, so a
    # second call for the same round (a retry after a mid-round exception) gets
    # None and cannot record the history row or pay the Moon Pool twice.
    settled = await _db.crash_round.find_one_and_update(
        {"id": "current", "round_no": round_no, "phase": "running"},
        {"$set": {"phase": "crashed"}},
        return_document=ReturnDocument.AFTER)
    await manager.broadcast({"type": Outgoing.PHASE_CRASHED, "crash_point": crash_point})
    if not settled:
        logger.warning("[crash] round %s was already finished, skipping settlement", round_no)
        return
    # Every bet still flying when the round busts is a loss. Recorded here rather
    # than at bust time because THIS is the one call latched to run exactly once.
    for lost in (settled.get("bets") or []):
        if lost.get("cashed_at") is None:
            await _record_bet(lost, 0, 0.0, "lose")
    if round_no % LEDGER_TRIM_EVERY == 0:
        await _trim_ledger()
    await _db.crash_history.insert_one({"round_no": round_no, "crash_point": crash_point, "ts": time.time()})
    old = await _db.crash_history.find({}, {"_id": 1}).sort("round_no", -1).skip(200).to_list(50)
    if old:
        await _db.crash_history.delete_many({"_id": {"$in": [o["_id"] for o in old]}})
    # Contained on purpose: the Moon Pool must never be able to take the round
    # loop down with it -- a failed settlement leaves the pool intact and the
    # next round still runs.
    try:
        await _settle_jackpot(round_no, settled)
    except Exception:
        logger.exception("[crash] moon pool settlement failed round=%s", round_no)


async def _rescue_abandoned_bets() -> None:
    """Refund every un-cashed stake left in a round that never settled.

    A round that dies mid-flight — the 2026-08-20 case: mongod terminated by an
    FTDC rename collision while bets were flying (rounds 129676/129680/130698/
    130897 that night) — used to be silently REPLACED by the next round's
    _start_betting_phase: its bets array vanished with the doc, the stakes had
    already been deducted at bet time, and nothing refunded or even recorded
    them. Worse, the stale doc still said "betting", so players kept pushing
    NEW stakes into a round no loop iteration would ever settle.

    Called from the round loop before every round starts, so the rescue runs
    exactly when the database is back. Order is load-bearing:
      1. FREEZE the doc (phase -> crashed + rescued marker): from this write on,
         _handle_bet's atomic push can no longer add stakes to the dead round.
         `rescued` is what distinguishes this from a normally settled round —
         _finish_round never sets it, and a normally crashed doc must never be
         refunded (its losses are real and already recorded).
      2. Refund per-bet behind an atomic per-bet claim (cashed_at None ->
         "refund"), so a rescue that dies halfway and reruns can neither pay a
         bet twice nor lose the rest. If the credit itself fails after a claim,
         the claim is released best-effort and the error names user and amount.
    """
    doc = await _db.crash_round.find_one({"id": "current"})
    if not doc:
        return
    if doc.get("phase") == "crashed" and not doc.get("rescued"):
        return    # settled normally: losses are real, never refund them
    uncashed = [b for b in (doc.get("bets") or []) if b.get("cashed_at") is None]
    if doc.get("phase") != "crashed":
        if not uncashed:
            return    # nothing at stake; the loop will replace it normally
        froze = await _db.crash_round.find_one_and_update(
            {"id": "current", "round_no": doc.get("round_no"), "phase": doc.get("phase")},
            {"$set": {"phase": "crashed", "rescued": True}},
            return_document=ReturnDocument.AFTER)
        if not froze:
            return    # the doc moved under us; the next iteration re-examines
        doc = froze
    for b in (doc.get("bets") or []):
        if b.get("cashed_at") is not None:
            continue
        user_id, amount = b.get("user_id"), int(b.get("amount") or 0)
        if not user_id or amount <= 0:
            continue
        claim = await _db.crash_round.find_one_and_update(
            {"id": "current", "round_no": doc.get("round_no"),
             "bets": {"$elemMatch": {"user_id": user_id, "cashed_at": None}}},
            {"$set": {"bets.$.cashed_at": "refund"}})
        if not claim:
            continue    # another pass already claimed this bet
        try:
            credited = await _add_coins(user_id, amount)
        except Exception:
            # Claimed but not paid would silently eat the stake on rerun:
            # release the claim (best effort) and let the next pass retry.
            try:
                await _db.crash_round.update_one(
                    {"id": "current", "round_no": doc.get("round_no"),
                     "bets": {"$elemMatch": {"user_id": user_id, "cashed_at": "refund"}}},
                    {"$set": {"bets.$.cashed_at": None}})
            except Exception:
                logger.exception("[crash] round %s refund unclaim ALSO failed user=%s amount=%s"
                                 " — repair by hand", doc.get("round_no"), user_id, amount)
            raise
        if credited is None:
            logger.error("[crash] round %s abandoned; REFUND LOST user=%s amount=%s"
                         " (no user row) — repair by hand",
                         doc.get("round_no"), user_id, amount)
            continue
        await _record_bet(b, amount, 1.0, "refund")
        logger.warning("[crash] round %s abandoned mid-flight; refunded stake user=%s amount=%s",
                       doc.get("round_no"), b.get("name") or user_id, amount)


async def _run_single_round(round_no: int) -> None:
    round_doc = await _start_betting_phase(round_no)
    await asyncio.sleep(BETTING_SECONDS)
    running_started_at = await _start_running_phase()
    await _fly_until_crash(running_started_at, round_doc["crash_point"])
    await _finish_round(round_no, round_doc["crash_point"])
    await asyncio.sleep(ROUND_COOLDOWN_SECONDS)


# ---------------------------------------------------------------------------
# Retirement
# ---------------------------------------------------------------------------
# 2026-08-20, the owner: "remopve crash game". True = the game is REMOVED:
# run_crash_loop announces its receipt, refunds whatever the final round left
# flying (the same rescue the live loop used), and starts NO rounds; the
# websocket answers every connection with a retired notice and closes, so a
# browser still holding an old bundle sees words instead of a spinner. The
# module, its routes and its ledger stay untouched -- flipping this back to
# False (a deploy) restores the game whole.
RETIRED = True
_RETIRED_MSG = "El juego Crash fue retirado de La Isla Nublar."


async def run_crash_loop() -> None:
    """Background task: an endless betting -> running -> crashed sequence. Call once
    from the host app's startup handler after configure() has been called."""
    await asyncio.sleep(2)  # let the rest of the app finish booting first
    # ★ THE ECONOMICS RECEIPT LANDS HERE, NOT IN configure(). server.py calls
    # configure() at module import, before the host app has attached a single
    # logging handler, so that emission goes nowhere -- measured on the live box
    # 2026-08-19 after the first deploy of this wave: every `[crash] moon pool
    # WON` line was in backend.log and the house-edge line was not. This task is
    # started from the app's own startup hook, by which time logging is live.
    logger.info("%s", economics_line())
    if RETIRED:
        # The final round's flying stakes are only rescuable while its doc
        # exists; nothing will ever replace it now, so a few patient attempts
        # cover a database that is still coming up at boot.
        for attempt in range(1, 6):
            try:
                await _rescue_abandoned_bets()
                break
            except Exception:  # noqa: BLE001
                logger.exception("[crash] retirement rescue attempt %s failed", attempt)
                await asyncio.sleep(10)
        logger.info("[crash] RETIRED: no rounds will run; the websocket answers retired")
        return
    meta = await _db.crash_meta.find_one({"id": "meta"}) or {}
    round_no = int(meta.get("last_round_no", 0))
    while True:
        round_no += 1
        try:
            # Refund whatever a dead prior round left flying BEFORE its doc is
            # replaced — this is the only moment those stakes are still visible.
            # Runs on the boot iteration too, so a deploy bounce that abandons
            # its mid-flight round heals itself.
            await _rescue_abandoned_bets()
            await _run_single_round(round_no)
            await _db.crash_meta.update_one({"id": "meta"}, {"$set": {"last_round_no": round_no}}, upsert=True)
        except Exception:
            logger.exception("[crash] round %s failed, retrying shortly", round_no)
            await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
async def _authenticate(websocket: WebSocket) -> Optional[dict]:
    """The first frame on every connection must be {"type":"auth","token":...} --
    never a query-string token, so the JWT never ends up in proxy/access logs."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        return None
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    if message.get("type") != Incoming.AUTH or not message.get("token"):
        return None
    try:
        payload = jwt.decode(message["token"], _jwt_secret, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None
    user = await _db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if user and _ban_check is not None:
        # A banned account gets no socket: same answer as its HTTP session. The
        # check never raises (fail-open, counted, inside webban.check).
        try:
            banned, _row = await _ban_check(user.get("steam_id"))
        except Exception:  # noqa: BLE001
            banned = False
        if banned:
            return None
    return user


async def _send_initial_state(websocket: WebSocket, user: dict) -> None:
    round_doc = await _get_round()
    payload_round, my_bet = None, None
    if round_doc:
        payload_round = _public_round_view(round_doc)
        my_bet = next((b for b in round_doc.get("bets", []) if b["user_id"] == user["id"]), None)
        if round_doc.get("phase") == "running":
            elapsed = time.time() - round_doc["running_started_at"]
            payload_round["elapsed"] = elapsed
            payload_round["current_multiplier"] = multiplier_at(elapsed)

    await manager.send(websocket, {
        "type": Outgoing.STATE,
        "round": payload_round,
        "history": await _get_history(),
        "jackpot": await _get_jackpot(),
        "last_win": await _get_last_win(),
        "my_bet": my_bet,
        "coins": int(user.get("coins", 0)),
        "config": {
            "min_bet": MIN_BET, "max_bet": MAX_BET, "growth_rate": GROWTH_RATE,
            "betting_seconds": BETTING_SECONDS, "jackpot_rate": JACKPOT_RATE,
            "jackpot_multiplier": JACKPOT_MULTIPLIER,
            # Published so the page states the odds from the one live source
            # instead of the browser keeping its own copy of a number that moves.
            "bust_one_in": BUST_ONE_IN,
        },
    })


@router.websocket("/ws/casino/crash")
async def crash_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    if RETIRED:
        # Answer BEFORE authenticating: a retired game owes the visitor one
        # sentence, not an auth handshake. Old bundles reconnect here; the
        # close code stops their retry loop cleanly.
        try:
            await manager.send(websocket, {"type": Outgoing.ERROR, "message": _RETIRED_MSG})
            await websocket.close(code=4410)
        except Exception:  # noqa: BLE001
            pass  # the client may already be gone
        return
    user = await _authenticate(websocket)
    if not user:
        try:
            await websocket.close(code=4401)
        except Exception:
            pass  # the client may already be gone (auth timeout/disconnect)
        return

    try:
        # Send the snapshot BEFORE registering: once registered, the socket is a
        # broadcast target, and a phase/tick event landing ahead of "state" would
        # arrive to a client that has nothing yet to merge it into.
        await _send_initial_state(websocket, user)
        manager.register(websocket, user["id"])
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            action = message.get("type")
            if action == Incoming.BET:
                await _handle_bet(websocket, user, message)
            elif action == Incoming.CASHOUT:
                await _handle_cashout(websocket, user)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(websocket)
