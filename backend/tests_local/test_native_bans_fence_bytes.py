# -*- coding: utf-8 -*-
"""BYTE-LEVEL property gate: a native ban entry must stay VISIBLE to the game fence.

WHY THIS FILE EXISTS
  PlayerBans.json is written UTF-16. The game-side guard
  (mod/lua/LaIslaNublarDataMod/Scripts/main.full.lua, __LaIslaNublarBanSpawnGuardRegister)
  does NOT parse it as JSON. It does:

      local f = io.open(path, "rb")            -- :15683  RAW BYTES
      local s = f:read("*all") or ""
      return (s:gsub("%z", ""))                -- :15687  strip every NUL
      ...
      for block in native:gmatch("{[^{}]*}")   -- :15753  Lua block pattern

  So the fence's view of the file is "the UTF-16 bytes with the NULs removed".
  Any codepoint whose UTF-16LE byte pair contains 0x7B therefore SYNTHESISES a
  literal "{" in that view even though the Python string holds no brace at all -
  U+017B (7B 01), U+047B (7B 04), the whole U+7B00 CJK row (xx 7B), U+FF7B
  (7B FF), emoji U+1F37B ... and the "{" lands INSIDE the entry, after
  "steamId". The block match then starts at the synthesised brace instead of the
  entry's own, so the matched block carries NO "steamId" and the fence never
  sees the ban: the banned player reconnects freely while every gate above
  reports success.

  0x7D is the mirror image: it synthesises "}", closing the block EARLY so
  "endBanTime" falls outside it. main.full.lua:15744 reads an absent/unparseable
  endBanTime as `return true` - a TIMED ban silently becomes PERMANENT.

  The field carrying this is attacker-controlled and refreshes on every login:
  server.py:802/:813 store the player's own Steam persona name, and it is passed
  as player_name into native_bans.add_ban at server.py:8536, :8707, :8723, :8950
  and :11851 (the unattended enforcer loop). A player renames themselves and
  walks back in.

  There is no second net on this owner: the fence's other source, the flat
  banned_players.json (main.full.lua:15751), has NO writer anywhere in LIN's
  backend. PlayerBans.json is the only surface that blocks a reconnect.

WHAT THIS FILE GUARANTEES
  The tests below do not inspect the sanitiser. They assert the PROPERTY, on the
  bytes that actually land on disk, through LIN's own add_ban writer:

      given ANY player_name / banReason / bannerName,
        the fence must find a block keyed on our steamId (VISIBLE), and
        that block must still contain our endBanTime (INTACT - not promoted to
        permanent by an early close).

  The pre-fix writer is reproduced INLINE (LEGACY_SAFE_FIELD + _write_legacy)
  and asserted to FAIL that property. That red guard is what stops this file
  going vacuous: weaken the fence simulation to make the green tests pass and
  the red guard goes green and fails.
"""
import importlib
import json
import os
import re
import time

import pytest


# =============================================================================
# the fence, simulated faithfully (main.full.lua:15683-15687, 15731-15757)
# =============================================================================

_BLOCK_RE = re.compile(rb"\{[^{}]*\}")            # :15753 gmatch("{[^{}]*}")
_SID_RE = re.compile(rb'"steamId"\s*:\s*"([^"]*)"')      # :15754
_END_RE = re.compile(rb'"endBanTime"\s*:\s*"([^"]*)"')   # :15742
_REASON_RE = re.compile(rb'"banReason"\s*:\s*"([^"]*)"')  # :15765
_TS_RE = re.compile(rb"^(\d+)\.(\d+)\.(\d+)-(\d+)\.(\d+)\.(\d+)")  # :15732


