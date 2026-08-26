"""Chat cosmetics catalog (Dino Den-style Decorations).

Six categories — colors, borders, effects, fonts, chat backgrounds and emotes.
Every decoration has a rarity; rarity drives both drop odds inside the Dino Egg
gacha and a PrimeMeat "value" (used for duplicate refunds). Apex is ~0.01%.
"""

# rarity -> drop weight (Apex ≈ 1/10191 ≈ 0.01%) + PrimeMeat value + display color
DECO_RARITY = {
    "Common":    {"weight": 6000, "value": 2000,   "color": "#9ca3af", "order": 0},
    "Uncommon":  {"weight": 2800, "value": 4000,   "color": "#22c55e", "order": 1},
    "Rare":      {"weight": 1000, "value": 8000,   "color": "#38bdf8", "order": 2},
    "Epic":      {"weight": 320,  "value": 16000,  "color": "#a855f7", "order": 3},
    "Legendary": {"weight": 70,   "value": 40000,  "color": "#f59e0b", "order": 4},
    "Apex":      {"weight": 2,    "value": 120000, "color": "#ef4444", "order": 5},
}

CATEGORIES = [
    {"key": "color",   "label": "Colores"},
    {"key": "border",  "label": "Bordes"},
    {"key": "effect",  "label": "Efectos"},
    {"key": "font",    "label": "Fuentes"},
    {"key": "chat_bg", "label": "Chat BG"},
    {"key": "emote",   "label": "Emotes"},
]

# ---- Name colors (applied to the player's name in chat) ----
COLORS = [
    {"id": "color_arctic",  "name": "Arctic White", "rarity": "Common",    "value": "#f8fafc"},
    {"id": "color_ocean",   "name": "Ocean Blue",   "rarity": "Common",    "value": "#38bdf8"},
    {"id": "color_crimson", "name": "Crimson",      "rarity": "Common",    "value": "#ef4444"},
    {"id": "color_toxic",   "name": "Toxic Green",  "rarity": "Uncommon",  "value": "#84cc16"},
    {"id": "color_royal",   "name": "Royal Purple", "rarity": "Uncommon",  "value": "#a855f7"},
    {"id": "color_pink",    "name": "Hot Pink",     "rarity": "Rare",      "value": "#ec4899"},
    {"id": "color_solar",   "name": "Solar Gold",   "rarity": "Rare",      "value": "#f59e0b"},
    {"id": "color_aurora",  "name": "Aurora",       "rarity": "Epic",      "gradient": "linear-gradient(90deg,#22d3ee,#a855f7)"},
    {"id": "color_prism",   "name": "Prismatic",    "rarity": "Legendary", "gradient": "linear-gradient(90deg,#ff3b3b,#f59e0b,#22c55e,#38bdf8,#a855f7)"},
    {"id": "color_void",    "name": "Void Singularity", "rarity": "Apex",  "gradient": "linear-gradient(90deg,#7c3aed,#ec4899,#22d3ee,#7c3aed)", "animated": True},
]

# ---- Avatar borders (ring around the chat avatar) ----
BORDERS = [
    {"id": "border_steel",  "name": "Steel Ring",    "rarity": "Common",    "value": "#64748b"},
    {"id": "border_sky",    "name": "Sky Ring",      "rarity": "Common",    "value": "#38bdf8"},
    {"id": "border_leaf",   "name": "Leaf Ring",     "rarity": "Common",    "value": "#22c55e"},
    {"id": "border_rose",   "name": "Rose Ring",     "rarity": "Uncommon",  "value": "#f43f5e"},
    {"id": "border_violet", "name": "Violet Ring",   "rarity": "Uncommon",  "value": "#a855f7"},
    {"id": "border_gold",   "name": "Gold Ring",     "rarity": "Rare",      "value": "#f5d020", "glow": True},
    {"id": "border_neoncy", "name": "Cyan Neon",     "rarity": "Rare",      "value": "#22d3ee", "glow": True},
    {"id": "border_auroraB","name": "Aurora Frame",  "rarity": "Epic",      "gradient": "linear-gradient(135deg,#22d3ee,#a855f7)"},
    {"id": "border_flameB", "name": "Flame Frame",   "rarity": "Epic",      "gradient": "linear-gradient(135deg,#f59e0b,#ef4444)"},
    {"id": "border_rainbowB","name": "Rainbow Frame","rarity": "Legendary", "gradient": "conic-gradient(#ff3b3b,#f59e0b,#fde047,#22c55e,#38bdf8,#a855f7,#ff3b3b)", "animated": True},
    {"id": "border_voidB",  "name": "Void Prism",    "rarity": "Apex",      "gradient": "conic-gradient(#7c3aed,#ec4899,#22d3ee,#7c3aed)", "animated": True},
]

