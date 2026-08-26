r"""SkinKeeper shared reference helper -- COPY VERBATIM into every owner port.

Single source of truth for the recipe contract and the frozen schema. Every
owner's web writer AND bot writer inline these exact functions. Do NOT
re-implement per owner: the digest, the payload bytes and the sid guard must be
byte-for-byte identical fleet-wide or the stored column stops being comparable
and dedupe silently breaks across processes.

Runtime: gated on C:\Python312\python.exe. Pure ASCII source on purpose -- fleet
bot .py files are known double-encoded UTF-8, so any non-ASCII literal risks a
mangled digest input on some boxes.

LaIslaNublar note: this file is carried BYTE-IDENTICALLY in both
  ghrepo/bot/skinkeeper_shared.py            (bot: restore + death + boot-ensure)
  ghrepo/web/backend/skinkeeper_shared.py    (web: capture + startup-ensure)
so whichever process boots first creates the table and both agree on the bytes.
Diff the two copies before deploy; they MUST be identical.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

# --- 1. RECIPE = COMMAND MINUS TRANSIENT KEYS (SUBTRACTION, never an allowlist:
#        FossilFalls' parser enforces exact key-set equality, so an allowlist that
#        drops a key an owner requires silently bricks that owner). ---
CANONICAL_TRANSIENT_KEYS = (
    "actor_name", "steamid", "request_id", "requested_at", "cmd_id",
)
RESTORE_REQUEST_MARKER = "rejoin-"  # every restore stamps this into request_id/cmd_id


def canonical_recipe(command):
    """Stored recipe = command minus transient keys. Presence/absence of
    color_space is preserved (the regular-vs-glitch contract)."""
    return {k: v for k, v in command.items() if k not in CANONICAL_TRANSIENT_KEYS}


# --- 2. CANONICAL SERIALIZATION (the EXACT bytes stored in payload) ---
def canonical_payload_json(recipe):
    """sort_keys => web and bot emit identical bytes and a reader can recompute the
    digest (a CHANGE vs the donor's unsorted dump). separators strip whitespace
    drift; ensure_ascii makes .encode() byte-deterministic; default=str degrades a
    stray type instead of raising in the never-fatal capture path."""
    return json.dumps(recipe, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def compute_recipe_digest(steam_id, payload_json):
    """'sha256:' + sha256(sid + US + payload)[:32]. hashlib NOT builtin hash()
    (hash() is PYTHONHASHSEED-salted, changes every restart). \x1f sid-binds it so
    two players applying the same preset never collide."""
    material = (str(steam_id) + "\x1f" + payload_json).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()[:32]


# --- 3. SID GUARD (closes hole #2 -- no CHECK in the DDL, enforce in code) ---
_SID_RE = re.compile(r"^[0-9]{1,20}$")  # non-empty, ASCII-numeric, u64-bounded


def is_valid_sid(sid):
    return bool(_SID_RE.match(str(sid or "").strip()))


def clean_sid(sid):
    s = str(sid or "").strip()
    return s if _SID_RE.match(s) else ""


def valid_sids(steam_ids):
    """De-duped list of valid sids for IN-lists (death lane can't take junk)."""
    out, seen = [], set()
    for s in steam_ids or ():
        c = clean_sid(s)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# --- 4. DEDUPE KEY (id when present, else the durable digest) ---
def is_restore_echo(command):
    for k in ("request_id", "cmd_id"):
        if str(command.get(k) or "").startswith(RESTORE_REQUEST_MARKER):
            return True
    return False


def dedupe_key(command, steam_id, payload_json):
    rid = str(command.get("request_id") or "").strip()
    if rid:
        return "rid:" + rid
    cid = str(command.get("cmd_id") or "").strip()
    if cid:
        return "cid:" + cid
    return compute_recipe_digest(steam_id, payload_json)


# --- 5. FROZEN SCHEMA + IDEMPOTENT DDL APPLY ---
CANONICAL_DDL = (
    "CREATE TABLE IF NOT EXISTS skin_last_applied (\n"
    "        steam_id TEXT PRIMARY KEY,\n"
    "        dino_class TEXT NOT NULL DEFAULT '',\n"
    "        actor_name TEXT NOT NULL DEFAULT '',\n"
    "        kind TEXT NOT NULL DEFAULT '',\n"
    "        payload TEXT NOT NULL,\n"
    "        active INTEGER NOT NULL DEFAULT 1,\n"
    "        updated_utc TEXT,\n"
    "        recipe_digest TEXT NOT NULL DEFAULT ''\n"
    "    )"
)
CANONICAL_COLUMNS = (
    "steam_id", "dino_class", "actor_name", "kind",
    "payload", "active", "updated_utc", "recipe_digest",
)
_REQUIRED_BEFORE_DIGEST = CANONICAL_COLUMNS[:-1]


def ensure_skin_last_applied(conn):
    """Idempotently guarantee the canonical table in the SHARED bot DB. Handles
    greenfield (CREATE makes all 8) and the donor 7-col shape (ALTER-adds
    recipe_digest). REFUSES a table missing any pre-digest column -- that is the
    legacy SweetScales web-private shape, which needs its own ORDERED storm-guard
    migration and must never be half-migrated here. Does NOT commit."""
    conn.execute(CANONICAL_DDL)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skin_last_applied)")}
    missing = [c for c in _REQUIRED_BEFORE_DIGEST if c not in cols]
    if missing:
        raise RuntimeError(
            "skin_last_applied is not the canonical shape (missing %r); this is the "
            "legacy SweetScales web-private table -- use its dedicated ordered "
            "reconciliation, not ensure_skin_last_applied()." % missing
        )
    if "recipe_digest" not in cols:
        conn.execute("ALTER TABLE skin_last_applied "
                     "ADD COLUMN recipe_digest TEXT NOT NULL DEFAULT ''")


# --- 6. WRITE / READ / DEACTIVATE (named-column, sid-guarded) ---
def record_skin_recipe(conn, steam_id, *, dino_class, actor_name, kind,
                       payload_json, recipe_digest, updated_utc):
    """Upsert one captured apply as the player's current recipe (active=1).
    Keyword-only descriptive fields (all str -> a positional mix-up would store
    actor_name as dino_class and silently fail the class gate). Idempotency
    predicate: WHERE digest changed OR active<>1 -- so a died-then-reapplied
    identical glitch REVIVES, while a bare re-read of a live block is a NO-OP that
    does not move updated_utc (freshness gate safe). Never fatal."""
    sid = clean_sid(steam_id)
    if not sid:
        return False
    try:
        cur = conn.execute(
            "INSERT INTO skin_last_applied "
            "(steam_id, dino_class, actor_name, kind, payload, active, "
            " updated_utc, recipe_digest) VALUES (?, ?, ?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(steam_id) DO UPDATE SET "
            "  dino_class=excluded.dino_class, actor_name=excluded.actor_name, "
            "  kind=excluded.kind, payload=excluded.payload, active=1, "
            "  updated_utc=excluded.updated_utc, recipe_digest=excluded.recipe_digest "
            "WHERE skin_last_applied.recipe_digest <> excluded.recipe_digest "
            "   OR skin_last_applied.active <> 1",
            (sid, str(dino_class or ""), str(actor_name or ""), str(kind or ""),
             str(payload_json), str(updated_utc), str(recipe_digest or "")),
        )
        return cur.rowcount > 0
    except sqlite3.Error:
        return False


def get_active_skin_recipes(conn, steam_ids):
    """Batch-read ACTIVE recipe rows -> {sid: row}. Named columns. Tolerant of a
    missing table (returns {}, never raises -> restore degrades to no-op)."""
    sids = valid_sids(steam_ids)
    if not sids:
        return {}
    try:
        prev = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT steam_id, dino_class, actor_name, kind, payload, active, "
                "updated_utc, recipe_digest FROM skin_last_applied "
                "WHERE active = 1 AND steam_id IN (%s)"
                % ",".join("?" for _ in sids), sids).fetchall()
            return {str(r["steam_id"]): dict(r) for r in rows}
        finally:
            conn.row_factory = prev
    except sqlite3.Error:
        return {}