def fence_read(path):
    """main.full.lua:15682-15688 readFile - raw bytes, NULs stripped, "" if absent."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return b""
    return raw.replace(b"\x00", b"")


def fence_blocks(path):
    return _BLOCK_RE.findall(fence_read(path))


def fence_block_for(path, sid):
    """The block the fence would match on this sid, or None (== ban invisible)."""
    want = sid.encode("ascii")
    for block in fence_blocks(path):
        found = _SID_RE.search(block)
        if found and found.group(1) == want:
            return block
    return None


def fence_expires(block):
    """main.full.lua:15731-15739 parseNativeTime. None == the fence cannot parse."""
    end = _END_RE.search(block)
    if not end:
        return None
    parts = _TS_RE.match(end.group(1))
    if not parts:
        return None
    year = int(parts.group(1))
    if year >= 9999:
        return 253402300799
    try:
        return time.mktime((year, int(parts.group(2)), int(parts.group(3)),
                            int(parts.group(4)), int(parts.group(5)),
                            int(parts.group(6)), 0, 0, -1))
    except (ValueError, OverflowError):
        return None


def fence_block_active(block):
    """main.full.lua:15741-15746. NOTE :15744 - an endBanTime the fence cannot
    find or parse reads as ACTIVE FOREVER, which is how a truncated block turns a
    timed ban into a permanent one."""
    expires = fence_expires(block)
    if expires is None:
        return True
    return expires > time.time()


def fence_sees(path, sid):
    """main.full.lua:15748-15758 isBanned, native leg only (LIN writes no
    banned_players.json - grep server.py: zero hits)."""
    block = fence_block_for(path, sid)
    return bool(block) and fence_block_active(block)


# =============================================================================
# the PRE-FIX writer, reproduced inline. The anti-vacuity guard.
# =============================================================================

def LEGACY_SAFE_FIELD(v):
    """native_bans.py:62 as it stood before this fix - ASCII braces only."""
    return str(v).replace("{", "(").replace("}", ")")


def _legacy_entry(sid, reason, end, player_name, banner_name, safe):
    return {
        "steamId": str(sid),
        "playerName": safe(player_name or "Unknown"),
        "banReason": safe(reason or "Rule violation"),
        "bannedTime": time.strftime("%Y.%m.%d-%H.%M.%S"),
        "endBanTime": end,
        "bannerName": safe(banner_name or "La Isla Nublar"),
        "bannerSteamId": "",
    }


def _write_like(path, doc, ensure_ascii):
    """native_bans.py:117-118 as it stood - open(...,'w',encoding='utf-16') +
    json.dump(ensure_ascii=<param>). Raises exactly where the real writer raises."""
    with open(path, "w", encoding="utf-16") as handle:
        json.dump(doc, handle, ensure_ascii=ensure_ascii, indent=2)


# =============================================================================
# corpus
# =============================================================================

SID = "76561199000000042"
NEIGHBOUR = "76561199000000777"

#  label, string, what it does to the fence's byte view
HAZARDS = [
    ("ascii_control_newline", "spawn killing\nsecond offence", "control"),
    ("U+017B_Z_dot",          "Player Żyrardow",          "brace_open"),
    ("U+047B_cyrillic",       "ѻ omega guy",              "brace_open"),
    ("U+7B11_CJK_row",        "笑 smile",                  "brace_open"),
    ("U+FF7B_halfwidth",      "ｻ katakana",               "brace_open"),
    ("U+7D00_kanji",          "紀 kanji",                  "brace_close"),
    ("U+017D_Z_caron",        "Ž caron",                  "brace_close"),
    ("emoji_U+1F37B",         "party \U0001f37b time",         "brace_open"),
    ("wholly_non_ascii",      "中文名字",      "clean_non_ascii"),
    # the ONLY two codepoints the old .replace() line actually caught, out of the
    # 17,324 in the hazard class - see test_the_old_replace_caught_exactly_two
    ("literal_braces",        "he said {gg} lol",              "legacy_handled"),
    ("lone_surrogate",        "bad \ud800 name",               "unencodable"),
]

# Real strings this owner actually writes. LIN's ban reasons are SPANISH:
# server.py:11851 writes "Sanción (auto-sync)" on the unattended enforcer.
ACCENTED = [
    "Sanción (auto-sync)",
    "Expulsión por comportamiento tóxico",
    "Baño de sangre - matanza en zona segura",
    "Reincidencia: 3ª infracción",
    "Violação das regras de construção",
    "Naruszenie zasad – zabijanie na spawnie",
    "Нарушение правил",
    "José María Álvarez",
    "Ñoño_Único",
    "Renée Çelik",
]


@pytest.fixture()
def nb(tmp_path):
    saved = tmp_path / "Saved"
    (saved / "PlayerData").mkdir(parents=True)
    bans = saved / "PlayerData" / "PlayerBans.json"
    os.environ["LIN_SAVED_DIR"] = str(saved)
    os.environ["LIN_PLAYER_BANS_JSON"] = str(bans)
    import game_ipc
    importlib.reload(game_ipc)
    import native_bans
    importlib.reload(native_bans)
    return native_bans, str(bans)


def _assert_visible_and_intact(path, sid, expect_end=None):
    """The property, on the bytes. Both halves, with the block dumped on failure."""
    block = fence_block_for(path, sid)
    if block is None:
        raise AssertionError(
            "BAN INVISIBLE - the fence found no block keyed on %s.\n"
            "fence view (NULs stripped):\n%r\nblocks it did match:\n%r"
            % (sid, fence_read(path)[:900], [b[:200] for b in fence_blocks(path)]))
    end = _END_RE.search(block)
    if not end:
        raise AssertionError(
            "BLOCK TRUNCATED - endBanTime fell outside the block, so "
            "main.full.lua:15744 reads this TIMED ban as PERMANENT.\nblock: %r" % block)
    if expect_end is not None:
        assert end.group(1) == expect_end.encode("ascii"), (
            "the fence reads a DIFFERENT endBanTime than we wrote: %r != %r"
            % (end.group(1), expect_end))
    assert fence_block_active(block), "the fence reads this fresh ban as expired"


# =============================================================================
# 1. RED GUARD - the pre-fix writer must FAIL the property. Inline, never vacuous.
# =============================================================================

@pytest.mark.parametrize("label,value,kind", HAZARDS)
def test_red_guard_legacy_writer_loses_the_ban(tmp_path, label, value, kind):
    """The exact pre-fix lane: native_bans.py:62 sanitiser + :118 ensure_ascii=False.
    Every brace-synthesising hazard must break it. If this test ever goes GREEN the
    fence simulation above has been weakened and every green test below is vacuous."""
    path = str(tmp_path / "PlayerBans.json")
    end = time.strftime("%Y.%m.%d-%H.%M.%S", time.localtime(time.time() + 3600))
    doc = {"bannedPlayerData": [
        _legacy_entry(SID, "Rule violation", end, value, "La Isla Nublar",
                      LEGACY_SAFE_FIELD)]}
    try:
        _write_like(path, doc, ensure_ascii=False)
    except UnicodeEncodeError:
        # lone surrogate: the legacy writer THROWS, add_ban swallows it and
        # returns False - the ban is never written at all. Still a lost ban.
        assert kind == "unencodable"
        assert fence_block_for(path, SID) is None
        return

    block = fence_block_for(path, SID)
    if kind == "brace_open":
        assert block is None, ("expected the pre-fix writer to LOSE the ban for %s, "
                               "but the fence still saw %r" % (label, block))
    elif kind == "brace_close":
        assert block is not None, "0x7D truncates, it does not hide"
        assert _END_RE.search(block) is None, (
            "expected endBanTime to fall OUTSIDE the block for %s" % label)
        assert fence_block_active(block) is True   # == reads PERMANENT
    else:
        # legacy_handled: the literal ASCII brace, which .replace() DID map.
        # control chars and clean non-ASCII do not synthesise a brace; they are
        # covered by the word-weld and byte-integrity tests instead.
        assert block is not None


def test_red_guard_counts_the_hazard_class_is_not_empty():
    """Cheap independent restatement of the mechanism, no file involved."""
    opens = [c for c in ("Ż", "ѻ", "笑", "ｻ", "\U0001f37b")
             if 0x7B in c.encode("utf-16-le")]
    closes = [c for c in ("紀", "Ž", "ｽ") if 0x7D in c.encode("utf-16-le")]
    assert len(opens) == 5 and len(closes) == 3
    assert "{" not in "Ż" and "}" not in "紀"   # no brace in the STRING


def test_the_old_replace_caught_exactly_two_of_the_hazard_class():
    """The size of the hole, stated exactly. 17,324 codepoints put an 0x7B or 0x7D
    byte into the fence's NUL-stripped view; the pre-fix .replace() line saw only the
    two that are literally "{" and "}", leaving 17,322 live. That is the number the
    end-to-end byte sweep measures (8,661 invisible + 8,661 truncated)."""
    hazard = [cp for cp in range(0x110000)
              if not 0xD800 <= cp <= 0xDFFF
              and ({0x7B, 0x7D} & set(chr(cp).encode("utf-16-le")))]
    assert len(hazard) == 17324
    caught = [cp for cp in hazard if LEGACY_SAFE_FIELD(chr(cp)) != chr(cp)]
    assert caught == [0x7B, 0x7D]
    assert len(hazard) - len(caught) == 17322

    import native_bans
    survivors = [cp for cp in hazard
                 if {0x7B, 0x7D} & set(
                     native_bans._safe_field(chr(cp)).encode("utf-16-le"))]
    assert survivors == [], "the shipped sanitiser let a hazard codepoint through"


# =============================================================================
# 2. GREEN - the shipped writer, through LIN's own add_ban, on real bytes
# =============================================================================

@pytest.mark.parametrize("label,value,kind", HAZARDS)
def test_hostile_player_name_stays_visible(nb, label, value, kind):
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="Cheating", hours=1, player_name=value,
                               banner_name="staff", banner_steamid="") is True
    _assert_visible_and_intact(path, SID)


@pytest.mark.parametrize("label,value,kind", HAZARDS)
def test_hostile_ban_reason_stays_visible(nb, label, value, kind):
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason=value, hours=1, player_name="Tester",
                               banner_name="staff", banner_steamid="") is True
    _assert_visible_and_intact(path, SID)


@pytest.mark.parametrize("label,value,kind", HAZARDS)
def test_hostile_banner_name_stays_visible(nb, label, value, kind):
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="Cheating", hours=1, player_name="Tester",
                               banner_name=value, banner_steamid="") is True
    _assert_visible_and_intact(path, SID)


def test_hostile_banner_steamid_stays_visible(nb):
    """bannerSteamId is the one entry field server.py fills from an unvalidated
    request string (server.py:8951 -> data.by_sid, InternalModInput.by_sid)."""
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="Cheating", hours=1, player_name="Tester",
                               banner_name="staff",
                               banner_steamid="7656{1199Ż000000001") is True
    _assert_visible_and_intact(path, SID)


def test_timed_ban_keeps_its_window(nb):
    """The 0x7D direction: the fence must read OUR endBanTime, not 'permanent'."""
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="紀 kanji reason", hours=1,
                               player_name="紀 kanji Ž") is True
    doc = json.load(open(path, encoding="utf-16"))
    written = doc["bannedPlayerData"][0]["endBanTime"]
    assert written != "9999.12.31-23.59.59"
    _assert_visible_and_intact(path, SID, expect_end=written)


def test_permanent_entry_stays_permanent_and_visible(nb):
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="perma ｻ", hours=0,
                               player_name="Ż perma") is True
    _assert_visible_and_intact(path, SID, expect_end="9999.12.31-23.59.59")
    block = fence_block_for(path, SID)
    assert fence_expires(block) == 253402300799


def test_wholly_non_ascii_name_still_keyed_on_steamid(nb):
    """A name with NO ASCII at all must not cost us the entry - the fence matches on
    steamId, which is digits, and that is what has to survive."""
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="русский",
                               hours=6, player_name="中文名字",
                               banner_name="日本語") is True
    block = fence_block_for(path, SID)
    assert block is not None
    assert _SID_RE.search(block).group(1) == SID.encode("ascii")
    _assert_visible_and_intact(path, SID)


def test_newline_does_not_weld_two_words(nb):
    """A control character becomes a SPACE, never nothing. Dropping the newline out
    of 'spawn killing\\nsecond offence' silently changes what a moderator wrote."""
    native_bans, path = nb
    native_bans.add_ban(SID, reason="spawn killing\nsecond offence", hours=1)
    doc = json.load(open(path, encoding="utf-16"))
    reason = doc["bannedPlayerData"][0]["banReason"]
    assert "killing second offence" in reason
    assert "killingsecond" not in reason
    assert "\n" not in reason
    _assert_visible_and_intact(path, SID)


def test_tab_and_cr_also_become_spaces(nb):
    native_bans, path = nb
    native_bans.add_ban(SID, reason="a\tb\r\nc\x00d", hours=1)
    doc = json.load(open(path, encoding="utf-16"))
    # tab, CR, LF and NUL each become ONE space - four control chars, four spaces,
    # nothing collapsed and nothing welded.
    assert doc["bannedPlayerData"][0]["banReason"] == "a b  c d"


def test_lone_surrogate_no_longer_kills_the_write(nb):
    """json.dump to a UTF-16 file RAISES on a lone surrogate; add_ban swallows it and
    the ban is silently never written. A lone surrogate is reachable: json.loads
    accepts \\ud800 in a request body, and persona_name is a request-shaped string."""
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason="bad \udfff reason", hours=1,
                               player_name="bad \ud800 name") is True
    _assert_visible_and_intact(path, SID)


# =============================================================================
# 3. ACCENTS - the reason LIN does NOT take the strip-all-non-ASCII form
# =============================================================================

@pytest.mark.parametrize("text", ACCENTED)
def test_spanish_and_friends_survive_byte_identical(nb, text):
    """LIN's ban reasons are Spanish. The canonical/TWB sanitiser strips ALL
    non-ASCII, which turns 'Sanción (auto-sync)' into 'Sancin'. The surgical form
    removes ONLY brace-synthesising codepoints, so accented text is untouched."""
    native_bans, path = nb
    assert native_bans.add_ban(SID, reason=text, hours=1, player_name=text,
                               banner_name=text) is True
    doc = json.load(open(path, encoding="utf-16"))
    row = doc["bannedPlayerData"][0]
    assert row["banReason"] == text, "ban reason was mangled"
    assert row["playerName"] == text, "player name was mangled"
    assert row["bannerName"] == text, "banner name was mangled"
    _assert_visible_and_intact(path, SID)


def test_the_strip_all_form_would_have_mangled_the_owners_own_reason():
    """Restates WHY this owner gets the surgical form, inline, so the choice cannot
    be silently reverted to the canonical one by a later port."""
    strip_all = "".join(c for c in "Sanción (auto-sync)" if " " <= c <= "~")
    assert strip_all == "Sancin (auto-sync)"       # what TWB's form would write
    import native_bans
    assert native_bans._safe_field("Sanción (auto-sync)") == "Sanción (auto-sync)"


# =============================================================================
# 4. the surgical pass SUBSUMES the old replace()
# =============================================================================

def test_literal_braces_are_removed_not_mapped(nb):
    """U+007B encodes 7B 00, so the brace-synthesis filter already drops a literal
    '{'. The old .replace('{','(') line is fully subsumed - nothing it caught
    escapes this."""
    import native_bans
    assert native_bans._safe_field("a{b}c") == "abc"
    assert "{" not in native_bans._safe_field("{" * 50)
    assert "}" not in native_bans._safe_field("}" * 50)
    native_bans_mod, path = nb
    native_bans_mod.add_ban(SID, reason="he said {gg} lol", hours=1)
    _assert_visible_and_intact(path, SID)


def test_no_surviving_codepoint_can_synthesise_a_brace():
    """The whole point, stated as a closed property over the sanitiser's output."""
    import native_bans
    sample = "".join(chr(c) for c in range(0x20, 0x3000) if not (0xD800 <= c <= 0xDFFF))
    out = native_bans._safe_field(sample)
    assert 0x7B not in out.encode("utf-16-le")
    assert 0x7D not in out.encode("utf-16-le")