# ---- Name effects (glow / pulse / neon / shimmer / gradient / fire / rainbow) ----
EFFECTS = [
    {"id": "fx_glow_white", "name": "Soft Glow",     "rarity": "Common",    "kind": "glow",   "color": "#f8fafc"},
    {"id": "fx_glow_blue",  "name": "Blue Glow",     "rarity": "Common",    "kind": "glow",   "color": "#38bdf8"},
    {"id": "fx_glow_green", "name": "Green Glow",    "rarity": "Common",    "kind": "glow",   "color": "#22c55e"},
    {"id": "fx_pulse_red",  "name": "Crimson Pulse", "rarity": "Uncommon",  "kind": "pulse",  "color": "#ef4444"},
    {"id": "fx_pulse_amber","name": "Amber Pulse",   "rarity": "Uncommon",  "kind": "pulse",  "color": "#f59e0b"},
    {"id": "fx_glow_purple","name": "Purple Glow",   "rarity": "Uncommon",  "kind": "glow",   "color": "#a855f7"},
    {"id": "fx_neon_cyan",  "name": "Cyan Neon",     "rarity": "Rare",      "kind": "neon",   "color": "#22d3ee"},
    {"id": "fx_neon_pink",  "name": "Neon Pink",     "rarity": "Rare",      "kind": "neon",   "color": "#ec4899"},
    {"id": "fx_neon_emer",  "name": "Emerald Neon",  "rarity": "Rare",      "kind": "neon",   "color": "#10b981"},
    {"id": "fx_shimmer_gold","name": "Gold Shimmer", "rarity": "Rare",      "kind": "shimmer","color": "#f5d020"},
    {"id": "fx_grad_sunset","name": "Sunset",        "rarity": "Epic",      "kind": "gradient","colors": ["#f59e0b", "#ef4444", "#ec4899"]},
    {"id": "fx_grad_aurora","name": "Aurora Wave",   "rarity": "Epic",      "kind": "gradient","colors": ["#22d3ee", "#a855f7", "#22c55e"]},
    {"id": "fx_shimmer_tox","name": "Toxic Shimmer", "rarity": "Epic",      "kind": "shimmer","color": "#84cc16"},
    {"id": "fx_fire",       "name": "Inferno",       "rarity": "Epic",      "kind": "fire",   "color": "#ef4444"},
    {"id": "fx_rainbow",    "name": "Rainbow",       "rarity": "Legendary", "kind": "rainbow"},
    {"id": "fx_solarflare", "name": "Solar Flare",   "rarity": "Legendary", "kind": "fire",   "color": "#f59e0b"},
    {"id": "fx_frostfire",  "name": "Frostfire",     "rarity": "Legendary", "kind": "gradient","colors": ["#e0f2fe", "#38bdf8", "#a855f7"]},
    {"id": "fx_voidprism",  "name": "Void Prism",    "rarity": "Apex",      "kind": "rainbow", "color": "#7c3aed"},
    {"id": "fx_genesis",    "name": "Genesis",       "rarity": "Apex",      "kind": "neon",   "color": "#fde047"},
    {"id": "fx_singularity","name": "Singularity",   "rarity": "Apex",      "kind": "gradient","colors": ["#7c3aed", "#ec4899", "#22d3ee", "#7c3aed"]},
]

# ---- Fonts ----
FONTS = [
    {"id": "font_mono",   "name": "Terminal Mono", "rarity": "Common",   "value": "'Courier New', ui-monospace, monospace"},
    {"id": "font_serif",  "name": "Elegant Serif", "rarity": "Uncommon", "value": "Georgia, 'Times New Roman', serif"},
    {"id": "font_impact", "name": "Bold Impact",   "rarity": "Rare",     "value": "Impact, 'Arial Black', sans-serif"},
    {"id": "font_display","name": "Cabinet Display","rarity": "Epic",    "value": "'Cabinet Grotesk', 'Manrope', sans-serif"},
]

# ---- Chat backgrounds (message row background) ----
CHAT_BG = [
    {"id": "bg_slate",  "name": "Slate",       "rarity": "Common",    "value": "rgba(148,163,184,0.10)"},
    {"id": "bg_ocean",  "name": "Ocean",       "rarity": "Common",    "value": "rgba(56,189,248,0.12)"},
    {"id": "bg_forest", "name": "Forest",      "rarity": "Common",    "value": "rgba(34,197,94,0.12)"},
    {"id": "bg_ember",  "name": "Ember",       "rarity": "Uncommon",  "value": "rgba(239,68,68,0.13)"},
    {"id": "bg_amethyst","name": "Amethyst",   "rarity": "Uncommon",  "value": "rgba(168,85,247,0.14)"},
    {"id": "bg_gold",   "name": "Gold Leaf",   "rarity": "Rare",      "value": "rgba(245,158,11,0.15)"},
    {"id": "bg_sunset", "name": "Sunset",      "rarity": "Rare",      "value": "linear-gradient(90deg,rgba(245,158,11,0.16),rgba(236,72,153,0.16))"},
    {"id": "bg_aurora", "name": "Aurora",      "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(34,211,238,0.16),rgba(168,85,247,0.16))"},
    {"id": "bg_nebula", "name": "Nebula",      "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(124,58,237,0.18),rgba(236,72,153,0.14))"},
    {"id": "bg_molten", "name": "Molten",      "rarity": "Legendary", "value": "linear-gradient(90deg,rgba(239,68,68,0.20),rgba(245,158,11,0.16))"},
    {"id": "bg_prism",  "name": "Prism",       "rarity": "Legendary", "value": "linear-gradient(90deg,rgba(34,211,238,0.16),rgba(132,204,22,0.16),rgba(236,72,153,0.16))"},
    {"id": "bg_singularity","name": "Singularity","rarity": "Apex",  "value": "linear-gradient(90deg,rgba(124,58,237,0.22),rgba(34,211,238,0.18),rgba(124,58,237,0.22))", "animated": True},
]

