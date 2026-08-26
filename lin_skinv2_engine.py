# -*- coding: utf-8 -*-
"""Transport-agnostic contract-v2 engine for the BESPOKE (non-webcore) sites.

Sixteen owners run their own websites - FastAPI (Fangs and Ferns, German
Dominion, Jurassic Haven...), aiohttp (Natural Selection...), one or two
static-plus-bridge shapes - and none of them can import :mod:`webcore.designs`
or :mod:`webcore.skin_apply`.  Before this module they were about to each carry
a hand-copied backend: the Codex-staged
``C:\\ServerStaging\\gd_skinv2_20260824\\backend\\skin_contract_routes.py`` and
its byte-identical twin already sitting inside FnF's own tree.

★ THE COPIES HAD ALREADY DRIFTED, WHICH IS THE WHOLE ARGUMENT.  Measured
2026-08-24 against ``webcore/skin_contract.py``:

  1. ``no_manifest`` was MISSING.  The copy called ``game_build()`` straight,
     so a bundle shipped without ``skincontract/skin_capabilities.v2.json``
     beside it answered the studio with a 500 the instant the game proved
     itself - the exact defect the canonical fixed on NAD Evrima.
  2. ``V2_ALIVE_LEAF`` and the ``alive_file`` check were MISSING, so a forged
     capability could point the website at another owner's heartbeat file.
  3. A SECOND PRIVATE RATE BUDGET.  The copy kept its own 6/min table beside
     the owner's v1 one, so a player got the v1 budget AND a v2 budget - the
     opposite of one funnel.
  4. The wire said ``request_id`` where the fleet's consumer reads ``cmd_id``.

So this module owns the LOGIC once, imports the canonical
:mod:`webcore.skin_contract` and :mod:`webcore.skin_wire` rather than copying
them, and takes everything owner-specific as injected callables.  Each owner is
an :class:`OwnerAdapter` literal, never a fork.

★ NOTHING HERE RAISES AT A TRANSPORT BOUNDARY.  Every public entry point
returns an :class:`Outcome`; the mounts turn that into a status code.  An
adapter callable that blows up is contained and reported as a named refusal,
because a bespoke owner's helper failing must not 500 a studio page.

★ THE DANGEROUS DIRECTION IS GATED IN CODE, NOT IN A COMMENT.  A v2 command
must never land in ``skin_commands.json``.  The channel is derived from the
capability file's own directory and its leaf is asserted against
:data:`skin_contract.V2_COMMAND_LEAF` immediately before the write, so no
adapter, config value or request can redirect it onto the v1 queue.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import lin_skin_contract as skin_contract
import lin_skin_wire as skin_wire

log = logging.getLogger("webcore.bespoke_skin_contract")

#: A SteamID64 is exactly seventeen digits.  Anything else is a wrong-id, and
#: an owner adapter that resolves a target for an admin lane is held to it too.
_STEAMID_RE = re.compile(r"^\d{17}$")

#: Refusal -> HTTP status.  Kept here so the FastAPI and aiohttp mounts cannot
#: answer the same refusal with two different codes.
STATUS_BY_REASON: dict[str, int] = {
    "ok": 202,
    "no_active_dino": 409,
    "actor_identity_unavailable": 409,
    "wrong_active_species": 409,
    "channel_busy": 409,
    "bad_recipe": 422,
    "invalid_target": 422,
    "rate_limited": 429,
    "not_authorized": 403,
    "unsupported_skin_contract": 503,
    "manifest_unavailable": 503,
    "manifest_hash_mismatch": 503,
    "target_resolution_failed": 503,
    "roster_unavailable": 503,
    "write_failed": 503,
    "entry_too_large": 503,
    "misconfigured": 503,
}

#: What a player is told.  A refusal a player can act on says so; one they
#: cannot is deliberately vague rather than leaking the island's internals.
MESSAGE_BY_REASON: dict[str, str] = {
    "no_active_dino": "Spawn in on the island first, then apply.",
    "actor_identity_unavailable": (
        "We can see you online but not which animal you are on yet. "
        "Give it a few seconds and try again."),
    "wrong_active_species": (
        "That design is for a different dinosaur than the one you are on."),
    "channel_busy": "The island is painting another skin. Try again in a moment.",
    "bad_recipe": "Those colours are not a valid design.",
    "invalid_target": "That player id is not valid.",
    "rate_limited": "That is enough applies for one minute. Try again shortly.",
    "not_authorized": "You do not have access to the advanced editor.",
    "unsupported_skin_contract": (
        "Advanced skin controls are not armed on this island."),
    "manifest_unavailable": "The advanced skin table is not loaded on this site.",
    "manifest_hash_mismatch": "The advanced skin table is not loaded on this site.",
    "target_resolution_failed": "Could not work out who to paint. Try again.",
    "roster_unavailable": "Could not read the island roster. Try again.",
    "write_failed": "Could not queue that skin. Try again.",
    "entry_too_large": "That design is too large to send.",
    "misconfigured": "Advanced skin controls are not set up on this site.",
}


@dataclass(frozen=True)
class Outcome:
    """One engine answer.  ``ok`` is the only success."""

    ok: bool
    reason: str
    status: int
    detail: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        return MESSAGE_BY_REASON.get(self.reason, "That did not work.")

    def payload(self) -> dict:
        """The JSON body both mounts send, success or refusal."""
        if self.ok:
            return {"ok": True, "queued": True,
                    "contract_version": skin_contract.SCHEMA_VERSION,
                    **self.detail}
        return {"ok": False, "error": self.reason, "message": self.message,
                **self.detail}


def _refuse(reason: str, **detail) -> Outcome:
    return Outcome(False, reason, STATUS_BY_REASON.get(reason, 503), dict(detail))


@dataclass(frozen=True)
class OwnerAdapter:
    """Everything that differs between two bespoke owners, and nothing else.

    An owner's integration is one literal of this.  If a new owner needs a
    field that is not here, that is a signal the framework is missing a seam -
    add the seam here so every sibling gets it, never a second engine.

    ``owner_key`` MUST equal the slug the game-side writer stamps into
    ``skin_contract_capabilities.json``.  It is compared case-folded and a
    mismatch is a named ``wrong_owner`` refusal, so pointing two owners at one
    Saved directory cannot cross-paint.

    ``alive_leaf`` is the owner's OWN heartbeat file (FnF publishes
    ``fangsandferns_mod_alive.json``).  It is used only while the capability
    does NOT declare an ``alive_file`` of its own; when it does, the canonical
    contract requires that declaration to be exactly
    ``skin_contract_v2_alive.json`` and derives the path itself.  ★ A writer
    that declares any other alive file is refused - that is the check the
    staged copies had dropped.

    ``rate_reserve`` / ``rate_rollback`` are the ONE budget.  ★ There is
    deliberately no fallback in this module: an owner who does not wire these
    to the SAME per-player budget their v1 apply consumes is refused at
    :func:`build_engine` rather than silently given a second allowance.
    ``rate_reserve`` returns an opaque token (or ``None`` when the owner's
    budget has nothing to roll back); it must raise nothing and instead return
    the sentinel :data:`RATE_DENIED` when the player is over budget.
    """

    owner_key: str
    saved_dir: Path
    alive_leaf: str
    find_active_dino: Callable[[str], Any]
    rate_reserve: Callable[[str], Any]
    rate_rollback: Callable[[Any], None]
    namespace: str = ""
    manifest_sha256: str = ""
    authorize: Callable[[str], Any] | None = None
    resolve_target: Callable[[str, Any], Any] | None = None
    on_queued: Callable[[str, dict, dict, Any], None] | None = None
    #: ★ FOR THE OWNER WHOSE WEBSITE MAY NOT WRITE GAME FILES AT ALL.
    #: Natural Selection's site is contractually forbidden from touching the
    #: Saved directory: it signs a request into ``skin_apply_requests.json`` and
    #: the BOT re-checks ownership and the live actor before writing the real
    #: command.  A default landing would break that contract outright, so an
    #: owner may replace ONLY the final write.  Everything above it - the
    #: capability proof, the boot token, the validated recipe, the budget, and
    #: the v2-leaf assertion - still runs exactly as it does for everyone else,
    #: and the handler is given the proven target path so it can see which
    #: channel the fleet would have used.  Signature:
    #: ``land(target_path, entry, request) -> (ok: bool, reason: str)``.
    land_command: Callable[[Path, dict, Any], tuple] | None = None


#: The sentinel :attr:`OwnerAdapter.rate_reserve` returns when the caller is
#: over their budget.  A sentinel rather than an exception keeps the owner's
#: helper free of any web-framework import.
RATE_DENIED = object()


class Engine:
    """The three operations a bespoke studio needs, and no transport."""

    def __init__(self, adapter: OwnerAdapter):
        self._adapter = adapter

    # -- capability ---------------------------------------------------------

    @property
    def capability_path(self) -> Path:
        return Path(self._adapter.saved_dir) / skin_contract.WRITER_CAPABILITY_LEAF

    @property
    def alive_path(self) -> Path:
        return Path(self._adapter.saved_dir) / self._adapter.alive_leaf

    def _manifest_ok(self) -> str:
        """``""`` when the shipped table is the one this build expects.

        ★ ABSENCE IS A STATE, NOT A CRASH.  A bespoke bundle sealed without
        ``skincontract/skin_capabilities.v2.json`` beside it is a real and
        expected first-ship condition; it answers ``no_manifest`` through the
        canonical contract and this returns the named refusal, never a 500.
        """
        try:
            raw = skin_contract.manifest_bytes()
        except FileNotFoundError:
            return "manifest_unavailable"
        except Exception:
            log.exception("skin v2 manifest unreadable owner=%s",
                          self._adapter.owner_key)
            return "manifest_unavailable"
        expected = str(self._adapter.manifest_sha256 or "").strip().lower()
        if expected:
            import hashlib
            if hashlib.sha256(raw).hexdigest() != expected:
                return "manifest_hash_mismatch"
        return ""

    def state(self, *, now: float | None = None) -> dict:
        """The compact, fail-closed gate the frontend probes.

        Never raises and always answers the same shape, so a studio page can
        decide between the v2 editor and the v1 seven-slot fallback from one
        request even on an owner where none of this is set up.
        """
        try:
            problem = self._manifest_ok()
            if problem:
                return skin_contract.disabled_capability(
                    "no_manifest" if problem == "manifest_unavailable" else problem)
            return skin_contract.effective_capability(
                self.capability_path, alive_path=self.alive_path,
                expected_owner_key=self._adapter.owner_key, now=now)
        except Exception:
            log.exception("skin v2 state failed owner=%s", self._adapter.owner_key)
            return skin_contract.disabled_capability("state_unavailable")

    def manifest(self) -> tuple[bytes, str] | None:
        """``(bytes, etag)`` of the checked game table, or ``None``."""
        try:
            if self._manifest_ok():
                return None
            return skin_contract.manifest_bytes(), skin_contract.manifest_etag()
        except Exception:
            log.exception("skin v2 manifest failed owner=%s",
                          self._adapter.owner_key)
            return None

    # -- apply --------------------------------------------------------------

    def apply(self, actor_id: str, recipe: Any, *, request: Any = None,
              now: float | None = None, preauthorized: bool = False) -> Outcome:
        """Validate -> prove the writer -> reserve budget -> land ONE command.

        The order is the canonical one and it is load-bearing: a malformed or
        unsupported v2 request must leave every mutable surface untouched, so
        the budget is reserved only once the command is certain to be sent, and
        rolled back if the landing itself fails.

        ★ ``preauthorized`` IS THE STORE LANE, AND IT IS NOT A BYPASS.
        :attr:`OwnerAdapter.authorize` gates FREE-FORM AUTHORING - "may this
        player compose arbitrary colours in the studio" - which on most owners
        is admins only.  Applying a skin the player OWNS is a different and
        stronger question, already answered by the caller's own catalogue
        ownership check, and every bespoke owner's v1 store route deliberately
        skips the authoring gate for exactly that reason.  Without this flag a
        store route wired to this engine would refuse to paint a skin the
        player had already paid for.  The caller opting in must have run a real
        entitlement check first; nothing else here is relaxed.
        """
        try:
            return self._apply(actor_id, recipe, request=request, now=now,
                               preauthorized=bool(preauthorized))
        except Exception as exc:
            # ★ AN OWNER'S OWN REFUSAL IS NOT A CRASH (measured 2026-08-24 on
            # FnF's real app).  `_apply` deliberately re-raises the owner's
            # framework HTTPException so their wording and status survive - and
            # this blanket guard was then catching it and answering
            # "Could not queue that skin. Try again." with a 503.  A player
            # told the studio is admins-only saw a fake server error instead,
            # and the log line said the engine had crashed when nothing had.
            if _is_transport_refusal(exc):
                raise
            log.exception("skin v2 apply crashed owner=%s",
                          self._adapter.owner_key)
            return _refuse("write_failed")

    def _apply(self, actor_id: str, recipe: Any, *, request: Any,
               now: float | None, preauthorized: bool = False) -> Outcome:
        adapter = self._adapter
        actor_id = str(actor_id or "").strip()
        if not _STEAMID_RE.fullmatch(actor_id):
            return _refuse("invalid_target")

        problem = self._manifest_ok()
        if problem:
            return _refuse(problem)

        if adapter.authorize is not None and not preauthorized:
            try:
                adapter.authorize(actor_id)
            except _PassThrough:
                raise
            except Exception as exc:
                if _is_transport_refusal(exc):
                    raise
                log.exception("skin v2 authorize failed owner=%s",
                              adapter.owner_key)
                return _refuse("not_authorized")

        # Whose animal gets painted.  Defaults to the caller; an owner with an
        # admin lane may resolve someone else, and is held to a real SteamID64.
        target_id = actor_id
        if adapter.resolve_target is not None:
            try:
                resolved = adapter.resolve_target(actor_id, request)
            except Exception as exc:
                if _is_transport_refusal(exc):
                    raise
                log.exception("skin v2 target resolution failed owner=%s",
                              adapter.owner_key)
                return _refuse("target_resolution_failed")
            target_id = str(resolved or "").strip()
            if not _STEAMID_RE.fullmatch(target_id):
                return _refuse("invalid_target")

        try:
            dino = adapter.find_active_dino(target_id)
        except Exception:
            log.exception("skin v2 roster read failed owner=%s",
                          adapter.owner_key)
            return _refuse("roster_unavailable")
        if not isinstance(dino, dict) or not dino:
            return _refuse("no_active_dino")
        # ★ THE COMPANION WRITER CORROBORATES THE EXACT ACTOR before it paints.
        # A roster row with no actor name cannot satisfy that fence, so refuse
        # here rather than queue a job the island will drop on the floor.
        actor_name = str(dino.get("actor_name") or "").strip()
        if not actor_name:
            return _refuse("actor_identity_unavailable")
        if str(dino.get("host") or "local") != "local":
            return _refuse("no_active_dino")

        live_class = str(dino.get("class") or "")
        live_species = skin_wire.manifest_species_key(live_class)
        if not live_species:
            return _refuse("wrong_active_species")

        normalised = normalise_recipe(recipe)
        if normalised is None:
            return _refuse("bad_recipe")
        # ★ A V1 PRESET OPENED IN THE V2 EDITOR IS NOT A V2 RECIPE.  Seven
        # slots and no ``contract_version`` is the frozen v1 wire; it is the
        # EDITOR's job to offer defaults for teeth/mouth/claws and stamp the
        # version.  This route refuses it by name instead of inventing the
        # three missing colours server-side.
        if not skin_contract.is_v2(normalised):
            return _refuse("bad_recipe")

        # Species is asserted against the LIVE pawn.  A recipe naming another
        # species is a wrong-id, never quietly repainted onto whatever is on.
        wanted = normalised.pop("species", None)
        if wanted is not None:
            if skin_wire.manifest_species_key(wanted) != live_species:
                return _refuse("wrong_active_species")

        valid = skin_contract.validate_recipe_v2(live_species, normalised)
        if valid is None:
            return _refuse("bad_recipe")

        # ONE read of the proof: state, the boot token stamped into the
        # command, and the queue path - all from the same bytes.  The staged
        # copies read the capability twice (once to compare the owner, once for
        # the context), which lets a rename between the two pair one file's
        # owner with another file's boot.
        state, boot_id, target = skin_contract.writer_context(
            self.capability_path, alive_path=self.alive_path,
            expected_owner_key=adapter.owner_key, now=now)
        if not skin_contract.v2_write_supported(live_species, valid, state):
            return _refuse("unsupported_skin_contract",
                           skin_contract=dict(state))
        if target is None or not boot_id:
            return _refuse("unsupported_skin_contract",
                           skin_contract=dict(state))
        # ★ THE DANGEROUS DIRECTION.  Nothing may put a contract-v2 command in
        # front of a v1 consumer: the legacy poller parses the first fields it
        # recognises and would paint a partial, wrong skin.  The path came from
        # the capability's own directory, but assert the leaf anyway - this is
        # the last line before bytes hit a queue.
        if Path(target).name != skin_contract.V2_COMMAND_LEAF:
            log.error("skin v2 refused a non-v2 channel owner=%s leaf=%s",
                      adapter.owner_key, Path(target).name)
            return _refuse("misconfigured")

        # Budget LAST, so nothing above can charge a player for a refusal.
        try:
            token = adapter.rate_reserve(target_id)
        except Exception as exc:
            if _is_transport_refusal(exc):
                raise
            log.exception("skin v2 rate reserve failed owner=%s",
                          adapter.owner_key)
            return _refuse("rate_limited")
        if token is RATE_DENIED:
            return _refuse("rate_limited")

        cmd_id = skin_wire.new_cmd_id(adapter.namespace or adapter.owner_key,
                                      target_id)
        try:
            entry = skin_wire.build_v2_entry(
                target_id, live_class, valid, cmd_id,
                actor_name=actor_name, writer_boot_id=boot_id)
        except (ValueError, TypeError, KeyError):
            self._rollback(token)
            log.exception("skin v2 entry build failed owner=%s",
                          adapter.owner_key)
            return _refuse("bad_recipe")

        if adapter.land_command is None:
            landed, why = skin_wire.append_single_command(target, entry)
        else:
            # An owner-supplied landing is still held to the engine's contract:
            # it answers (ok, reason) and any exception is a contained refusal,
            # never a 500 on a player who has already been charged.
            try:
                result = adapter.land_command(target, entry, request)
                landed, why = bool(result[0]), str(result[1])
            except Exception as exc:
                if _is_transport_refusal(exc):
                    self._rollback(token)
                    raise
                self._rollback(token)
                log.exception("skin v2 owner landing failed owner=%s cmd=%s",
                              adapter.owner_key, cmd_id)
                return _refuse("write_failed")
        if not landed:
            self._rollback(token)
            return _refuse(why if why in STATUS_BY_REASON else "write_failed")

        # The skin is already on its way.  Bookkeeping that fails must be
        # reported, never rolled back into a refusal the player would read as
        # "it did not work" while their dinosaur changes colour in front of
        # them.
        bookkeeping_ok = True
        if adapter.on_queued is not None:
            try:
                adapter.on_queued(target_id, entry, dino, request)
            except Exception:
                bookkeeping_ok = False
                log.exception("skin v2 bookkeeping failed owner=%s cmd=%s",
                              adapter.owner_key, cmd_id)

        log.info("skin v2 queued owner=%s steam=...%s class=%s cmd=%s",
                 adapter.owner_key, target_id[-4:], live_class, cmd_id)
        return Outcome(True, "ok", 202, {
            "cmd_id": cmd_id, "actor_name": actor_name,
            "class": live_class, "bookkeeping_ok": bookkeeping_ok})

    def _rollback(self, token) -> None:
        try:
            self._adapter.rate_rollback(token)
        except Exception:
            log.exception("skin v2 rate rollback failed owner=%s",
                          self._adapter.owner_key)


class _PassThrough(Exception):
    """Never raised here; the name keeps the intent of the guards readable."""


def _is_transport_refusal(exc: BaseException) -> bool:
    """Is this the owner's own web framework saying 'refused', not a bug?

    An adapter hook is allowed to raise its framework's HTTP error (FastAPI's
    ``HTTPException``, aiohttp's ``HTTPException``) to answer with its own
    wording and status.  Those pass straight through; anything else is a bug
    and becomes a named, contained refusal.  Matched structurally so this
    module imports no web framework.

    ★ THE ATTRIBUTE ALONE IS NOT ENOUGH.  An earlier draft returned True for
    anything carrying ``status_code`` or ``status``, which would have let a
    genuine failure escape as a 500: ``aiohttp.ClientResponseError`` has
    ``.status``, so an owner whose roster helper talks HTTP and gets a 503 from
    its own upstream would have had that exception propagate out of a lane
    whose whole contract is that it never raises.  The class must ALSO come
    from a web framework, or be named like one.
    """
    kind = type(exc)
    name = kind.__name__
    module = str(getattr(kind, "__module__", ""))
    framework = (module.startswith("fastapi")
                 or module.startswith("starlette")
                 or module.startswith("aiohttp.web")
                 or module.startswith("werkzeug")
                 or module.startswith("flask"))
    if framework and (hasattr(exc, "status_code") or hasattr(exc, "status")):
        return True
    # An owner's own subclass, declared in their app, still reads as a refusal
    # when it is named like one and carries a status.
    return (name in ("HTTPException", "HTTPError")
            and (hasattr(exc, "status_code") or hasattr(exc, "status")))


def normalise_recipe(raw: Any) -> dict | None:
    """Accept both transport shapes and return the contract's list shape.

    The fleet's studios send ``{"body": {"r":..,"g":..,"b":..,"a":1}}`` while
    the contract validator speaks ``[r, g, b, a]``.  Converting here means no
    owner writes that conversion, and the alpha rule (v2 slots are opaque; the
    contract itself forces ``a`` to 1.0) is enforced in one place: a caller
    that explicitly asks for transparency is REFUSED rather than silently
    given an opaque colour it did not ask for.
    """
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    # ★ ``glitch`` IS CARRIED THROUGH ON PURPOSE, and it is the one field here
    # that exists only to be REFUSED.  A glitch payload is the out-of-range
    # magnitudes the fleet never lets leave the server, and
    # ``validate_recipe_v2`` refuses any recipe carrying the flag.  An earlier
    # draft of this normaliser copied only the fields v2 uses, which SILENTLY
    # DROPPED the flag - and a dropped flag is an accepted glitch request. A
    # normaliser that strips the field its own validator gates on has disarmed
    # that gate.
    for key in ("contract_version", "pattern", "variation", "theme", "species",
                "glitch"):
        if key in raw:
            out[key] = raw[key]
    for slot in skin_contract.ALL_SLOTS:
        value = raw.get(slot)
        if isinstance(value, dict):
            alpha = value.get("a", 1.0)
            if (isinstance(alpha, bool)
                    or not isinstance(alpha, (int, float))
                    or not math.isfinite(float(alpha))
                    or float(alpha) != 1.0):
                return None
            value = [value.get("r"), value.get("g"), value.get("b"), 1.0]
        out[slot] = value
    return out


def build_engine(adapter: OwnerAdapter) -> Engine:
    """Refuse a misconfigured owner at import time, not on a player's request.

    ★ A FEATURE THAT IS ON MUST WORK THE INSTANT IT IS ON.  Every one of these
    is something an owner integration can only get wrong once, at wiring time,
    and every one of them would otherwise surface as a runtime refusal on a
    live player's first advanced apply.
    """
    if not isinstance(adapter, OwnerAdapter):
        raise TypeError("bespoke skin contract needs an OwnerAdapter")
    if not str(adapter.owner_key or "").strip():
        raise ValueError("bespoke skin contract needs the owner key the game writer stamps")
    if not str(adapter.alive_leaf or "").strip():
        raise ValueError("bespoke skin contract needs the owner's alive beacon leaf")
    if not adapter.saved_dir:
        raise ValueError("bespoke skin contract needs the Saved directory")
    for name in ("find_active_dino", "rate_reserve", "rate_rollback"):
        if not callable(getattr(adapter, name, None)):
            # ★ rate_reserve/rate_rollback are REQUIRED on purpose. The staged
            # copies made the budget optional and quietly kept a private one,
            # which handed every player a second allowance beside their v1 one.
            raise ValueError(
                "bespoke skin contract needs a callable %s - the rate hooks "
                "MUST consume the same per-player budget as this owner's v1 "
                "apply, never a second one" % name)
    return Engine(adapter)
