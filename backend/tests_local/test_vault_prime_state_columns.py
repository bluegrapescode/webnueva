"""Gate for the vault half: the three Prime mission-state columns.

Runs against a REAL sqlite database built with the PRE-WAVE schema, so the
migration itself is under test rather than assumed. The mod's own decision is
mirrored in the docstrings: receiving NO bits, it force-ticks all ten missions
for a dino at >=75% growth or any elder, and strips Prime entirely below that.
Sending 0 is therefore NOT a safe default — it is a different, wrong claim.

Run:  py -3.12 -m pytest tests_local/test_vault_prime_state_columns.py -q
"""
import importlib
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The exact pre-wave CREATE, column for column, from live PRAGMA table_info.
PRE_WAVE_SCHEMA = """
CREATE TABLE parked_dinos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id TEXT, discord_id TEXT, dino_class TEXT, growth REAL,
  health REAL, max_health REAL, stamina REAL, max_stamina REAL,
  hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL,
  oxygen REAL, max_oxygen REAL, x REAL, y REAL, z REAL,
  is_prime INTEGER, is_elder INTEGER, mutations TEXT, parent_mutations TEXT,
  elder_mutations TEXT, elder_stacks INTEGER, skin_code TEXT, skin_data TEXT,
  diet_a REAL, diet_b REAL, diet_c REAL,
  parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at INTEGER,
  custom_name TEXT
);
"""

PRE_WAVE_COLS = 33


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    db = tmp_path / "laislanublar.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(PRE_WAVE_SCHEMA)
    conn.commit()
    conn.close()
    monkeypatch.setenv("BOT_DB_PATH", str(db))
    import game_ipc
    importlib.reload(game_ipc)
    import vault as v
    importlib.reload(v)
    assert v.game_ipc.BOT_DB_PATH == str(db)
    return v


def columns(v):
    conn = sqlite3.connect(v.game_ipc.BOT_DB_PATH)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(parked_dinos)")]
    finally:
        conn.close()


