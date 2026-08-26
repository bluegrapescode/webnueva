"""Pure-module tests for native_bans (game PlayerBans.json writer) + strike ladder.
Runs without motor/mongo — sets the Saved dir + ban-file path to a temp dir before
importing the module (paths are resolved at import time)."""
import os
import io
import json
import importlib
import tempfile
from datetime import datetime, timedelta

import pytest


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


def _read_utf16(path):
    with open(path, "r", encoding="utf-16") as f:
        return json.load(f)


def test_add_creates_utf16_file(nb):
    native_bans, path = nb
    assert native_bans.is_available() is True
    ok = native_bans.add_ban("76561199000000001", reason="Cheating", hours=1,
                             player_name="Tester", banner_name="crysis", banner_steamid="765611990AAA")
    assert ok is True
    doc = _read_utf16(path)  # must be UTF-16 or this raises
    rows = doc["bannedPlayerData"]
    assert len(rows) == 1
    e = rows[0]
    assert e["steamId"] == "76561199000000001"
    assert e["banReason"] == "Cheating"
    assert e["playerName"] == "Tester"
    assert e["bannerName"] == "crysis"
    # endBanTime is ~1h out, game format YYYY.MM.DD-HH.MM.SS
    end = datetime.strptime(e["endBanTime"], "%Y.%m.%d-%H.%M.%S")
    delta = (end - datetime.now()).total_seconds()
    assert 3000 < delta < 4200


def test_permanent_sentinel(nb):
    native_bans, path = nb
    native_bans.add_ban("76561199000000002", reason="perma", hours=0)
    rows = _read_utf16(path)["bannedPlayerData"]
    assert rows[0]["endBanTime"] == "9999.12.31-23.59.59"


def test_add_replaces_same_sid(nb):
    native_bans, path = nb
    native_bans.add_ban("76561199000000003", hours=1)
    native_bans.add_ban("76561199000000003", hours=24)  # escalate -> replace, not dup
    rows = _read_utf16(path)["bannedPlayerData"]
    assert len(rows) == 1
    end = datetime.strptime(rows[0]["endBanTime"], "%Y.%m.%d-%H.%M.%S")
    assert (end - datetime.now()).total_seconds() > 23 * 3600


def test_remove(nb):
    native_bans, path = nb
    native_bans.add_ban("76561199000000004", hours=1)
    native_bans.add_ban("76561199000000005", hours=1)
    assert native_bans.remove_ban("76561199000000004") is True
    assert native_bans.remove_ban("76561199000000004") is False  # already gone
    rows = _read_utf16(path)["bannedPlayerData"]
    assert [r["steamId"] for r in rows] == ["76561199000000005"]


def test_active_ids_and_prune(nb):
    native_bans, path = nb
    # one active (future), one expired (write a manual past endBanTime)
    native_bans.add_ban("76561199000000006", hours=1)  # active
    doc = _read_utf16(path)
    past = (datetime.now() - timedelta(hours=2)).strftime("%Y.%m.%d-%H.%M.%S")
    doc["bannedPlayerData"].append({
        "steamId": "76561199000000007", "playerName": "old", "banReason": "x",
        "bannedTime": past, "endBanTime": past, "bannerName": "b", "bannerSteamId": "",
    })
    with open(path, "w", encoding="utf-16") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    active = native_bans.active_banned_ids()
    assert active == {"76561199000000006"}
    assert native_bans.prune_expired() == 1
    rows = _read_utf16(path)["bannedPlayerData"]
    assert [r["steamId"] for r in rows] == ["76561199000000006"]


def test_permanent_is_active(nb):
    native_bans, _ = nb
    native_bans.add_ban("76561199000000008", hours=0)  # permanent
    assert "76561199000000008" in native_bans.active_banned_ids()


