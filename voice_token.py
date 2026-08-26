"""LiveKit JWT minter for La Isla Nublar voice.

Ported from the Arkadia donor (voice_token.py). Server mints HS256 tokens
against the LiveKit shared secret; identity is the caller's Steam64 from the
session (clients cannot influence it). Grants are limited to
roomJoin/canPublish/canSubscribe. Short TTL.

Config is read EXPLICITLY from the LAISLANUBLAR_LIVEKIT_* env vars — never the
generic LIVEKIT_* fallback — so a co-hosted Arkadia config can never leak this
server's room/keys or vice-versa.

Token TTL: LiveKit validates the join token only when a connection is
(re)established — an already-connected participant is never cut at `exp`. The
TTL therefore only bounds how long a minted-but-unused token stays valid and
how old a token livekit-client may still reuse for its internal reconnects, so
it defaults generously (24h) to keep long-lived tabs reconnect-clean; the page
mints a fresh token per join attempt regardless. Tune without a code change:
LAISLANUBLAR_VOICE_TOKEN_TTL_SECS (seconds, clamped 300..604800).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from collections import deque
from threading import Lock
from typing import Final

from fastapi import HTTPException

log = logging.getLogger("laislanublar.voice")

# Explicit LIN LiveKit config (no generic LIVEKIT_* fallback).
LIVEKIT_URL: Final[str] = os.environ.get("LAISLANUBLAR_LIVEKIT_URL", "")
LIVEKIT_API_KEY: Final[str] = os.environ.get("LAISLANUBLAR_LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET: Final[str] = os.environ.get("LAISLANUBLAR_LIVEKIT_API_SECRET", "")
LIVEKIT_ROOM: Final[str] = os.environ.get("LAISLANUBLAR_LIVEKIT_ROOM", "laislanublar")

def _ttl_from_env() -> int:
    """Safe-parse the TTL knob; a bad value falls back to the 24h default and
    the clamp keeps operator typos from minting instant-dead or year-long tokens."""
    raw = os.environ.get("LAISLANUBLAR_VOICE_TOKEN_TTL_SECS", "")
    try:
        val = int(str(raw).strip() or 0)
    except (TypeError, ValueError):
        log.warning("voice: bad LAISLANUBLAR_VOICE_TOKEN_TTL_SECS=%r — using default", raw)
        val = 0
    if val <= 0:
        val = 24 * 60 * 60
    return max(300, min(val, 7 * 24 * 60 * 60))


_TOKEN_TTL_SECONDS: Final[int] = _ttl_from_env()
_RATE_WINDOW: Final[float] = 60.0
_RATE_LIMIT_IDENTITY: Final[int] = 30   # donor value (multi-tab/reconnect burst)
_RATE_LIMIT_IP: Final[int] = 120        # donor value (CGNAT-shared clusters)
_RATE_TRIM_INTERVAL: Final[float] = 30.0
_rate_hits_identity: dict[str, deque] = {}
_rate_hits_ip: dict[str, deque] = {}
_rate_lock = Lock()
_rate_last_trim = 0.0


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _mint(identity: str, room: str, ttl: int) -> str:
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise HTTPException(503, "El chat de voz no está configurado.")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": LIVEKIT_API_KEY,
        "sub": identity,
        "nbf": now,
        "exp": now + ttl,
        "name": identity,
        "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True},
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode("ascii"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("ascii"))
    sig = hmac.new(LIVEKIT_API_SECRET.encode("ascii"), f"{h}.{p}".encode("ascii"), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def _rate_check(bucket: dict[str, deque], key: str, limit: int) -> None:
    global _rate_last_trim
    now = time.monotonic()
    with _rate_lock:
        if now - _rate_last_trim >= _RATE_TRIM_INTERVAL:
            _rate_last_trim = now
            cutoff = now - _RATE_WINDOW
            for hits in (_rate_hits_identity, _rate_hits_ip):
                for bk in list(hits.keys()):
                    q0 = hits.get(bk)
                    while q0 and q0[0] < cutoff:
                        q0.popleft()
                    if not q0:
                        hits.pop(bk, None)
        q = bucket.setdefault(key, deque())
        cutoff = now - _RATE_WINDOW
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Demasiadas solicitudes de voz — espera un momento.")
        q.append(now)


def mint_token(steam_id: str, client_ip: str = "") -> dict:
    """Mint a voice token for a validated Steam64 identity. Raises HTTPException
    on rate limit (429) or when voice is not configured (503)."""
    identity = str(steam_id or "").strip()
    _rate_check(_rate_hits_identity, identity, _RATE_LIMIT_IDENTITY)
    _rate_check(_rate_hits_ip, str(client_ip or "unknown"), _RATE_LIMIT_IP)
    token = _mint(identity, LIVEKIT_ROOM, _TOKEN_TTL_SECONDS)
    now = int(time.time())
    return {
        "token": token,
        "room": LIVEKIT_ROOM,
        "identity": identity,
        "expires_at": now + _TOKEN_TTL_SECONDS,
        "livekit_url": LIVEKIT_URL,
        # Server epoch ms so the client can correct for local clock skew before
        # deciding a token is expired (donor clock-skew mitigation).
        "server_time_ms": int(time.time() * 1000),
    }