# =============================================================================
# 5. ROUND-TRIP - a GAME-authored neighbour row must not stay invisible
# =============================================================================

def test_foreign_game_authored_row_is_repaired_by_our_write(nb):
    """ensure_ascii=False meant our sanitiser only ever covered the fields WE filled.
    A row the game wrote for a player whose persona carries U+017B was invisible the
    moment the game wrote it, and every read-modify-write we did preserved it
    verbatim. With ensure_ascii=True the escape is emitted instead, so the enforcer
    loop (server.py:11851) now REPAIRS those rows as a side effect."""
    native_bans, path = nb
    with open(path, "w", encoding="utf-16") as handle:
        json.dump({"bannedPlayerData": [{
            "steamId": NEIGHBOUR,
            "playerName": "game wrote Ż this",
            "banReason": "Ban por admin 笑",
            "bannedTime": "2026.08.01-10.00.00",
            "endBanTime": "9999.12.31-23.59.59",
            "bannerName": "ｻ admin",
            "bannerSteamId": "",
        }]}, handle, ensure_ascii=False, indent=2)

    # precondition: that foreign row is invisible to the fence RIGHT NOW
    assert fence_block_for(path, NEIGHBOUR) is None, \
        "precondition failed - the foreign row was supposed to be invisible"

    assert native_bans.add_ban(SID, reason="Cheating", hours=1,
                               player_name="Tester") is True

    _assert_visible_and_intact(path, SID)
    _assert_visible_and_intact(path, NEIGHBOUR, expect_end="9999.12.31-23.59.59")

    # and the foreign row's DATA is unchanged - repaired in the bytes, not rewritten
    doc = json.load(open(path, encoding="utf-16"))
    row = [r for r in doc["bannedPlayerData"] if r["steamId"] == NEIGHBOUR][0]
    assert row["playerName"] == "game wrote Ż this"
    assert row["banReason"] == "Ban por admin 笑"
    assert row["bannerName"] == "ｻ admin"


