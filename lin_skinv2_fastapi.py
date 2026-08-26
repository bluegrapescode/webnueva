# -*- coding: utf-8 -*-
"""FastAPI transport for :mod:`webcore.bespoke_skin_contract`.

Three routes, no logic.  Everything the engine decides is turned into a status
code by :data:`engine.STATUS_BY_REASON`, so the aiohttp sibling cannot answer
the same refusal differently.

★ FASTAPI IS IMPORTED AT MODULE SCOPE, AND IT HAS TO BE (measured 2026-08-24 by
booting Fangs and Ferns' real app).  An earlier draft imported it inside
:func:`install` so an aiohttp owner's bundle would never touch FastAPI - but
this file carries ``from __future__ import annotations``, so every annotation
is a STRING that FastAPI resolves against the function's ``__globals__``.  With
the import local to ``install``, ``Request`` was not a module global, FastAPI
could not resolve it, and it fell back to treating the parameter as a QUERY
STRING FIELD: ``GET /api/studio/skin-contract`` answered
``422 {"loc":["query","request"],"msg":"Field required"}`` on every call.  The
studio would have probed a route that could never answer.

This costs an aiohttp owner nothing: they import :mod:`.aiohttp_mount`, and
neither mount imports the other.
"""
from __future__ import annotations

import json
import logging

from fastapi import Depends, Request, Response

import lin_skin_contract as skin_contract
import lin_skinv2_engine as _engine

log = logging.getLogger("webcore.bespoke_skin_contract.fastapi")

MANIFEST_ROUTE = "/api/studio/skin-contract"
STATE_ROUTE = "/api/studio/skin-contract-state"
APPLY_ROUTE = "/api/studio/apply-v2"


def install(app, adapter: _engine.OwnerAdapter, *, auth_dependency,
            manifest_route: str = MANIFEST_ROUTE,
            state_route: str = STATE_ROUTE,
            apply_route: str = APPLY_ROUTE):
    """Register the v2 routes.  Returns the engine so tests can drive it.

    ★ CALL THIS BEFORE THE CATCH-ALL STATIC MOUNT.  Every bespoke site in the
    fleet mounts ``StaticFiles(directory=..., html=True)`` at ``/``; a route
    added after it is shadowed and answers 404 with no error anywhere.

    ``auth_dependency`` is the owner's existing SteamID dependency - the same
    one their v1 apply uses, so identity can never diverge between the two
    lanes.
    """
    built = _engine.build_engine(adapter)

    async def get_manifest(request: Request):
        """The immutable game table.  Cached hard; it changes only on a patch."""
        bundle = built.manifest()
        if bundle is None:
            return Response(
                content=b'{"ok":false,"error":"skin_contract_unavailable"}',
                status_code=503, media_type="application/json")
        raw, etag = bundle
        headers = {"Cache-Control": "public, max-age=31536000, immutable",
                   "ETag": etag, "X-Content-Type-Options": "nosniff"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=raw, media_type="application/json",
                        headers=headers)

    async def get_state():
        """The capability probe.  ★ ALWAYS 200 - 'off' is an answer, not an
        error, and a studio that cannot read this cannot fall back to v1."""
        return {"ok": True, "skin_contract": built.state()}

    async def apply_v2(request: Request, steam_id: str = Depends(auth_dependency)):
        try:
            body = await request.json()
        except Exception:
            body = None
        outcome = built.apply(steam_id, body, request=request)
        return Response(
            content=_json(outcome.payload()), status_code=outcome.status,
            media_type="application/json")

    app.add_api_route(manifest_route, get_manifest, methods=["GET"],
                      include_in_schema=False)
    app.add_api_route(state_route, get_state, methods=["GET"],
                      include_in_schema=False)
    app.add_api_route(apply_route, apply_v2, methods=["POST"],
                      include_in_schema=False)
    log.info("skin contract v2 mounted owner=%s slots=%d",
             adapter.owner_key, len(skin_contract.ALL_SLOTS))
    return built


def _json(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")
