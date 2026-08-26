"""Real-time game telemetry for The Isle: Evrima.

Reads the live server log (`TheIsle.log`) over SFTP and parses the LogTheIsle*
events into an in-memory state: who is connected, as what species, growth,
gender, mutation, plus a rolling activity + in-game chat feed.

RCON only reports total player count; the server log is the ONLY accessible
source for per-player species / growth, so this module is the source of truth
for the "real" population and live-dino features. (Positions are NOT logged, so
map coordinates remain unavailable.)
"""
import os
import re
import threading
import time
import logging
from collections import deque
from datetime import datetime, timezone

import paramiko

logging.getLogger("paramiko").setLevel(logging.WARNING)

SFTP_HOST = os.environ.get("SFTP_HOST")
SFTP_PORT = int(os.environ.get("SFTP_PORT", "0") or 0)
SFTP_USER = os.environ.get("SFTP_USER")
SFTP_PASSWORD = os.environ.get("SFTP_PASSWORD")
LOCAL_ISLE_LOG_PATH = os.environ.get("ISLE_LOG_PATH")
ISLE_LOG_PATH = LOCAL_ISLE_LOG_PATH or "server/TheIsle/Saved/Logs/TheIsle.log"

# Evrima class/species name -> our internal dino slug
EVRIMA_SPECIES = {
    "Tyrannosaurus": "trex", "Carnotaurus": "carno", "Allosaurus": "allo",
    "Dilophosaurus": "dilo", "Omniraptor": "raptor", "Deinosuchus": "deino",
    "Triceratops": "trike", "Stegosaurus": "stego", "Kentrosaurus": "kentro", "Pteranodon": "ptera",
    "Austroraptor": "austro",
    "Ceratosaurus": "cerato", "Troodon": "troodon", "Herrerasaurus": "herrera",
    "Tenontosaurus": "tenonto", "Hypsilophodon": "hypsi",
    "Pachycephalosaurus": "pachy", "Dryosaurus": "dryo", "Maiasaura": "maia",
    "Diabloceratops": "diablo", "Gallimimus": "galli", "Beipiaosaurus": "beipiao",
}