# ---- Emotes (unlockable emojis usable in chat) ----
EMOTES = [
    {"id": "emote_meat",   "name": "Meat",     "rarity": "Common",    "emote": "🥩", "code": ":meat:"},
    {"id": "emote_leaf",   "name": "Leaf",     "rarity": "Common",    "emote": "🌿", "code": ":leaf:"},
    {"id": "emote_bone",   "name": "Bone",     "rarity": "Common",    "emote": "🦴", "code": ":bone:"},
    {"id": "emote_egg",    "name": "Egg",      "rarity": "Common",    "emote": "🥚", "code": ":egg:"},
    {"id": "emote_target", "name": "Target",   "rarity": "Uncommon",  "emote": "🎯", "code": ":target:"},
    {"id": "emote_shield", "name": "Shield",   "rarity": "Uncommon",  "emote": "🛡️", "code": ":shield:"},
    {"id": "emote_rage",   "name": "Rage",     "rarity": "Uncommon",  "emote": "😤", "code": ":rage:"},
    {"id": "emote_bolt",   "name": "Bolt",     "rarity": "Rare",      "emote": "⚡", "code": ":bolt:"},
    {"id": "emote_blood",  "name": "Blood",    "rarity": "Rare",      "emote": "🩸", "code": ":blood:"},
    {"id": "emote_croc",   "name": "Croc",     "rarity": "Rare",      "emote": "🐊", "code": ":croc:"},
    {"id": "emote_bronto", "name": "Bronto",   "rarity": "Rare",      "emote": "🦕", "code": ":bronto:"},
    {"id": "emote_fire",   "name": "Fire",     "rarity": "Epic",      "emote": "🔥", "code": ":fire:"},
    {"id": "emote_skull",  "name": "Skull",    "rarity": "Epic",      "emote": "💀", "code": ":skull:"},
    {"id": "emote_gem",    "name": "Gem",      "rarity": "Epic",      "emote": "💎", "code": ":gem:"},
    {"id": "emote_volcano","name": "Volcano",  "rarity": "Epic",      "emote": "🌋", "code": ":volcano:"},
    {"id": "emote_crown",  "name": "Crown",    "rarity": "Legendary", "emote": "👑", "code": ":crown:"},
    {"id": "emote_star",   "name": "Star",     "rarity": "Legendary", "emote": "⭐", "code": ":star:"},
    {"id": "emote_party",  "name": "Party",    "rarity": "Legendary", "emote": "🎉", "code": ":party:"},
    {"id": "emote_rex",    "name": "Rex",      "rarity": "Apex",      "emote": "🦖", "code": ":rex:"},
    {"id": "emote_poison", "name": "Poison",   "rarity": "Apex",      "emote": "☠️", "code": ":poison:"},
]

