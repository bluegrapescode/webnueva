"""Default quests for PRIMAL — The Isle: Evrima.

Quests are driven by IN-GAME actions. Progress is fed via the game hook
(POST /api/quests/track {action, amount}) — RCON will call this once the
server telemetry is wired up. `play_time` also advances from the passive
activity tick while a player is in-game (proxy until RCON).

Objective types:
  - kill_dino        : number of dinosaurs killed
  - play_time        : minutes played
  - visit_location   : number of named locations visited
                        optional objective.poi (exact POI name, see
                        backend/quest_pois.py) restricts credit to first
                        visiting THAT ONE location per period; omitted -> any
                        of the named POIs counts (server.py's visit tracker).

Categories: daily | weekly | achievement  (NO permanent).
Rarities:  Common | Uncommon | Rare | Epic | Legendary
`requires` references another quest `key` (prerequisite) — locks the quest
until the prerequisite is claimed for its current period.
"""

# key is a stable id (used for seeding + prerequisites).
DEFAULT_QUESTS = [
    # ---------- DAILY ----------
    {"key": "daily_kill_beginner", "category": "daily", "rarity": "Common",
     "title": "Kill Beginner", "description": "Kill 3 dinosaurs",
     "objective": {"type": "kill_dino", "target": 3, "label": "Kill 3x any dinosaur"},
     "coins": 15000, "vip": 0, "xp": 15, "egg": None, "requires": None},
    {"key": "daily_play_30", "category": "daily", "rarity": "Common",
     "title": "Play for 30 minutes", "description": "Play for 30 minutes",
     "objective": {"type": "play_time", "target": 30, "label": "Play for 30 minutes"},
     "coins": 50000, "vip": 0, "xp": 69, "egg": None, "requires": None},
    {"key": "daily_killer", "category": "daily", "rarity": "Uncommon",
     "title": "Killer", "description": "Kill 6 dinosaurs",
     "objective": {"type": "kill_dino", "target": 6, "label": "Kill 6x any dinosaur"},
     "coins": 32500, "vip": 0, "xp": 25, "egg": None, "requires": None},
    {"key": "daily_play_1h", "category": "daily", "rarity": "Uncommon",
     "title": "Play for 1 hour", "description": "Play for 1 hour",
     "objective": {"type": "play_time", "target": 60, "label": "Play for 60 minutes"},
     "coins": 85000, "vip": 0, "xp": 100, "egg": None, "requires": None},
    {"key": "daily_play_6h", "category": "daily", "rarity": "Rare",
     "title": "Play for 6 hours", "description": "Play for 6 hours",
     "objective": {"type": "play_time", "target": 360, "label": "Play for 360 minutes"},
     "coins": 250000, "vip": 0, "xp": 450, "egg": None, "requires": "daily_play_1h"},

    # ---------- WEEKLY ----------
    {"key": "weekly_apex", "category": "weekly", "rarity": "Epic",
     "title": "Apex Predator", "description": "Kill 50 dinosaurs this week",
     "objective": {"type": "kill_dino", "target": 50, "label": "Kill 50x any dinosaur"},
     "coins": 500000, "vip": 0, "xp": 1500, "egg": "epic", "requires": None},
    {"key": "weekly_grind", "category": "weekly", "rarity": "Rare",
     "title": "Weekly Grind", "description": "Play for 20 hours this week",
     "objective": {"type": "play_time", "target": 1200, "label": "Play for 1200 minutes"},
     "coins": 750000, "vip": 0, "xp": 1000, "egg": None, "requires": None},
    {"key": "weekly_cartographer", "category": "weekly", "rarity": "Rare",
     "title": "Cartographer", "description": "Visit 8 different locations",
     "objective": {"type": "visit_location", "target": 8, "label": "Visit 8x locations"},
     "coins": 400000, "vip": 0, "xp": 800, "egg": None, "requires": None},

    # ---------- ACHIEVEMENTS (never reset) ----------
    {"key": "ach_first_blood", "category": "achievement", "rarity": "Common",
     "title": "First Blood", "description": "Get your first kill",
     "objective": {"type": "kill_dino", "target": 1, "label": "Kill 1x any dinosaur"},
     "coins": 10000, "vip": 0, "xp": 10, "egg": None, "requires": None},
    {"key": "ach_veteran", "category": "achievement", "rarity": "Legendary",
     "title": "Isle Veteran", "description": "Play for 100 hours total",
     "objective": {"type": "play_time", "target": 6000, "label": "Play for 6000 minutes"},
     "coins": 2000000, "vip": 0, "xp": 5000, "egg": "legendary", "requires": None},
]

# Quests removed from DEFAULT_QUESTS by owner request: the seeder deactivates
# these ids at boot so an existing DB row can never resurface them.
RETIRED_QUEST_KEYS = ["daily_visit_dome"]  # removed 2026-07-16 (owner ask)

OBJECTIVE_TYPES = ["kill_dino", "play_time", "visit_location"]
QUEST_CATEGORIES = ["daily", "weekly", "achievement"]
QUEST_RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]

# ---------- Multiplier Events (admin-created, time-boxed earning boosts) ------
# Multiplier events live in their own db.multiplier_events collection: while
# one is active, every player whose CURRENT dino is the event species earns
# their passive PrimeMeat multiplied by the event value (server.py hooks the
# verified passive-payout lane; nothing is paid one-time).

# Canonical Evrima species (clean class names, BP_/_C stripped) an event may
# target. Must stay in step with the 21-species fleet list
# (game_telemetry.EVRIMA_SPECIES / pop_control._DEFAULT_SPECIES) — quest_data
# stays dependency-free so the pure event logic is testable everywhere.
EVENT_SPECIES = [
    "Allosaurus", "Beipiaosaurus", "Carnotaurus", "Ceratosaurus",
    "Deinosuchus", "Diabloceratops", "Dilophosaurus", "Dryosaurus",
    "Austroraptor",
    "Gallimimus", "Herrerasaurus", "Hypsilophodon", "Kentrosaurus",
    "Maiasaura", "Omniraptor", "Pachycephalosaurus", "Pteranodon",
    "Stegosaurus", "Tenontosaurus", "Triceratops", "Troodon", "Tyrannosaurus",
]

# Admin-selectable run lengths (hours) and the hard bounds for custom values.
EVENT_DURATION_PRESETS_H = [6, 12, 24, 48, 72, 168, 336]
EVENT_MAX_HOURS = 720            # 30 days — duration cap
MULT_EVENT_DEFAULT_HOURS = 24    # duration preselected in the admin form
MULT_EVENT_DEFAULT = 30          # multiplier preloaded in the admin form
MULT_EVENT_MIN = 2               # x1 would be a no-op event
MULT_EVENT_MAX = 1000            # typo guard (x30000 would mint the economy)