def deactivate_skin_recipes(conn, steam_ids, updated_utc):
    """Death lane (per-life), keyed on the VICTIM sid. No CREATE here -- runs on
    every kill; the web migration owns the schema."""
    sids = valid_sids(steam_ids)
    if not sids:
        return 0
    try:
        cur = conn.execute(
            "UPDATE skin_last_applied SET active = 0, updated_utc = ? "
            "WHERE active = 1 AND steam_id IN (%s)"
            % ",".join("?" for _ in sids), (str(updated_utc), *sids))
        return cur.rowcount
    except sqlite3.Error:
        return 0


# --- 6b. UNOBSERVED-DEATH RETIREMENT (closes the "recipe never retired" hole) ---
# Per-life semantics retire a recipe on an OBSERVED death. A death the bot never
# saw -- it was down, or the line fell in the window the tail cursor skipped when
# it seeded to EOF -- otherwise leaves the recipe ACTIVE FOREVER, so a long-dead
# skin is repainted onto a life it does not belong to. Two mechanisms, both using
# only signals LaIslaNublar actually has in TheIsle.log and only columns that
# exist in the FROZEN schema (no DDL change):
#   1. retire_skin_recipes() -- fed by a bounded backfill scan of the log tail at
#      bot start, plus the "Save file not found - Starting as fresh spawn" line
#      (unambiguous proof the previous life ended), ORDERED against the recipe's
#      own updated_utc so a replayed/backfilled OLD event can never kill a NEWER
#      apply.
#   2. recipe_age_seconds() -- a validity bound for the residual gap (a death both
#      unobserved AND older than the backfill window). Caller expires + retires.
def parse_iso_utc(value):
    """Parse a stored ISO-8601 stamp into an AWARE UTC datetime, or None.

    TIMEZONE-CRITICAL: every writer stamps datetime.now(timezone.utc).isoformat(),
    so a NAIVE stamp (a legacy/donor row, or a 'Z' suffix) is UTC and is read as
    UTC. NEVER interpret it as box-local and NEVER use time.mktime -- on a box
    whose local time is not UTC that silently shifts every comparison by the
    offset, which makes an age gate either permanently inert or permanently
    closed with no error anywhere."""
    s = str(value or "").strip()
    if not s:
        return None
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recipe_age_seconds(row, now=None):
    """Age of a recipe row in seconds (UTC-anchored), or None when its
    updated_utc is missing/unparseable -- callers treat None as EXPIRED
    (fail closed: an unbounded recipe is exactly the never-retired hole)."""
    written = parse_iso_utc((row or {}).get("updated_utc"))
    if written is None:
        return None
    return ((now or datetime.now(timezone.utc)) - written).total_seconds()