def _clean_species(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("BP_"):
        s = s[3:]
    if s.endswith("_C"):
        s = s[:-2]
    return s


def _slug(species: str) -> str:
    return EVRIMA_SPECIES.get(_clean_species(species), "")


def is_configured() -> bool:
    return _has_local_log() or bool(SFTP_HOST and SFTP_PORT and SFTP_USER and SFTP_PASSWORD)


def _has_local_log() -> bool:
    return bool(LOCAL_ISLE_LOG_PATH and os.path.isfile(ISLE_LOG_PATH))


# regexes over the log lines
_STEAM = r"(\d{17})"
_TS = r"\[[^\]]*\]"
RX_JOIN = re.compile(r"LogTheIsleJoinData:\s*" + _TS + r"\s*(.+?)\s*\[" + _STEAM + r"\].*?Class:\s*([A-Za-z0-9_]+),\s*Gender:\s*(\w+),\s*Growth:\s*([\d.]+)")
RX_LEFT = re.compile(r"LogTheIsleJoinData:.*?\[" + _STEAM + r"\]\s*Left The Server")
RX_CHAR = re.compile(r"LogTheIsleCharacter:.*?\[" + _STEAM + r"\],\s*Dino:\s*([A-Za-z]+),\s*Gender:\s*(\w+),\s*Growth:\s*([\d.]+)(?:,\s*Selected Mutation:\s*\[([^\]]*)\])?")
RX_KILL = re.compile(r"LogTheIsleKillData:\s*" + _TS + r"\s*(.+?)\s*\[" + _STEAM + r"\]\s*Dino:\s*([A-Za-z]+),\s*(\w+),\s*([\d.]+)\s*-\s*(.+)")
RX_CHAT = re.compile(r"LogTheIsleChatData:.*?ALL \[\]:\s*(.*?),\s*Sent by:\s*(.+?),\s*\[" + _STEAM + r"\]")

# RX_KILL group(1)/group(2) are the KILLER's name/steam64; the cause tail (group(6))
# starts with PVP_CAUSE_PREFIX for player-vs-player kills and embeds the VICTIM's
# name/steamid at the end of that same tail (e.g. "Killed the following player:
# VictimName [76561198000000001]"). Natural deaths ("Died from Natural cause") never
# match this prefix and are never credited as a kill.
PVP_CAUSE_PREFIX = "Killed the following player"
RX_KILL_VICTIM_SID = re.compile(r"\[" + _STEAM + r"\]")


class GameTelemetry:
    def __init__(self):
        self.players = {}           # steam64 -> {name, species, slug, gender, growth, mutation, alive, ts}
        self.activity = deque(maxlen=60)
        self._chat_out = deque(maxlen=40)   # drained by server to mirror into web chat
        self.kills_out = deque(maxlen=200)  # drained by server to credit the kill_dino quest objective
        self.deaths_out = deque(maxlen=200)  # drained by server to reset survive-type event quest progress
        self._offset = 0
        self._lock = threading.Lock()
        self._last_poll = 0
        self._online = False

    # ---- log reading ----
    def _read_new(self):
        if _has_local_log():
            return self._read_new_local()
        return self._read_new_sftp()

    def _read_new_local(self):
        size = os.path.getsize(ISLE_LOG_PATH)
        if self._offset == 0:
            self._offset = max(0, size - 400_000)
        elif size < self._offset:
            self._offset = 0
        if size <= self._offset:
            return ""
        with open(ISLE_LOG_PATH, "rb") as f:
            f.seek(self._offset)
            data = f.read(size - self._offset)
        self._offset = size
        return data.decode("utf-8", "ignore")

    def _read_new_sftp(self):
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASSWORD)
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            size = sftp.stat(ISLE_LOG_PATH).st_size
            if self._offset == 0:
                # first run: only ingest the tail so we build current state fast
                self._offset = max(0, size - 400_000)
            elif size < self._offset:
                self._offset = 0    # log rotated
            if size <= self._offset:
                return ""
            with sftp.open(ISLE_LOG_PATH, "r") as f:
                f.seek(self._offset)
                data = f.read(size - self._offset)
            self._offset = size
            return data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
        finally:
            transport.close()

    def poll(self):
        try:
            chunk = self._read_new()
            self._online = True
        except Exception as e:
            self._online = False
            raise e
        if not chunk:
            return
        with self._lock:
            for line in chunk.splitlines():
                self._process(line)

    def _process(self, line):
        # Chat is the ONLY player-controlled free text in the log. A crafted chat
        # message can embed a forged "LogTheIsleKillData: ... Killed the following
        # player: ..." payload, and the parsers below use .search (unanchored), so
        # a chat line must be fully handled and returned BEFORE any kill/join/char
        # parse can see it -- otherwise a player farms kill_dino quest credit by
        # typing. Server-emitted join/char/kill lines are never chat lines.
        if "LogTheIsleChatData:" in line:
            m = RX_CHAT.search(line)
            if m:
                msg, name, sid = m.group(1).strip(), m.group(2).strip(), m.group(3)
                if msg:
                    self._chat_out.append({"steam_id": sid, "name": name, "text": msg, "ts": self._now()})
            return
        m = RX_CHAR.search(line)
        if m:
            sid, dino, gender, growth, mut = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            self._upsert(sid, species=dino, gender=gender, growth=float(growth), mutation=(mut or None), alive=True)
            return
        m = RX_JOIN.search(line)
        if m:
            name, sid, cls, gender, growth = m.group(1).strip(), m.group(2), m.group(3), m.group(4), m.group(5)
            self._upsert(sid, name=name, species=_clean_species(cls), gender=gender, growth=float(growth), alive=True)
            self._push_activity("spawn", sid, name, _clean_species(cls), float(growth))
            return
        m = RX_KILL.search(line)
        if m:
            name, sid, dino, gender, growth, cause = m.group(1).strip(), m.group(2), m.group(3), m.group(4), float(m.group(5)), m.group(6).strip()
            self._push_activity("death", sid, name, dino, growth, extra=cause)
            # kill_dino quest credit -- PVP only (see PVP_CAUSE_PREFIX/RX_KILL comment
            # above); sid here is the KILLER. Guard against crediting a self-kill when
            # the victim's steamid is parseable out of the cause tail. Natural deaths
            # ("Died from Natural cause") never match the prefix and are never credited.
            if cause.startswith(PVP_CAUSE_PREFIX):
                victim_m = RX_KILL_VICTIM_SID.search(cause)
                victim_sid = victim_m.group(1) if victim_m else None
                # The line's primary sid/species/growth describe the KILLER; the
                # victim's live state row (fed by their join/char lines) is the
                # only species/growth source for them. A missing victim row just
                # leaves those fields None — the event matcher fails closed.
                victim = self.players.get(victim_sid) if victim_sid else None
                if victim_sid:
                    # A parseable victim died — record the death even when the
                    # line is self-kill-shaped (killer == victim): survive-type
                    # event progress must reset on EVERY death. Only the kill
                    # CREDIT below excludes self-kills.
                    if victim:
                        victim["alive"] = False
                    self.deaths_out.append({
                        "sid": victim_sid,
                        "species": (victim or {}).get("species"),
                        "ts": self._now()})
                if victim_sid is None or victim_sid != sid:
                    self.kills_out.append({
                        "killer_sid": sid,
                        "killer_species": _clean_species(dino),
                        "killer_growth": growth,
                        "victim_sid": victim_sid,
                        "victim_species": (victim or {}).get("species"),
                        "victim_growth": (victim or {}).get("growth"),
                        "ts": self._now()})
            else:
                # Natural death: the line's primary sid IS the dying player.
                # (PVP lines used to mark the KILLER dead here — the dying side
                # is now the one flagged so population stays accurate.)
                p = self.players.get(sid)
                if p:
                    p["alive"] = False
                self.deaths_out.append({"sid": sid, "species": _clean_species(dino), "ts": self._now()})
            return
        m = RX_LEFT.search(line)
        if m:
            self.players.pop(m.group(1), None)
            return
        # Chat lines are handled at the top of _process (before the kill parser);
        # nothing to do here.

    def _upsert(self, sid, **kw):
        p = self.players.get(sid) or {"steam_id": sid, "name": None, "species": None, "slug": None,
                                      "gender": None, "growth": 0.0, "mutation": None, "alive": True}
        for k, v in kw.items():
            if v is not None:
                p[k] = v
        if kw.get("species"):
            p["slug"] = _slug(kw["species"])
        p["ts"] = self._now()
        self.players[sid] = p

    def _push_activity(self, kind, sid, name, species, growth, extra=None):
        self.activity.appendleft({
            "kind": kind, "steam_id": sid, "name": name,
            "species": _clean_species(species), "slug": _slug(species),
            "growth": round(growth * 100, 1), "extra": extra, "ts": self._now(),
        })

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    # ---- accessors ----
    def get_player(self, sid):
        with self._lock:
            p = self.players.get(str(sid))
            return dict(p) if p else None

    def population(self, connected_ids):
        """Per-species counts for players confirmed connected via RCON."""
        with self._lock:
            counts, unknown = {}, 0
            details = []
            for sid in connected_ids:
                p = self.players.get(sid)
                if p and p.get("slug") and p.get("alive"):
                    counts[p["slug"]] = counts.get(p["slug"], 0) + 1
                    details.append({"steam_id": sid, "name": p.get("name"), "slug": p["slug"],
                                    "species": p.get("species"), "growth": round(p.get("growth", 0) * 100, 1),
                                    "gender": p.get("gender"), "mutation": p.get("mutation")})
                else:
                    unknown += 1
            return counts, unknown, details

    def recent_activity(self, limit=30):
        with self._lock:
            return list(self.activity)[:limit]

    def drain_chat(self):
        with self._lock:
            out = list(self._chat_out)
            self._chat_out.clear()
            return out

    def drain_kills(self):
        """Pop every PVP kill observed since the last drain -- rich rows:
        [{killer_sid, killer_species, killer_growth, victim_sid, victim_species,
          victim_growth, ts}, ...] (victim fields None when their state row is
        unknown -- constraint matching fails closed on those)."""
        with self._lock:
            out = list(self.kills_out)
            self.kills_out.clear()
            return out

    def drain_deaths(self):
        """Pop every observed player death (natural AND PVP victims) since the
        last drain -- [{sid, species, ts}, ...]. Used to reset survive-type
        event quest progress."""
        with self._lock:
            out = list(self.deaths_out)
            self.deaths_out.clear()
            return out

    @property
    def online(self):
        return self._online


telemetry = GameTelemetry()