def row(v, rid):
    conn = sqlite3.connect(v.game_ipc.BOT_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM parked_dinos WHERE id=?", (rid,)).fetchone())
    finally:
        conn.close()


BASE_PAYLOAD = {
    "dino": "BP_Allosaurus_C", "growth": 0.877,
    "health": 0.0, "max_health": 0.0, "stamina": 0.0, "max_stamina": 0.0,
    "hunger": 0.0, "max_hunger": 0.0, "thirst": 0.0, "max_thirst": 0.0,
    "oxygen": 0.0, "max_oxygen": 0.0, "x": 0.0, "y": 0.0, "z": 0.0,
    "is_prime": True, "is_elder": False,
    "mutations": "Hemomania|Gastronomic Regeneration|Osteosclerosis|Epidermal Fibrosis",
    "parent_mutations": "Accelerated Prey Drive|Hemomania|None|None",
    "elder_mutations": "None|None|None|None|None|None|None|None",
    "elder_stacks": 0, "skin_code": "", "skin_data": "",
    "diet_a": 0.0, "diet_b": 0.0, "diet_c": 0.0,
}


# ---------------------------------------------------------------------------
# the fixture must be what it claims to be
# ---------------------------------------------------------------------------
def test_the_fixture_really_starts_on_the_pre_wave_schema(vault):
    cols = columns(vault)
    assert len(cols) == PRE_WAVE_COLS
    for col in ("prime_conditions", "prime_route_mig", "prime_route_pat"):
        assert col not in cols


# ---------------------------------------------------------------------------
# migration
# ---------------------------------------------------------------------------
def test_migration_adds_exactly_three_nullable_columns(vault):
    assert vault.ensure_prime_state_columns() is True
    cols = columns(vault)
    assert len(cols) == PRE_WAVE_COLS + 3
    assert cols[-3:] == ["prime_conditions", "prime_route_mig", "prime_route_pat"]


def test_migration_is_idempotent(vault):
    assert vault.ensure_prime_state_columns() is True
    vault._PRIME_STATE_READY = False  # force it to re-inspect a migrated table
    assert vault.ensure_prime_state_columns() is True
    assert len(columns(vault)) == PRE_WAVE_COLS + 3


def test_a_failed_migration_leaves_the_vault_on_the_old_shape(vault, monkeypatch):
    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(vault, "_connect_rw", boom)
    assert vault.ensure_prime_state_columns() is False
    # and the select shape must not pretend the columns exist
    assert "prime_conditions" not in vault._parked_select()


def test_the_select_shape_only_widens_once_the_columns_exist(vault):
    assert "prime_conditions" not in vault._parked_select()
    vault.ensure_prime_state_columns()
    for col in vault._PRIME_STATE_COLS:
        assert col in vault._parked_select()


def test_both_parked_selects_carry_the_same_columns(vault):
    """★The two SELECTs diverging is a silent-no-op trap, not a style point."""
    import inspect
    vault.ensure_prime_state_columns()
    src = inspect.getsource(vault.mark_redeem_pending)
    assert "_parked_select()" in src
    assert "{_PARKED_SELECT}" not in src


# ---------------------------------------------------------------------------
# NULL is not 0
# ---------------------------------------------------------------------------
def test_a_payload_that_knows_nothing_leaves_the_columns_null(vault):
    vault.ensure_prime_state_columns()
    rid = vault.save_parked("76561199023620899", "", dict(BASE_PAYLOAD), 0)
    stored = row(vault, rid)
    for col in vault._PRIME_STATE_COLS:
        assert stored[col] is None, col


def test_a_recorded_zero_is_stored_as_zero_not_null(vault):
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd.update(prime_conditions=0, prime_route_mig=0, prime_route_pat=0)
    stored = row(vault, vault.save_parked("76561199023620899", "", pd, 0))
    for col in vault._PRIME_STATE_COLS:
        assert stored[col] == 0, col


def test_real_values_round_trip(vault):
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd.update(prime_conditions=63, prime_route_mig=1, prime_route_pat=2)
    stored = row(vault, vault.save_parked("76561199023620899", "", pd, 0))
    assert stored["prime_conditions"] == 63
    assert stored["prime_route_mig"] == 1
    assert stored["prime_route_pat"] == 2
    # everything the row already carried is untouched
    assert stored["mutations"] == BASE_PAYLOAD["mutations"]
    assert stored["is_prime"] == 1


def test_values_are_clamped_to_the_mods_limits(vault):
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd.update(prime_conditions=99999, prime_route_mig=99, prime_route_pat=99)
    stored = row(vault, vault.save_parked("76561199023620899", "", pd, 0))
    assert stored["prime_conditions"] == 1023
    assert stored["prime_route_mig"] == 2
    assert stored["prime_route_pat"] == 4


@pytest.mark.parametrize("junk", [None, "", "  ", "abc", True, False, float("nan"), [], {}])
def test_unusable_values_never_reach_the_row(vault, junk):
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd["prime_conditions"] = junk
    stored = row(vault, vault.save_parked("76561199023620899", "", pd, 0))
    assert stored["prime_conditions"] is None


def test_an_engine_infinity_saturates_to_the_ceiling(vault):
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd["prime_conditions"] = float("inf")
    stored = row(vault, vault.save_parked("76561199023620899", "", pd, 0))
    assert stored["prime_conditions"] == 1023


def test_before_the_migration_the_extra_keys_are_harmless(vault):
    """The wave must not depend on its own migration having succeeded."""
    pd = dict(BASE_PAYLOAD)
    pd.update(prime_conditions=63, prime_route_mig=1, prime_route_pat=2)
    rid = vault.save_parked("76561199023620899", "", pd, 0)
    assert rid is not None
    assert len(columns(vault)) == PRE_WAVE_COLS


# ---------------------------------------------------------------------------
# the wire
# ---------------------------------------------------------------------------
def test_the_restore_command_omits_what_was_never_recorded(vault):
    """Absent means absent — the mod keeps behaving exactly as it does today."""
    state = vault._prime_state_from_payload({"is_prime": 1, "mutations": "x"})
    assert state == {}


def test_the_restore_command_carries_what_was_recorded(vault):
    state = vault._prime_state_from_payload(
        {"prime_conditions": 63, "prime_route_mig": 1, "prime_route_pat": 2})
    assert state == {"prime_conditions": 63, "prime_route_mig": 1, "prime_route_pat": 2}


def test_a_recorded_zero_does_go_on_the_wire(vault):
    """0 is a real claim: 'this dino completed nothing'. It must be sent."""
    state = vault._prime_state_from_payload({"prime_conditions": 0})
    assert state == {"prime_conditions": 0}


def test_partial_records_send_only_the_parts_they_have(vault):
    state = vault._prime_state_from_payload({"prime_conditions": 500, "prime_route_mig": None})
    assert state == {"prime_conditions": 500}


def test_the_read_back_row_feeds_the_wire(vault):
    """End to end: park -> read -> the exact dict the restore command merges."""
    vault.ensure_prime_state_columns()
    pd = dict(BASE_PAYLOAD)
    pd.update(prime_conditions=241, prime_route_mig=2, prime_route_pat=3)
    rid = vault.save_parked("76561199023620899", "", pd, 0)
    parked = vault.get_parked_by_id(rid)
    assert parked is not None
    assert vault._prime_state_from_payload(parked) == {
        "prime_conditions": 241, "prime_route_mig": 2, "prime_route_pat": 3}


def test_a_legacy_row_read_back_sends_nothing(vault):
    vault.ensure_prime_state_columns()
    rid = vault.save_parked("76561199023620899", "", dict(BASE_PAYLOAD), 0)
    parked = vault.get_parked_by_id(rid)
    assert vault._prime_state_from_payload(parked) == {}