def retire_skin_recipes(conn, events, updated_utc):
    """Retire recipes for observed-or-backfilled life-ending events.

    events = [(sid, occurred_dt_or_None)] where occurred_dt is the AWARE UTC time
    of the death / fresh-spawn line. A recipe is retired only when the event is
    NOT OLDER than the recipe itself, so replaying the log tail (bot-start
    backfill, or a post-rotation cold read) can never retire a skin the player
    applied AFTER that death. occurred_dt None => retire unconditionally; the
    caller only passes None for a live incremental batch, which is fresh by
    construction. Returns the list of sids actually retired. Never raises."""
    pairs = []
    for sid, occurred in events or ():
        c = clean_sid(sid)
        if c:
            pairs.append((c, occurred))
    if not pairs:
        return []
    rows = get_active_skin_recipes(conn, [p[0] for p in pairs])
    if not rows:
        return []
    doomed = []
    seen = set()
    for sid, occurred in pairs:
        if sid in seen:
            continue
        row = rows.get(sid)
        if not row:
            continue
        if occurred is not None:
            written = parse_iso_utc(row.get("updated_utc"))
            if written is not None and occurred < written:
                # The event predates the recipe -> it ended an EARLIER life and
                # the current recipe was applied after it. Leave it active.
                continue
        seen.add(sid)
        doomed.append(sid)
    if not doomed:
        return []
    deactivate_skin_recipes(conn, doomed, updated_utc)
    return doomed


# --- 7. RESTORE ACTOR RESOLUTION (settled policy: only ever send an actor_name
#        the LIVE FEED bound to THIS SID -- kills BOTH mod mis-paint branches) ---
READY_POLLS = 30            # ~45s at READY_INTERVAL_S
READY_INTERVAL_S = 1.5


def resolve_restore_actor(sid, stale_actor, read_player_row, sleep,
                          ready_polls=READY_POLLS, ready_interval_s=READY_INTERVAL_S):
    """Return the actor_name to send, or '' to drop.

    ONLY EVER RETURNS AN ACTOR THE LIVE FEED BOUND TO THIS SID. read_player_row is
    keyed by steamid, so anything it yields is this player's own pawn. Preference:
    (1) a live actor that is init-done AND differs from the known-stale one (the
    rebuilt pawn, defeating the 60-100s stale-row trap); else (2) whatever the feed
    last bound to this sid (may still be the stale name -- harmless, it is this
    player's own); else (3) '' -> caller fails closed.

    NEVER falls back to the STORED stale actor when the feed never showed this sid.
    That is a remembered string from a previous life, and UE re-issues actor
    UniqueIDs from the same counter after a server restart, so by then it can name a
    DIFFERENT player's pawn. The mod's Priority 1 (SkinSystem.cpp:517-520
    FindByActorName) resolves a non-empty actor_name with NO steamid cross-check, so
    sending an unobserved name repaints whoever owns it now. Post-restart reconnect
    -- when players.json may not yet list the rejoiner -- is exactly this port's
    primary trigger, so the unsafe path coincided with the main use case. Dropping
    costs one relog; a mis-paint is player-visible and hits a stranger."""
    fresh = ""
    observed = ""
    for i in range(ready_polls):
        row = read_player_row(sid) or {}
        a = str(row.get("actor_name") or "").strip()
        if a:
            observed = a
            if a != stale_actor:
                fresh = a
        try:
            init_done = float(row.get("max_hunger") or 0) > 0
        except (TypeError, ValueError):
            init_done = False
        if fresh and init_done:
            break
        if i < ready_polls - 1:
            sleep(ready_interval_s)
    return fresh or observed


def build_restore_command(recipe_payload, sid, resolved_actor, new_request_id):
    """Re-stamp ONLY the transient keys onto a VERBATIM replay of the stored
    payload (preserving the glitch raw contract: color_space present/absent,
    variation 0.0, raw RGBA). Owners whose write lane splits glitch vs regular MUST
    dispatch on the stored recipe's `kind`, never rebuild via to_command. Returns
    None on a junk sid or empty resolved actor (fail closed)."""
    if not is_valid_sid(sid) or not resolved_actor:
        return None
    cmd = dict(recipe_payload)
    cmd["steamid"] = clean_sid(sid)
    cmd["actor_name"] = resolved_actor
    cmd["request_id"] = new_request_id  # caller uses RESTORE_REQUEST_MARKER + rand
    return cmd