# ---- Expanded catalog (more variety) ----
COLORS += [
    {"id": "color_cyan",   "name": "Cyan",         "rarity": "Common",    "value": "#22d3ee"},
    {"id": "color_lime",   "name": "Lime",         "rarity": "Common",    "value": "#a3e635"},
    {"id": "color_slate",  "name": "Indigo",       "rarity": "Uncommon",  "value": "#6366f1"},
    {"id": "color_teal",   "name": "Teal",         "rarity": "Uncommon",  "value": "#14b8a6"},
    {"id": "color_orange", "name": "Orange",       "rarity": "Rare",      "value": "#fb923c"},
    {"id": "color_coral",  "name": "Coral",        "rarity": "Rare",      "value": "#fb7185"},
    {"id": "color_mint",   "name": "Mint Fusion",  "rarity": "Epic",      "gradient": "linear-gradient(90deg,#34d399,#22d3ee)"},
    {"id": "color_ember",  "name": "Ember Fusion", "rarity": "Epic",      "gradient": "linear-gradient(90deg,#f59e0b,#ef4444)"},
    {"id": "color_galaxy", "name": "Galaxy",       "rarity": "Legendary", "gradient": "linear-gradient(90deg,#6366f1,#a855f7,#ec4899)"},
    {"id": "color_chrome", "name": "Liquid Chrome","rarity": "Apex",      "gradient": "linear-gradient(90deg,#e5e7eb,#9ca3af,#e5e7eb,#6b7280)", "animated": True},
]
BORDERS += [
    {"id": "border_amber",  "name": "Amber Ring",   "rarity": "Common",    "value": "#f59e0b"},
    {"id": "border_teal",   "name": "Teal Ring",    "rarity": "Common",    "value": "#14b8a6"},
    {"id": "border_indigo", "name": "Indigo Ring",  "rarity": "Uncommon",  "value": "#6366f1"},
    {"id": "border_lime",   "name": "Lime Ring",    "rarity": "Uncommon",  "value": "#a3e635"},
    {"id": "border_crimson","name": "Crimson Neon", "rarity": "Rare",      "value": "#ef4444", "glow": True},
    {"id": "border_emerald","name": "Emerald Neon", "rarity": "Rare",      "value": "#10b981", "glow": True},
    {"id": "border_galaxyB","name": "Galaxy Frame", "rarity": "Epic",      "gradient": "linear-gradient(135deg,#6366f1,#ec4899)"},
    {"id": "border_oceanB", "name": "Ocean Frame",  "rarity": "Epic",      "gradient": "linear-gradient(135deg,#22d3ee,#3b82f6)"},
    {"id": "border_inferno","name": "Inferno Frame","rarity": "Legendary", "gradient": "conic-gradient(#ef4444,#f59e0b,#fde047,#ef4444)", "animated": True},
]
EFFECTS += [
    {"id": "fx_glow_pink",   "name": "Pink Glow",     "rarity": "Common",    "kind": "glow",   "color": "#ec4899"},
    {"id": "fx_glow_gold",   "name": "Gold Glow",     "rarity": "Common",    "kind": "glow",   "color": "#f5d020"},
    {"id": "fx_glow_cyan",   "name": "Cyan Glow",     "rarity": "Common",    "kind": "glow",   "color": "#22d3ee"},
    {"id": "fx_pulse_green", "name": "Green Pulse",   "rarity": "Uncommon",  "kind": "pulse",  "color": "#22c55e"},
    {"id": "fx_pulse_blue",  "name": "Blue Pulse",    "rarity": "Uncommon",  "kind": "pulse",  "color": "#38bdf8"},
    {"id": "fx_pulse_pink",  "name": "Pink Pulse",    "rarity": "Uncommon",  "kind": "pulse",  "color": "#ec4899"},
    {"id": "fx_neon_purple", "name": "Purple Neon",   "rarity": "Rare",      "kind": "neon",   "color": "#a855f7"},
    {"id": "fx_neon_gold",   "name": "Gold Neon",     "rarity": "Rare",      "kind": "neon",   "color": "#f5d020"},
    {"id": "fx_neon_lime",   "name": "Lime Neon",     "rarity": "Rare",      "kind": "neon",   "color": "#a3e635"},
    {"id": "fx_shimmer_sil", "name": "Silver Shimmer","rarity": "Rare",      "kind": "shimmer","color": "#e5e7eb"},
    {"id": "fx_shimmer_cy",  "name": "Cyan Shimmer",  "rarity": "Epic",      "kind": "shimmer","color": "#22d3ee"},
    {"id": "fx_grad_ocean",  "name": "Ocean Wave",    "rarity": "Epic",      "kind": "gradient","colors": ["#22d3ee", "#3b82f6", "#6366f1"]},
    {"id": "fx_grad_candy",  "name": "Candy",         "rarity": "Epic",      "kind": "gradient","colors": ["#ec4899", "#f472b6", "#a855f7"]},
    {"id": "fx_grad_frost",  "name": "Frost",         "rarity": "Epic",      "kind": "gradient","colors": ["#a5f3fc", "#38bdf8"]},
    {"id": "fx_grad_toxic",  "name": "Toxic Wave",    "rarity": "Legendary", "kind": "gradient","colors": ["#84cc16", "#22c55e"]},
    {"id": "fx_rainbow_soft","name": "Soft Rainbow",  "rarity": "Legendary", "kind": "rainbow"},
    {"id": "fx_neon_white",  "name": "White Neon",    "rarity": "Legendary", "kind": "neon",   "color": "#f8fafc"},
    {"id": "fx_grad_galaxy", "name": "Galaxy Wave",   "rarity": "Apex",      "kind": "gradient","colors": ["#6366f1", "#a855f7", "#ec4899", "#6366f1"]},
    {"id": "fx_rainbow_apex","name": "Prism Storm",   "rarity": "Apex",      "kind": "rainbow"},
    {"id": "fx_neon_apex",   "name": "Overload",      "rarity": "Apex",      "kind": "neon",   "color": "#22d3ee"},
]
FONTS += [
    {"id": "font_futura",  "name": "Clean Sans",   "rarity": "Common",   "value": "'Trebuchet MS', sans-serif"},
    {"id": "font_narrow",  "name": "Condensed",    "rarity": "Uncommon", "value": "'Arial Narrow', sans-serif"},
    {"id": "font_type",    "name": "Typewriter",   "rarity": "Uncommon", "value": "'Lucida Console', monospace"},
    {"id": "font_palat",   "name": "Classic Serif","rarity": "Rare",     "value": "'Palatino Linotype', Palatino, serif"},
    {"id": "font_black",   "name": "Heavy Black",  "rarity": "Rare",     "value": "'Arial Black', sans-serif"},
    {"id": "font_brush",   "name": "Brush Script", "rarity": "Epic",     "value": "'Brush Script MT', cursive"},
]
CHAT_BG += [
    {"id": "bg_rose",    "name": "Rose",     "rarity": "Common",    "value": "rgba(244,63,94,0.12)"},
    {"id": "bg_sky",     "name": "Sky",      "rarity": "Common",    "value": "rgba(56,189,248,0.12)"},
    {"id": "bg_lime",    "name": "Lime",     "rarity": "Uncommon",  "value": "rgba(163,230,53,0.12)"},
    {"id": "bg_indigo",  "name": "Indigo",   "rarity": "Uncommon",  "value": "rgba(99,102,241,0.14)"},
    {"id": "bg_teal",    "name": "Teal",     "rarity": "Rare",      "value": "rgba(20,184,166,0.13)"},
    {"id": "bg_candy",   "name": "Candy",    "rarity": "Rare",      "value": "linear-gradient(90deg,rgba(236,72,153,0.16),rgba(168,85,247,0.16))"},
    {"id": "bg_ocean2",  "name": "Deep Sea", "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(34,211,238,0.16),rgba(59,130,246,0.16))"},
    {"id": "bg_toxic",   "name": "Toxic",    "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(132,204,22,0.16),rgba(34,197,94,0.16))"},
    {"id": "bg_inferno", "name": "Inferno",  "rarity": "Legendary", "value": "linear-gradient(90deg,rgba(239,68,68,0.20),rgba(251,146,60,0.16))"},
    {"id": "bg_galaxy",  "name": "Galaxy",   "rarity": "Legendary", "value": "linear-gradient(90deg,rgba(99,102,241,0.18),rgba(168,85,247,0.16),rgba(236,72,153,0.16))"},
    {"id": "bg_void",    "name": "Void",     "rarity": "Apex",      "value": "linear-gradient(90deg,rgba(15,23,42,0.55),rgba(124,58,237,0.24),rgba(15,23,42,0.55))", "animated": True},
    {"id": "bg_chrome",  "name": "Chrome",   "rarity": "Apex",      "value": "linear-gradient(90deg,rgba(229,231,235,0.18),rgba(148,163,184,0.14),rgba(229,231,235,0.18))", "animated": True},
]
EMOTES += [
    {"id": "emote_lizard", "name": "Lizard",  "rarity": "Common",    "emote": "🦎", "code": ":lizard:"},
    {"id": "emote_turtle", "name": "Turtle",  "rarity": "Common",    "emote": "🐢", "code": ":turtle:"},
    {"id": "emote_paw",    "name": "Paw",     "rarity": "Common",    "emote": "🐾", "code": ":paw:"},
    {"id": "emote_wave",   "name": "Wave",    "rarity": "Common",    "emote": "🌊", "code": ":wave:"},
    {"id": "emote_snow",   "name": "Snow",    "rarity": "Common",    "emote": "❄️", "code": ":snow:"},
    {"id": "emote_muscle", "name": "Muscle",  "rarity": "Uncommon",  "emote": "💪", "code": ":muscle:"},
    {"id": "emote_cool",   "name": "Cool",    "rarity": "Uncommon",  "emote": "😎", "code": ":cool:"},
    {"id": "emote_scream", "name": "Scream",  "rarity": "Uncommon",  "emote": "😱", "code": ":scream:"},
    {"id": "emote_salute", "name": "Salute",  "rarity": "Uncommon",  "emote": "🫡", "code": ":salute:"},
    {"id": "emote_100",    "name": "Hundred", "rarity": "Uncommon",  "emote": "💯", "code": ":100:"},
    {"id": "emote_storm",  "name": "Storm",   "rarity": "Rare",      "emote": "🌩️", "code": ":storm:"},
    {"id": "emote_devil",  "name": "Devil",   "rarity": "Rare",      "emote": "😈", "code": ":devil:"},
    {"id": "emote_lol",    "name": "LOL",     "rarity": "Rare",      "emote": "🤣", "code": ":lol:"},
    {"id": "emote_cry",    "name": "Cry",     "rarity": "Rare",      "emote": "😭", "code": ":cry:"},
    {"id": "emote_sword",  "name": "Sword",   "rarity": "Rare",      "emote": "⚔️", "code": ":sword:"},
    {"id": "emote_alien",  "name": "Alien",   "rarity": "Epic",      "emote": "👽", "code": ":alien:"},
    {"id": "emote_robot",  "name": "Robot",   "rarity": "Epic",      "emote": "🤖", "code": ":robot:"},
    {"id": "emote_game",   "name": "Gamepad", "rarity": "Epic",      "emote": "🎮", "code": ":game:"},
    {"id": "emote_medal",  "name": "Medal",   "rarity": "Epic",      "emote": "🥇", "code": ":medal:"},
    {"id": "emote_pray",   "name": "Pray",    "rarity": "Epic",      "emote": "🙏", "code": ":pray:"},
    {"id": "emote_dragon", "name": "Dragon",  "rarity": "Legendary", "emote": "🐉", "code": ":dragon:"},
    {"id": "emote_trophy", "name": "Trophy",  "rarity": "Legendary", "emote": "🏆", "code": ":trophy:"},
    {"id": "emote_rocket", "name": "Rocket",  "rarity": "Legendary", "emote": "🚀", "code": ":rocket:"},
    {"id": "emote_goat",   "name": "GOAT",    "rarity": "Apex",      "emote": "🐐", "code": ":goat:"},
    {"id": "emote_infinity","name": "Infinity","rarity": "Apex",     "emote": "♾️", "code": ":infinity:"},
]