def test_add_aborts_on_unreadable_file_no_clobber(nb):
    # A present-but-unparseable file must NOT be overwritten (data-loss guard).
    native_bans, path = nb
    with open(path, "wb") as f:
        f.write(b"\xff\xfe not valid json at all \x00\x01")
    before = open(path, "rb").read()
    assert native_bans.add_ban("76561199000000020", hours=1) is False
    assert native_bans.remove_ban("76561199000000020") is False
    assert native_bans.prune_expired() == 0
    after = open(path, "rb").read()
    assert before == after  # untouched


def test_empty_file_is_writable_not_blocked(nb):
    # A present-but-EMPTY (0-byte) PlayerBans.json must be treated as "no bans yet"
    # (writable), NOT "unreadable" (which would permanently refuse all native bans).
    native_bans, path = nb
    open(path, "wb").close()  # 0-byte file
    assert native_bans.add_ban("76561199000000030", hours=1) is True
    assert "76561199000000030" in native_bans.active_banned_ids()


def test_bom_only_file_is_writable(nb):
    native_bans, path = nb
    with open(path, "wb") as f:
        f.write(b"\xff\xfe")  # UTF-16 BOM, no content
    assert native_bans.add_ban("76561199000000031", hours=1) is True
    assert "76561199000000031" in native_bans.active_banned_ids()


def test_foreign_endbantime_skipped_not_kicked(nb):
    # An entry the game wrote in a format we can't parse must NOT be treated as an
    # active ban (so the reconciler never re-kicks a player we don't understand).
    native_bans, path = nb
    with open(path, "w", encoding="utf-16") as f:
        json.dump({"bannedPlayerData": [
            {"steamId": "76561199000000021", "endBanTime": "2026-07-13T10:00:00Z"}]}, f)
    assert "76561199000000021" not in native_bans.active_banned_ids()
    # prune must KEEP the foreign entry (game owns it)
    assert native_bans.prune_expired() == 0
    rows = _read_utf16(path)["bannedPlayerData"]
    assert any(r["steamId"] == "76561199000000021" for r in rows)


def test_always_writes_utf16(nb):
    # Even when the current file is UTF-8, a write must restore canonical UTF-16.
    native_bans, path = nb
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"bannedPlayerData": []}, f)
    native_bans.add_ban("76561199000000022", hours=1)
    b = open(path, "rb").read()
    assert b[0:2] == b"\xff\xfe"  # UTF-16 LE BOM


def test_reads_existing_utf8_file(nb):
    # The game normally writes UTF-16, but our reader must tolerate a UTF-8 file too.
    native_bans, path = nb
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"bannedPlayerData": [
            {"steamId": "76561199000000009", "endBanTime": "9999.12.31-23.59.59"}]}, f)
    assert "76561199000000009" in native_bans.active_banned_ids()
    # a subsequent add must not corrupt / must keep both
    native_bans.add_ban("76561199000000010", hours=1)
    ids = native_bans.active_banned_ids()
    assert {"76561199000000009", "76561199000000010"} <= ids


# --- strike ladder -> enforcement mapping (mirrors server.STRIKE_LADDER) ---
STRIKE_LADDER = [
    {"threshold": 2, "label": "1 hour ban", "seconds": 3600},
    {"threshold": 3, "label": "24 hour ban", "seconds": 86400},
    {"threshold": 4, "label": "7 day ban", "seconds": 604800},
    {"threshold": 5, "label": "Permanent ban", "seconds": None},
]


def _rung(count):
    applicable = None
    for item in STRIKE_LADDER:
        if count >= item["threshold"]:
            applicable = item
    return applicable


@pytest.mark.parametrize("count,expect", [
    (1, None),               # warning + kick only
    (2, "1 hour ban"),
    (3, "24 hour ban"),
    (4, "7 day ban"),
    (5, "Permanent ban"),
    (7, "Permanent ban"),    # caps at permanent
])
def test_ladder_rung(count, expect):
    r = _rung(count)
    assert (r["label"] if r else None) == expect


def test_ladder_hours():
    assert _rung(2)["seconds"] // 3600 == 1
    assert _rung(3)["seconds"] // 3600 == 24
    assert _rung(4)["seconds"] // 3600 == 168
    assert _rung(5)["seconds"] is None  # permanent