def test_file_stays_valid_utf16_json_and_round_trips_losslessly(nb):
    """The three properties ensure_ascii=True must not cost us."""
    native_bans, path = nb
    names = ["Sanción", "中文", "José", "рус"]
    for i, name in enumerate(names):
        native_bans.add_ban("765611990000001%02d" % i, reason=name, hours=1,
                            player_name=name, banner_name=name)
    raw = open(path, "rb").read()
    assert raw[0:2] == b"\xff\xfe", "not UTF-16 LE any more"          # 1. UTF-16
    doc = json.loads(raw.decode("utf-16"))                            # 2. valid JSON
    got = [r["playerName"] for r in doc["bannedPlayerData"]]
    assert got == names                                               # 3. lossless
    assert all(r["banReason"] == r["playerName"] for r in doc["bannedPlayerData"])


def test_every_row_in_the_file_survives_the_fence(nb):
    """A mixed file - ours, the game's, hostile, clean - and NOT ONE row may go
    missing from the fence's view."""
    native_bans, path = nb
    with open(path, "w", encoding="utf-16") as handle:
        json.dump({"bannedPlayerData": [
            {"steamId": "76561199000000801", "playerName": "Ż one",
             "banReason": "a", "bannedTime": "2026.08.01-10.00.00",
             "endBanTime": "9999.12.31-23.59.59", "bannerName": "x",
             "bannerSteamId": ""},
            {"steamId": "76561199000000802", "playerName": "plain two",
             "banReason": "b", "bannedTime": "2026.08.01-10.00.00",
             "endBanTime": "9999.12.31-23.59.59", "bannerName": "y",
             "bannerSteamId": ""},
            {"steamId": "76561199000000803", "playerName": "紀 three",
             "banReason": "c \U0001f47b", "bannedTime": "2026.08.01-10.00.00",
             "endBanTime": "9999.12.31-23.59.59", "bannerName": "z",
             "bannerSteamId": ""},
        ]}, handle, ensure_ascii=False, indent=2)
    native_bans.add_ban(SID, reason="Cheating Ż", hours=2, player_name="ｻ me")
    for sid in ("76561199000000801", "76561199000000802", "76561199000000803", SID):
        _assert_visible_and_intact(path, sid)
    assert native_bans.active_banned_ids() >= {
        "76561199000000801", "76561199000000802", "76561199000000803", SID}