_GROUPS = {
    "color": COLORS, "border": BORDERS, "effect": EFFECTS,
    "font": FONTS, "chat_bg": CHAT_BG, "emote": EMOTES,
}

# ===== Expansion #2 (more variety + emote packs) =====
COLORS += [
    {"id": "color_red",    "name": "Scarlet",    "rarity": "Common",    "value": "#dc2626"},
    {"id": "color_amber2", "name": "Amber",       "rarity": "Common",    "value": "#fbbf24"},
    {"id": "color_violet", "name": "Violet",      "rarity": "Uncommon",  "value": "#8b5cf6"},
    {"id": "color_emerald","name": "Emerald",     "rarity": "Uncommon",  "value": "#10b981"},
    {"id": "color_magenta","name": "Magenta",     "rarity": "Rare",      "value": "#d946ef"},
    {"id": "color_azure",  "name": "Azure",       "rarity": "Rare",      "value": "#3b82f6"},
    {"id": "color_lava",   "name": "Lava",        "rarity": "Epic",      "gradient": "linear-gradient(90deg,#f97316,#dc2626)"},
    {"id": "color_neonfx", "name": "Neon Dream",  "rarity": "Legendary", "gradient": "linear-gradient(90deg,#22d3ee,#a855f7,#ec4899)"},
]
BORDERS += [
    {"id": "border_red",    "name": "Scarlet Ring", "rarity": "Common",    "value": "#dc2626"},
    {"id": "border_violet2","name": "Violet Ring",   "rarity": "Common",    "value": "#8b5cf6"},
    {"id": "border_pink",   "name": "Pink Ring",     "rarity": "Uncommon",  "value": "#ec4899"},
    {"id": "border_cyan2",  "name": "Cyan Ring",     "rarity": "Uncommon",  "value": "#22d3ee"},
    {"id": "border_goldN",  "name": "Gold Neon",     "rarity": "Rare",      "value": "#fbbf24", "glow": True},
    {"id": "border_violetN","name": "Violet Neon",   "rarity": "Rare",      "value": "#a855f7", "glow": True},
    {"id": "border_lavaB",  "name": "Lava Frame",    "rarity": "Epic",      "gradient": "linear-gradient(135deg,#f97316,#dc2626)"},
    {"id": "border_prismB", "name": "Prism Frame",   "rarity": "Legendary", "gradient": "conic-gradient(#22d3ee,#a855f7,#ec4899,#22d3ee)", "animated": True},
]
EFFECTS += [
    {"id": "fx_glow_red",    "name": "Red Glow",      "rarity": "Common",    "kind": "glow",   "color": "#ef4444"},
    {"id": "fx_glow_violet", "name": "Violet Glow",   "rarity": "Common",    "kind": "glow",   "color": "#8b5cf6"},
    {"id": "fx_glow_teal",   "name": "Teal Glow",     "rarity": "Common",    "kind": "glow",   "color": "#14b8a6"},
    {"id": "fx_glow_orange", "name": "Orange Glow",   "rarity": "Common",    "kind": "glow",   "color": "#fb923c"},
    {"id": "fx_pulse_purple","name": "Purple Pulse",  "rarity": "Uncommon",  "kind": "pulse",  "color": "#a855f7"},
    {"id": "fx_pulse_cyan",  "name": "Cyan Pulse",    "rarity": "Uncommon",  "kind": "pulse",  "color": "#22d3ee"},
    {"id": "fx_pulse_gold",  "name": "Gold Pulse",    "rarity": "Uncommon",  "kind": "pulse",  "color": "#f5d020"},
    {"id": "fx_pulse_white", "name": "White Pulse",   "rarity": "Uncommon",  "kind": "pulse",  "color": "#f8fafc"},
    {"id": "fx_neon_red",    "name": "Red Neon",      "rarity": "Rare",      "kind": "neon",   "color": "#ef4444"},
    {"id": "fx_neon_blue",   "name": "Blue Neon",     "rarity": "Rare",      "kind": "neon",   "color": "#3b82f6"},
    {"id": "fx_neon_orange", "name": "Orange Neon",   "rarity": "Rare",      "kind": "neon",   "color": "#fb923c"},
    {"id": "fx_shimmer_pink","name": "Pink Shimmer",  "rarity": "Rare",      "kind": "shimmer","color": "#ec4899"},
    {"id": "fx_grad_lava",   "name": "Lava Flow",     "rarity": "Epic",      "kind": "gradient","colors": ["#f97316", "#dc2626"]},
    {"id": "fx_grad_neon",   "name": "Neon Flow",     "rarity": "Epic",      "kind": "gradient","colors": ["#22d3ee", "#a855f7", "#ec4899"]},
    {"id": "fx_grad_emerald","name": "Emerald Flow",  "rarity": "Epic",      "kind": "gradient","colors": ["#34d399", "#10b981"]},
    {"id": "fx_shimmer_gold2","name": "Royal Shimmer","rarity": "Epic",      "kind": "shimmer","color": "#fbbf24"},
    {"id": "fx_rainbow_bold","name": "Bold Rainbow",  "rarity": "Legendary", "kind": "rainbow"},
    {"id": "fx_grad_sunset2","name": "Sunset Blaze",  "rarity": "Legendary", "kind": "gradient","colors": ["#f59e0b", "#ec4899", "#8b5cf6"]},
    {"id": "fx_neon_pink2",  "name": "Hot Neon",      "rarity": "Legendary", "kind": "neon",   "color": "#ec4899"},
    {"id": "fx_grad_aurora2","name": "Aurora Storm",  "rarity": "Apex",      "kind": "gradient","colors": ["#22d3ee", "#34d399", "#a855f7", "#22d3ee"]},
    {"id": "fx_rainbow_mega","name": "Mega Prism",    "rarity": "Apex",      "kind": "rainbow"},
    {"id": "fx_neon_gold2",  "name": "Golden God",    "rarity": "Apex",      "kind": "neon",   "color": "#f5d020"},
]
# Fonts using loaded Google Fonts (see public/index.html)
FONTS += [
    {"id": "font_bebas",    "name": "Bebas",       "rarity": "Uncommon",  "value": "'Bebas Neue', Impact, sans-serif"},
    {"id": "font_vt323",    "name": "CRT Terminal","rarity": "Uncommon",  "value": "'VT323', monospace"},
    {"id": "font_righteous","name": "Righteous",   "rarity": "Uncommon",  "value": "'Righteous', sans-serif"},
    {"id": "font_pacifico", "name": "Pacifico",    "rarity": "Rare",      "value": "'Pacifico', cursive"},
    {"id": "font_bangers",  "name": "Comic Bang",  "rarity": "Rare",      "value": "'Bangers', cursive"},
    {"id": "font_orbitron", "name": "Orbitron",    "rarity": "Rare",      "value": "'Orbitron', sans-serif"},
    {"id": "font_cinzel",   "name": "Cinzel",      "rarity": "Epic",      "value": "'Cinzel', serif"},
    {"id": "font_audiowide","name": "Audiowide",   "rarity": "Epic",      "value": "'Audiowide', sans-serif"},
    {"id": "font_pixel",    "name": "Pixel Arcade","rarity": "Legendary", "value": "'Press Start 2P', monospace"},
    {"id": "font_creepster","name": "Creepster",   "rarity": "Legendary", "value": "'Creepster', cursive"},
]
CHAT_BG += [
    {"id": "bg_scarlet", "name": "Scarlet",  "rarity": "Common",    "value": "rgba(220,38,38,0.12)"},
    {"id": "bg_amber2",  "name": "Amber",    "rarity": "Common",    "value": "rgba(251,191,36,0.13)"},
    {"id": "bg_violet",  "name": "Violet",   "rarity": "Uncommon",  "value": "rgba(139,92,246,0.14)"},
    {"id": "bg_emerald", "name": "Emerald",  "rarity": "Uncommon",  "value": "rgba(16,185,129,0.13)"},
    {"id": "bg_magenta", "name": "Magenta",  "rarity": "Rare",      "value": "rgba(217,70,239,0.14)"},
    {"id": "bg_lava",    "name": "Lava",     "rarity": "Rare",      "value": "linear-gradient(90deg,rgba(249,115,22,0.16),rgba(220,38,38,0.16))"},
    {"id": "bg_neon",    "name": "Neon",     "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(34,211,238,0.16),rgba(217,70,239,0.16))"},
    {"id": "bg_forest2", "name": "Jungle",   "rarity": "Epic",      "value": "linear-gradient(90deg,rgba(52,211,153,0.16),rgba(16,185,129,0.14))"},
    {"id": "bg_solar",   "name": "Solar",    "rarity": "Legendary", "value": "linear-gradient(90deg,rgba(251,191,36,0.20),rgba(236,72,153,0.16))"},
    {"id": "bg_prism2",  "name": "Prism",    "rarity": "Apex",      "value": "linear-gradient(90deg,rgba(34,211,238,0.18),rgba(168,85,247,0.18),rgba(236,72,153,0.18))", "animated": True},
]

# Emote packs (tabs in the chat picker).
EMOTE_PACKS = [
    {"key": "react",   "label": "React"},
    {"key": "meme",    "label": "Meme"},
    {"key": "dino",    "label": "Dino"},
    {"key": "vibe",    "label": "Vibe"},
    {"key": "animals", "label": "Animals"},
]

# Assign a pack to every existing emote.
_EMOTE_PACK_BY_ID = {
    # dino
    "emote_meat": "dino", "emote_leaf": "dino", "emote_bone": "dino", "emote_egg": "dino",
    "emote_croc": "dino", "emote_bronto": "dino", "emote_rex": "dino", "emote_poison": "dino",
    "emote_target": "dino", "emote_shield": "dino", "emote_sword": "dino",
    # vibe
    "emote_bolt": "vibe", "emote_fire": "vibe", "emote_gem": "vibe", "emote_volcano": "vibe",
    "emote_crown": "vibe", "emote_star": "vibe", "emote_party": "vibe", "emote_trophy": "vibe",
    "emote_rocket": "vibe", "emote_medal": "vibe", "emote_infinity": "vibe", "emote_storm": "vibe",
    "emote_snow": "vibe", "emote_wave": "vibe", "emote_game": "vibe", "emote_blood": "vibe",
    # meme
    "emote_skull": "meme", "emote_devil": "meme", "emote_alien": "meme", "emote_robot": "meme",
    "emote_100": "meme", "emote_rage": "meme",
    # react
    "emote_muscle": "react", "emote_cool": "react", "emote_scream": "react", "emote_salute": "react",
    "emote_lol": "react", "emote_cry": "react", "emote_pray": "react",
    # animals
    "emote_lizard": "animals", "emote_turtle": "animals", "emote_paw": "animals",
    "emote_goat": "animals", "emote_dragon": "animals",
}
for _e in EMOTES:
    _e["pack"] = _EMOTE_PACK_BY_ID.get(_e["id"], "react")