# =============================================================================
# 6. UNBAN - the same failure in the opposite direction
# =============================================================================

def test_unban_still_matches_a_hostile_name_row(nb):
    """remove_ban keys on steamId through the PARSED json, so a hostile name can
    never orphan a row. Proven, not assumed - an unban that silently matches nothing
    is this defect's mirror image."""
    native_bans, path = nb
    native_bans.add_ban(SID, reason="Sanción Ż", hours=5,
                        player_name="\U0001f37b 紀 hostile", banner_name="ｻ")
    assert SID in native_bans.active_banned_ids()
    assert native_bans.remove_ban(SID) is True
    assert SID not in native_bans.active_banned_ids()
    assert fence_block_for(path, SID) is None
    assert native_bans.remove_ban(SID) is False


def test_unban_leaves_the_neighbour_visible(nb):
    native_bans, path = nb
    native_bans.add_ban(SID, hours=1, player_name="Ż a")
    native_bans.add_ban(NEIGHBOUR, hours=1, player_name="紀 b")
    assert native_bans.remove_ban(SID) is True
    _assert_visible_and_intact(path, NEIGHBOUR)


def test_steamid_is_never_rewritten(nb):
    """The identity key add_ban / remove_ban / active_banned_ids all agree on. The
    sanitiser must be IDENTITY here or an unban stops matching its own ban."""
    native_bans, path = nb
    native_bans.add_ban(SID, hours=1, player_name="Ż 紀 \U0001f37b")
    doc = json.load(open(path, encoding="utf-16"))
    assert doc["bannedPlayerData"][0]["steamId"] == SID
    assert native_bans.list_bans()[0]["steam_id"] == SID