# Many more emotes.
EMOTES += [
    # react (faces)
    {"id": "emote_grin",   "name": "Grin",     "rarity": "Common",    "pack": "react", "emote": "😁", "code": ":grin:"},
    {"id": "emote_sweat",  "name": "Sweat",    "rarity": "Common",    "pack": "react", "emote": "😅", "code": ":sweat:"},
    {"id": "emote_wink",   "name": "Wink",     "rarity": "Common",    "pack": "react", "emote": "😉", "code": ":wink:"},
    {"id": "emote_kiss",   "name": "Kiss",     "rarity": "Common",    "pack": "react", "emote": "😘", "code": ":kiss:"},
    {"id": "emote_tongue", "name": "Tongue",   "rarity": "Common",    "pack": "react", "emote": "😜", "code": ":tongue:"},
    {"id": "emote_neutral","name": "Neutral",  "rarity": "Uncommon",  "pack": "react", "emote": "😐", "code": ":neutral:"},
    {"id": "emote_sleepy", "name": "Sleepy",   "rarity": "Uncommon",  "pack": "react", "emote": "😴", "code": ":sleepy:"},
    {"id": "emote_angry",  "name": "Angry",    "rarity": "Uncommon",  "pack": "react", "emote": "😡", "code": ":angry:"},
    {"id": "emote_hug",    "name": "Hug",      "rarity": "Uncommon",  "pack": "react", "emote": "🤗", "code": ":hug:"},
    {"id": "emote_shush",  "name": "Shush",    "rarity": "Rare",      "pack": "react", "emote": "🤫", "code": ":shush:"},
    {"id": "emote_zany",   "name": "Zany",     "rarity": "Rare",      "pack": "react", "emote": "🤪", "code": ":zany:"},
    {"id": "emote_mind",   "name": "Mindblown","rarity": "Epic",      "pack": "react", "emote": "🤯", "code": ":mindblown:"},
    # meme
    {"id": "emote_clown",  "name": "Clown",    "rarity": "Common",    "pack": "meme",  "emote": "🤡", "code": ":clown:"},
    {"id": "emote_nerd",   "name": "Nerd",     "rarity": "Uncommon",  "pack": "meme",  "emote": "🤓", "code": ":nerd:"},
    {"id": "emote_moai",   "name": "Moai",     "rarity": "Rare",      "pack": "meme",  "emote": "🗿", "code": ":moai:"},
    {"id": "emote_woozy",  "name": "Woozy",    "rarity": "Rare",      "pack": "meme",  "emote": "🥴", "code": ":woozy:"},
    {"id": "emote_dizzy",  "name": "Dizzy",    "rarity": "Epic",      "pack": "meme",  "emote": "😵‍💫", "code": ":dizzy:"},
    {"id": "emote_melt",   "name": "Melt",     "rarity": "Epic",      "pack": "meme",  "emote": "🫠", "code": ":melt:"},
    {"id": "emote_sick",   "name": "Sick",     "rarity": "Uncommon",  "pack": "meme",  "emote": "🤢", "code": ":sick:"},
    {"id": "emote_cowboy", "name": "Cowboy",   "rarity": "Rare",      "pack": "meme",  "emote": "🤠", "code": ":cowboy:"},
    # dino
    {"id": "emote_dodo",   "name": "Dodo",     "rarity": "Rare",      "pack": "dino",  "emote": "🦤", "code": ":dodo:"},
    {"id": "emote_snake",  "name": "Snake",    "rarity": "Uncommon",  "pack": "dino",  "emote": "🐍", "code": ":snake:"},
    {"id": "emote_nest",   "name": "Nest",     "rarity": "Rare",      "pack": "dino",  "emote": "🪺", "code": ":nest:"},
    {"id": "emote_meteor", "name": "Meteor",   "rarity": "Epic",      "pack": "dino",  "emote": "☄️", "code": ":meteor:"},
    {"id": "emote_tree",   "name": "Tree",     "rarity": "Common",    "pack": "dino",  "emote": "🌴", "code": ":tree:"},
    {"id": "emote_footprint","name": "Tracks", "rarity": "Common",    "pack": "dino",  "emote": "👣", "code": ":tracks:"},
    # vibe
    {"id": "emote_sparkle","name": "Sparkle",  "rarity": "Common",    "pack": "vibe",  "emote": "✨", "code": ":sparkle:"},
    {"id": "emote_boom",   "name": "Boom",     "rarity": "Uncommon",  "pack": "vibe",  "emote": "💥", "code": ":boom:"},
    {"id": "emote_rainbow","name": "Rainbow",  "rarity": "Rare",      "pack": "vibe",  "emote": "🌈", "code": ":rainbow:"},
    {"id": "emote_disco",  "name": "Disco",    "rarity": "Epic",      "pack": "vibe",  "emote": "🪩", "code": ":disco:"},
    {"id": "emote_glowstar","name": "Glow Star","rarity": "Rare",     "pack": "vibe",  "emote": "🌟", "code": ":glowstar:"},
    {"id": "emote_comet",  "name": "Comet",    "rarity": "Legendary", "pack": "vibe",  "emote": "🎇", "code": ":comet:"},
    {"id": "emote_moneybag","name": "Money",   "rarity": "Legendary", "pack": "vibe",  "emote": "💰", "code": ":money:"},
    # animals
    {"id": "emote_wolf",   "name": "Wolf",     "rarity": "Uncommon",  "pack": "animals","emote": "🐺", "code": ":wolf:"},
    {"id": "emote_fox",    "name": "Fox",      "rarity": "Uncommon",  "pack": "animals","emote": "🦊", "code": ":fox:"},
    {"id": "emote_lion",   "name": "Lion",     "rarity": "Rare",      "pack": "animals","emote": "🦁", "code": ":lion:"},
    {"id": "emote_tiger",  "name": "Tiger",    "rarity": "Rare",      "pack": "animals","emote": "🐯", "code": ":tiger:"},
    {"id": "emote_eagle",  "name": "Eagle",    "rarity": "Rare",      "pack": "animals","emote": "🦅", "code": ":eagle:"},
    {"id": "emote_shark",  "name": "Shark",    "rarity": "Epic",      "pack": "animals","emote": "🦈", "code": ":shark:"},
    {"id": "emote_octopus","name": "Octopus",  "rarity": "Epic",      "pack": "animals","emote": "🐙", "code": ":octopus:"},
    {"id": "emote_scorpion","name": "Scorpion","rarity": "Legendary", "pack": "animals","emote": "🦂", "code": ":scorpion:"},
]



# Flatten into a single list with the category tag on every item.
DECORATIONS = []
for _cat, _items in _GROUPS.items():
    for _it in _items:
        DECORATIONS.append({**_it, "category": _cat})

DECO_BY_ID = {d["id"]: d for d in DECORATIONS}


def items_by_category(cat: str):
    return [d for d in DECORATIONS if d["category"] == cat]


ITEMS_BY_RARITY = {}
for _d in DECORATIONS:
    ITEMS_BY_RARITY.setdefault(_d["rarity"], []).append(_d)


# Dino Eggs — NOT purchasable. Only won from crates and the daily login gift.
# Four rarity tiers; each tier's shell colour matches its rarity and defines the
# odds of the decoration rarity you pull when you open it.
EGGS = {
    "common": {
        "id": "egg_common", "tier": "common", "name": "Huevo Común", "rarity": "Common",
        "color": "#9ca3af", "image": "/cosmetics/egg-common.png",
        "buckets": [("Common", 42), ("Uncommon", 10), ("coins", 48)], "coin_amounts": [200, 400, 600, 1000, 1500],
    },
    "uncommon": {
        "id": "egg_uncommon", "tier": "uncommon", "name": "Huevo Poco Común", "rarity": "Uncommon",
        "color": "#22c55e", "image": "/cosmetics/egg-uncommon.png",
        "buckets": [("Common", 20), ("Uncommon", 24), ("Rare", 8), ("coins", 48)], "coin_amounts": [300, 600, 900, 1200, 1500],
    },
    "rare": {
        "id": "egg_rare", "tier": "rare", "name": "Huevo Raro", "rarity": "Rare",
        "color": "#38bdf8", "image": "/cosmetics/egg-rare.png",
        "buckets": [("Uncommon", 18), ("Rare", 22), ("Epic", 10), ("Legendary", 2), ("coins", 48)], "coin_amounts": [500, 800, 1000, 1200, 1500],
    },
    "epic": {
        "id": "egg_epic", "tier": "epic", "name": "Huevo Épico", "rarity": "Epic",
        "color": "#a855f7", "image": "/cosmetics/egg-epic.png",
        "buckets": [("Rare", 20), ("Epic", 24), ("Legendary", 8), ("Apex", 1), ("coins", 47)], "coin_amounts": [700, 1000, 1200, 1400, 1500],
    },
    "legendary": {
        "id": "egg_legendary", "tier": "legendary", "name": "Huevo Legendario", "rarity": "Legendary",
        "color": "#f59e0b", "image": "/cosmetics/egg-legendary.png",
        "buckets": [("Epic", 24), ("Legendary", 24), ("Apex", 3), ("coins", 49)], "coin_amounts": [1000, 1200, 1300, 1400, 1500],
    },
}
EGG_TIERS = ["common", "uncommon", "rare", "epic", "legendary"]


def egg_odds(tier):
    """Decoration-rarity odds (%) for a given egg tier (for UI display)."""
    egg = EGGS[tier]
    total = sum(w for _, w in egg["buckets"])
    return [{"label": b, "chance": round(w / total * 100, 2),
             "color": (DECO_RARITY.get(b, {}).get("color") if b != "coins" else "#34D399")}
            for b, w in egg["buckets"]]


def egg_draw(tier, roll_bucket, roll_item):
    """Two-step provably-fair draw: pick a rarity/coins bucket, then an item within it."""
    egg = EGGS[tier]
    buckets = egg["buckets"]
    total = sum(w for _, w in buckets)
    target = roll_bucket * total
    acc, chosen = 0.0, buckets[-1][0]
    for b, w in buckets:
        acc += w
        if target < acc:
            chosen = b
            break
    if chosen == "coins":
        amts = egg["coin_amounts"]
        amt = amts[min(int(roll_item * len(amts)), len(amts) - 1)]
        return {"type": "coins", "amount": amt, "rarity": egg["rarity"]}
    items = ITEMS_BY_RARITY.get(chosen, [])
    if not items:
        return {"type": "coins", "amount": egg["coin_amounts"][0], "rarity": chosen}
    it = items[min(int(roll_item * len(items)), len(items) - 1)]
    return {"type": "decoration", "id": it["id"], "rarity": chosen}


def egg_random_entry(tier):
    """Random outcome for reel filler (visual only)."""
    import random as _r
    return egg_draw(tier, _r.random(), _r.random())