# =============================================================================
# 7. each leg of the fix closes the hole on its own (defence in depth, proven)
# =============================================================================

@pytest.mark.parametrize("label,value,kind",
                         [h for h in HAZARDS if h[2] in ("brace_open", "brace_close")])
def test_leg_one_sanitiser_alone_closes_it(tmp_path, label, value, kind):
    """Fixed sanitiser + the OLD ensure_ascii=False."""
    import native_bans
    path = str(tmp_path / "PlayerBans.json")
    end = time.strftime("%Y.%m.%d-%H.%M.%S", time.localtime(time.time() + 3600))
    doc = {"bannedPlayerData": [
        _legacy_entry(SID, "Rule violation", end, value, "staff",
                      native_bans._safe_field)]}
    _write_like(path, doc, ensure_ascii=False)
    _assert_visible_and_intact(path, SID, expect_end=end)


@pytest.mark.parametrize("label,value,kind",
                         [h for h in HAZARDS
                          if h[2] in ("brace_open", "brace_close") and "{" not in h[1]])
def test_leg_two_ensure_ascii_alone_closes_it(tmp_path, label, value, kind):
    """OLD sanitiser + ensure_ascii=True. (A literal ASCII brace is excluded: JSON
    does not escape it, so only the sanitiser can catch that one - which is exactly
    why both legs ship.)"""
    path = str(tmp_path / "PlayerBans.json")
    end = time.strftime("%Y.%m.%d-%H.%M.%S", time.localtime(time.time() + 3600))
    doc = {"bannedPlayerData": [
        _legacy_entry(SID, "Rule violation", end, value, "staff", LEGACY_SAFE_FIELD)]}
    _write_like(path, doc, ensure_ascii=True)
    _assert_visible_and_intact(path, SID, expect_end=end)
