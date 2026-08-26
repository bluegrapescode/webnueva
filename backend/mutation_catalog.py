# -*- coding: utf-8 -*-
"""Vault mutation editor catalog (owner ask 2026-07-11: players edit a stored
dino's mutations from the web for a PrimeMeat charge — Dino Den style, up to
16 slots, diet-class restricted, no duplicates).

Species diet classification + pickable pool follow the fleet set first shipped
for a donor shop picker implementation (
mutation_catalog.py); the per-mutation diet RESTRICTIONS were re-derived from
the game's own availability rules on 2026-07-12 (the earlier 4/3 split was too
small — see the note above CARNIVORE_ONLY). The CARNIVORES set is
byte-identical to the LIN mod's own validator
(_G.LaIslaNublarMutV2.carnivores, main.full.lua:7232) so a species is never
classified differently on the web than in-game. Every PICKABLE name resolves
inside the mod's known-mutation table and none is in its banned table.

2026-07-27: the five that the server never enabled are in. Reabsorption,
Barometric Sensitivity, Social Behavior, Parthenogenesis and Cannibalistic are
all real on this build (the Shipping exe carries a name and a player-facing
description for each) and the owner enabled all five in Game.ini, so the site
now offers exactly what the game has - 41 - and nothing it does not. NEVER add
a name here before the MOD half that accepts it is LIVE: a name the running mod
refuses is dropped from the dino AND makes the restore report failure, which
leaves the vault copy alive beside a dinosaur that already spawned.

2026-08-12: the 41 became true in PICKABLE too. Parthenogenesis had been held
back (only from the site) while the C++ half that arms its reproduction-unlock
byte was unshippable; that DLL has been live since the 08-10/08-11 rebuilds, so
the catalog finally offers it — see the dated note inside PICKABLE. Any stored
name this catalog does NOT recognise is now also named once in the log by
slot_lock_map ("stored name not in catalog"), so the next mutation the game
grows lands in the log the first day a player opens the editor on it, instead
of arriving as a "my slot is bugged" ticket weeks later.

Slot model — mirrors bot-src/mutations.py SLOT_CHOICES and the parked_dinos
"|"-string encoding the redeem restore passes to the game verbatim:
  n1..n4  -> mutations         (4 segments)
  p1..p4  -> parent_mutations  (4 segments)
  ea1..ea4 / eb1..eb4 -> elder_mutations (8 segments, INTERLEAVED — see
  _SLOT_MAP: the pairs are 1A,1B,2A,2B,3A,3B,4A,4B, NOT the four A's followed
  by the four B's).
The dino's OWN slots (n1..n4) are gated on growth and Prime (owner ruling
2026-07-25, see GROWTH_LADDER) and the twelve INHERITED slots are gated on how
many times the dino has been entombed (owner ruling 2026-07-26, see
ENTOMB_LADDER). Clearing a slot is never gated and never charged.

On top of those two ladders, n1 and n3 do not OFFER the game's unlockable
mutations (owner ruling 2026-07-27, see HIDDEN / HIDDEN_BLOCKED_SLOTS). That is
a third, independent axis: the ladders say whether a slot may be written at all,
the diet sets say which names a SPECIES may carry, and this says which names a
SLOT may be given. Keep the three apart.

Game-captured strings may hold camel-case names (e.g. AcceleratedPreyDrive);
the mod's own writes use spaced display names. Comparison always goes through
normalize_mutation_name(); writes emit the canonical spaced display name,
matching what the mod's set_mutation_slot lane writes on live players.
"""
from __future__ import annotations

import logging
from functools import lru_cache

_log = logging.getLogger("laislanublar.mutations")

# Stored values already warned about this process (see the beacon in
# slot_lock_map). Process-lifetime on purpose: one line per unknown name is a
# signal, one per GET is noise.
_UNKNOWN_STORED_SEEN: set[str] = set()

# ── species diet classification ───────────────────────────────────────────────
CARNIVORES = {
    "BP_Tyrannosaurus_C", "BP_Allosaurus_C", "BP_Carnotaurus_C",
    "BP_Ceratosaurus_C", "BP_Deinosuchus_C", "BP_Dilophosaurus_C",
    "BP_Herrerasaurus_C", "BP_Troodon_C", "BP_Omniraptor_C",
    "BP_Pteranodon_C", "BP_Austroraptor_C",
}
HERBIVORES = {
    "BP_Stegosaurus_C", "BP_Triceratops_C", "BP_Maiasaura_C",
    "BP_Hypsilophodon_C", "BP_Pachycephalosaurus_C", "BP_Tenontosaurus_C",
    "BP_Beipiaosaurus_C", "BP_Dryosaurus_C", "BP_Diabloceratops_C",
    "BP_Kentrosaurus_C",
}
GALLIMIMUS = {"BP_Gallimimus_C"}


# ── pickable pool (41 = every mutation the game has) ─────────────────────────
PICKABLE: tuple[str, ...] = (
    "Hemomania", "Accelerated Prey Drive", "Hypermetabolic Inanition",
    "Osteophagic", "Augmented Tapetum", "Xerocole Adaptation",
    "Tactile Endurance", "Hematophagy", "Truculency",
    "Photosynthetic Regeneration", "Cellular Regeneration",
    "Advanced Gestation", "Sustained Hydration", "Efficient Digestion",
    "Featherweight", "Osteosclerosis", "Wader", "Epidermal Fibrosis",
    "Congenital Hypoalgesia", "Photosynthetic Tissue", "Nocturnal",
    "Hydroregenerative", "Increased Inspiratory Capacity", "Hydrodynamic",
    "Submerged Optical Retention", "Enhanced Digestion",
    "Reinforced Tendons", "Multichambered Lungs",
    "Infrasound Communication", "Heightened Ghrelin",
    "Prolific Reproduction", "Gastronomic Regeneration", "Hypervigilance",
    "Enlarged Meniscus", "Reniculate Kidneys", "Sequential Hermaphroditism",
    "Reabsorption", "Barometric Sensitivity", "Social Behavior",
    "Cannibalistic",
    # PARTHENOGENESIS WAS HELD BACK from the site 2026-07-27..08-11 while the
    # C++ half that arms its ability was unshippable: it is one of the three
    # reproduction mutations whose value only resolves when the per-dino
    # reproduction-unlock byte is also set, and that byte is written by the
    # mod's C++ force-unlock lane. That lane is LIVE now — the shipped DLL's
    # kRegistryDefaults carries {"parthenogenesis", repro1450=true}
    # (PEDispatch.cpp, proven in the live binary on 2026-08-12: the string
    # sits in the on-box main.dll) — so a redeemed dino gets the ability, not
    # just the name. Meanwhile the GAME had been rolling it since 2026-07-29
    # (58 parked segments carried it while the site refused the name and drew
    # those slots as unrecognised: the "my 4th mutation is bugged, I can't
    # edit it" ticket class). The hold-back note promised "put it back the
    # day the DLL ships - it is this one line"; this is that line.
    "Parthenogenesis",
)

# Diet restrictions = the GAME's own availability rules (owner report
# 2026-07-12: "tactile endurance ... herbi muts" were pickable on carnivores —
# the earlier 4/3 split was too small). Verified against the in-game
# availability table (evrimaquickguide.com/gameplay/health-statuses/mutations)
# and byte-identical to JK's shop catalog diet flags
# (C:\IsleLocalFleet\JurassicKingdom\web\packages\domain\src\shop\catalog.ts).
# NOTE Photosynthetic Tissue is available to ALL diets in-game (only
# Photosynthetic Regeneration is herbivore-only).
CARNIVORE_ONLY: frozenset[str] = frozenset({
    "Hemomania", "Hematophagy", "Accelerated Prey Drive",
    "Hypermetabolic Inanition", "Osteophagic", "Augmented Tapetum",
    # The mod refuses this one on a non-carnivore itself (validateMutationForSid
    # is the only diet gate it has), so the site has to agree with it.
    "Cannibalistic",
})
HERBIVORE_ONLY: frozenset[str] = frozenset({
    "Xerocole Adaptation", "Photosynthetic Regeneration",
    "Truculency", "Hypervigilance", "Tactile Endurance",
})
GENERIC: frozenset[str] = frozenset(PICKABLE) - CARNIVORE_ONLY - HERBIVORE_ONLY

# ── UNLOCKABLE ("hidden") mutations — the game's own bHasRequirement flag ─────
#
# THE ORACLE IS THE GAME BINARY. Not a wiki, and not the mod: the mod has no
# such list at all (its kRegistryDefaults / isRegistryDefaultName is five names
# about HOW a capability is switched on, not about whether it is in the roll
# pool, and only one name is in both sets). Every mutation the server registers
# carries a per-mutation UE property `bHasRequirement` — the reflection strings
# sit together in .rdata at file 0x08EF3F08 `MutationDescription`, 0x08EF3F20
# `MutationType`, 0x08EF3F70 `bHasRequirement`.
#
# WHERE THE BYTES ARE. The registry builder at .text RVA 0xF7E6E8 of
#   C:\IsleOps\ghidra_inputs\TheIsleServer-24167035-B1BCBEE1.exe
# (185,213,952 B, a local byte-identical copy of LIN's prod
# TheIsleServer-Win64-Shipping.exe — no box access was needed) lays out 43 stack
# structs of stride 0x24 and stores two immediates per entry: base+0x10 =
# MutationType (enum ETIMutationTypes) and base+0x20 = bHasRequirement. Exactly
# SEVEN entries carry bHasRequirement = 1, at the .text RVAs listed against each
# name below (registry positions 4, 26, 27, 28, 29, 34 and 41 of 43).
#
# WHAT THE FLAG MEANS. GetAllEnabledLifecycleMutations reads it: a 0 mutation is
# ALWAYS in the enabled set; a non-zero one is included ONLY when its FName is
# already in that dino's MutationsRequirementsData (the per-dino unlock pool at
# +0x960). That is exactly "not in the normal roll pool, has to be earned in
# game first" — the community's "unlockable" / "lifestyle" mutation. Two of the
# seven have their own earn-by-use handlers in the same binary (Reniculate
# Kidneys counts saltwater drinks to 99/999, Heightened Ghrelin to 1799).
#
# THAT OFFSET IS NOT READ OFF A DISASSEMBLY, it is the number the binary states
# about itself. UE registers every property with its own byte offset inside the
# owner, and the record for MutationsRequirementsData sits in .rdata at file
# 0x08F5AA40 (rva 0x08F5B840): a pointer to the name string at file 0x08F47D58,
# EPropertyGenFlags 0x19 (Struct), ObjectFlags 0x45, then ArrayDim = 1 and
# Offset = 0x960 as two uint16 at +0x30. (Until 2026-07-26 this block cited a
# number eight bytes lower, which was simply wrong. Nothing else in it moved, and
# the same dump re-confirms the rest — bHasRequirement's own record at file
# 0x08EF3C30 reads Flags 0x4C = Bool|NativeBool with SizeOfOuter 0x24, the very
# stride the registry walk below uses.)
#
# HOW POSITION -> NAME WAS PROVEN, since a wrong alignment here would block a
# mutation players are entitled to. The decoded MutationType column is GROUPED
# and its group sizes are 4 / 4 / 25 / 3 / 3 / 4 = 43, and the .rdata
# name->description block (file 0x08DD6D50 .. 0x08DD7D90) lines up with those
# groups exactly, with zero exceptions:
#   1-4   Carnivore ....... Hemomania, Hematophagy, Accelerated Prey Drive,
#                           Osteophagic
#   5-8   Herbivore ....... Xerocole Adaptation, Hypervigilance, Truculency,
#                           Photosynthetic Regeneration
#   9-33  Generic ......... 25 entries, incl. the 2 dev placeholders NHJ-INF/UND
#   34-36 CarnivoreExc .... Augmented Tapetum, Cannibalistic,
#                           Hypermetabolic Inanition
#   37-39 HerbivoreExc .... Barometric Sensitivity, Social Behavior,
#                           Tactile Endurance
#   40-43 GenericExc ...... Gastronomic Regeneration, Heightened Ghrelin,
#                           Prolific Reproduction, Parthenogenesis
# The carnivore side is CARNIVORE_ONLY above plus Cannibalistic (excluded from
# PICKABLE on purpose), and the herbivore side is HERBIVORE_ONLY plus the two
# names that are not PICKABLE — i.e. the binary reproduces this file's own
# hand-derived diet split name for name. A wrong offset could not do that.
#
# CORROBORATION, NEVER THE SOURCE: the only three enabled mutations with ZERO
# picks in 1,674 logged "Selected Mutation: [...]" rolls on LIN's own server
# (Osteophagic, Augmented Tapetum, Heightened Ghrelin) are all three in this
# set. The other four DO get picked (Multichambered Lungs 41, Reinforced Tendons
# 6, Reniculate Kidneys 4, Enhanced Digestion 2), which is consistent rather
# than contradictory: hidden does not mean nobody has it, it means it has to be
# earned before it rolls, and those players earned it.
#
# NO NAME IS UNCLASSIFIED, so nothing here is a guess: the flag is defined for
# all 43 registry entries and all 36 PICKABLE names are among them. If a future
# build ever adds a name this file cannot classify, it MUST be treated as NOT
# hidden — wrongly blocking a mutation denies a player something he is entitled
# to and gives him no way to tell why, which is the worse bug of the two.
HIDDEN: frozenset[str] = frozenset({
    "Osteophagic",            # registry  4  .text 0xF7E805
    "Enhanced Digestion",     # registry 26  .text 0xF7EEFC
    "Reinforced Tendons",     # registry 27  .text 0xF7EF3D
    "Reniculate Kidneys",     # registry 28  .text 0xF7EFA6
    "Multichambered Lungs",   # registry 29  .text 0xF7EFFB
    "Augmented Tapetum",      # registry 34  .text 0xF7F1A4
    "Heightened Ghrelin",     # registry 41  .text 0xF7F3F7
})

# ── which slots refuse the unlockable names ───────────────────────────────────
# Owner ruling 2026-07-27, verbatim: "slot 1 shouldnt have hidden mutations
# neither should slot 3. well for main slots. slot 2 and 4 can" — and, for the
# inherited families, "for elder mutations it should offer every mutation any
# slot".
#
# THE WHOLE RULE IS THIS ONE SET, so a re-ruling stays a one-line edit: put a
# slot id in to close it to the unlockables, take it out to open it. n2/n4 and
# all twelve inherited slots are absent, which is what "slot 2 and 4 can" and
# "every mutation any slot" mean.
#
# THIS IS STRICTER THAN THE GAME AND STRICTER THAN THE MOD, on purpose. It is a
# web-editor rule: the mod's own write path (validateMutationForSid) takes no
# slot argument and will happily put any of these in any slot, and parked rows
# are captured verbatim off live dinos that legitimately earned them. So it
# gates NEW WRITES ONLY and never wipes or hides a stored value — see
# validate_slot_edit.
HIDDEN_BLOCKED_SLOTS: frozenset[str] = frozenset({"n1", "n3"})

# The dino's OWN slots, in the order the editor numbers them ("Ranura 1".."4").
# Named once so the player-facing copy below is generated FROM
# HIDDEN_BLOCKED_SLOTS instead of restating it — change the set and every
# sentence follows.
_OWN_SLOT_ORDER: tuple[str, ...] = ("n1", "n2", "n3", "n4")
_FEM_ORDINAL: dict[int, str] = {1: "1ª", 2: "2ª", 3: "3ª", 4: "4ª"}

# Player-facing Spanish descriptions (the LIN site is Spanish end to end).
DESCRIPTIONS: dict[str, str] = {
    "Hemomania": "Inflige daño adicional a objetivos que están sangrando.",
    "Hematophagy": "Recupera algo de sed al comer.",
    "Accelerated Prey Drive": "Inflige más daño a animales con poca salud.",
    "Hypermetabolic Inanition": "Cuanta más hambre tienes, más daño infliges.",
    "Xerocole Adaptation": "Obtienes algo de agua al comer plantas.",
    "Photosynthetic Regeneration": "Regeneras estamina más rápido durante el día.",
    "Photosynthetic Tissue": "Regeneración pasiva de constantes bajo la luz del sol.",
    "Hypervigilance": "Ángulo de cámara más amplio mientras comes o bebes.",
    "Truculency": "Corcovear tiene más probabilidad de desmontar a animales enganchados.",
    "Osteophagic": "Consume huesos para regenerar fracturas más rápido.",
    "Cellular Regeneration": "Recuperas salud un poco más rápido.",
    "Advanced Gestation": "Gestación más rápida al anidar.",
    "Sustained Hydration": "Tu agua se agota más despacio.",
    "Enlarged Meniscus": "El daño por caída golpea la estamina antes que la salud.",
    "Efficient Digestion": "Tu comida se agota más despacio.",
    "Featherweight": "Tus huellas se desvanecen mucho más rápido.",
    "Osteosclerosis": "Resistes y reduces el daño por fracturas.",
    "Wader": "Menos impedimento al vadear aguas poco profundas.",
    "Epidermal Fibrosis": "Mayor resistencia al sangrado.",
    "Congenital Hypoalgesia": "Menos daño recibido al luchar contra especies más grandes.",
    "Nocturnal": "Visión mejorada durante la noche.",
    "Hydroregenerative": "Recuperas salud más rápido durante la lluvia.",
    "Increased Inspiratory Capacity": "Mayor capacidad de oxígeno.",
    "Hydrodynamic": "Mayor velocidad de nado.",
    "Submerged Optical Retention": "Mayor alcance de visión bajo el agua.",
    "Enhanced Digestion": "La nutrición decae más despacio.",
    "Reinforced Tendons": "Saltar cuesta menos estamina.",
    "Reniculate Kidneys": "Puedes beber agua salada.",
    "Multichambered Lungs": "Umbral de regeneración de estamina más bajo.",
    "Infrasound Communication": "Haces mucho menos ruido al usar el chat de voz.",
    "Sequential Hermaphroditism": "Cambia el sexo del modelo del personaje; no se hereda.",
    "Augmented Tapetum": "Visión nocturna muy mejorada.",
    "Tactile Endurance": "Convierte parte del daño recibido en pérdida de estamina.",
    "Heightened Ghrelin": "Capacidad de sobrealimentación muy aumentada.",
    "Prolific Reproduction": "Tus crías se regeneran más rápido, necesitan menos comida y crecen más rápido.",
    "Gastronomic Regeneration": "Comer restaura una pequeña cantidad de salud.",
    # The exe's own copy is "Allows the player to nest without a mate" — said
    # in the site's voice, like every line here.
    "Parthenogenesis": "Permite anidar sin pareja.",
    "Reabsorption": "Recuperas algo de agua cuando llueve o mientras nadas en agua potable.",
    "Barometric Sensitivity": "Recibes un aviso antes de las tormentas y las sequías.",
    "Social Behavior": "Aumenta el tamaño del grupo; solo aplica al líder del grupo.",
    "Cannibalistic": "Añade tu propia especie como presa preferida para nutrientes.",
}


def normalize_mutation_name(name: str) -> str:
    """"hemomania", "Hemo Mania", "HEMOMANIA" and "AcceleratedPreyDrive" all
    collapse to the same key (mirrors the mod's normKey: lowercase, strip
    spaces and underscores)."""
    return str(name or "").replace(" ", "").replace("_", "").strip().lower()


_NORM_TO_CANONICAL: dict[str, str] = {
    normalize_mutation_name(name): name for name in PICKABLE
}


def canonical_mutation_name(name: str) -> str | None:
    """Known-name lookup tolerant of spacing/underscore/camel-case drift.
    None when the name is not one of the 36 pickable mutations."""
    value = str(name or "").strip()
    if not value:
        return None
    return _NORM_TO_CANONICAL.get(normalize_mutation_name(value))


def dino_type(dino_class: str) -> str:
    if dino_class in CARNIVORES:
        return "carnivore"
    if dino_class in HERBIVORES:
        return "herbivore"
    if dino_class in GALLIMIMUS:
        return "gallimimus"
    return "unknown"


def restriction_for(mutation_name: str) -> str | None:
    if mutation_name in CARNIVORE_ONLY:
        return "carnivore"
    if mutation_name in HERBIVORE_ONLY:
        return "herbivore"
    return None


def allowed_names_for_class(dino_class: str) -> set[str]:
    dt = dino_type(dino_class)
    if dt == "carnivore":
        return set(GENERIC) | set(CARNIVORE_ONLY)
    if dt == "herbivore":
        return set(GENERIC) | set(HERBIVORE_ONLY)
    # gallimimus / unknown -> generic only
    return set(GENERIC)


def catalog_for_class(dino_class: str) -> list[dict]:
    """[{name, restriction, description}, ...] sorted by name, for the
    GET /me/vault/{id}/mutations response.

    DELIBERATELY THE FULL DIET-LEGAL LIST, hidden names included. It is what the
    editor looks a stored value up in to render its display name and its Spanish
    description, so a dino that already holds an unlockable in n1 keeps showing
    it properly. WHICH slot may be given which name travels separately, in
    slot_catalog_map."""
    return [
        {
            "name": name,
            "restriction": restriction_for(name),
            "description": DESCRIPTIONS.get(name, ""),
            # First-party, from the game's own bHasRequirement flag — see HIDDEN.
            #
            # THE WIRE NAME IS "unlockable", NOT "hidden", AND THAT IS LOAD
            # BEARING. Tailwind's scanner is a plain token pass over whole files
            # in web/frontend/src, comments and test titles included, and `hidden`
            # is a real utility (display:none) — so the bare word travelling into
            # the JSX that consumes this field would emit CSS on a JS-only change.
            # tailwind.config.js says so itself. Python is not scanned, so the
            # rule keeps the owner's own word (HIDDEN) on this side.
            "unlockable": name in HIDDEN,
        }
        for name in sorted(allowed_names_for_class(dino_class))
    ]


def is_hidden(name) -> bool:
    """True when `name` is one of the game's unlockable mutations.

    Goes through canonical_mutation_name, never a raw string compare, so
    spacing/underscore/camel-case drift ("AugmentedTapetum") and the catalog's
    "Enlarged Meniscus" vs the game's "Enlarged meniscus" can never miss. A name
    this catalog does not know is NOT hidden — unclassified always means
    offered."""
    canon = canonical_mutation_name(name)
    return canon is not None and canon in HIDDEN


def slot_allows_hidden(slot_id) -> bool:
    """May this slot be given an unlockable mutation?

    An unknown slot id answers True on purpose: validate_slot_edit's own slot-id
    check is what refuses those, and this rule must never become the thing that
    rejects an unrelated bad id with a message about unlockable mutations."""
    return not (isinstance(slot_id, str) and slot_id in HIDDEN_BLOCKED_SLOTS)


def allowed_names_for_slot(dino_class: str, slot_id: str) -> set[str]:
    """The names THIS slot will actually accept: diet-legal MINUS the
    unlockables when the slot is one the owner closed to them.

    The diet rule is unchanged and composes with this one — a herbivore's n1
    loses the 5 unlockables it could have carried, a carnivore's loses all 7."""
    names = allowed_names_for_class(dino_class)
    return names if slot_allows_hidden(slot_id) else names - HIDDEN


def _own_slots(allowed: bool) -> list[str]:
    """The own-slot ids that do / do not take the unlockables, read straight off
    HIDDEN_BLOCKED_SLOTS."""
    return [sid for sid in _OWN_SLOT_ORDER if slot_allows_hidden(sid) is allowed]


def _own_ordinals(allowed: bool) -> list[str]:
    """The same answer as the editor's own-slot numbers ("1ª", "3ª")."""
    return [_FEM_ORDINAL[_OWN_SLOT_ORDER.index(sid) + 1]
            for sid in _own_slots(allowed)]


def _own_requirement(slot_id: str) -> str:
    """What THIS own slot still asks for, in words, generated from the growth
    ladder: "50% de crecimiento", "75% de crecimiento y ser Prime".

    Reads _LADDER (defined further down, and only ever at call time) so the
    percent quoted is the DISPLAYED one slot_lock compares against — one number
    per rung on every surface. A slot that is not on the ladder has nothing to
    say and answers "", which the callers drop."""
    req = _LADDER.get(slot_id)
    if not req:
        return ""
    need_pct, need_prime = req
    parts = []
    if need_pct is not None:
        parts.append(f"{need_pct}% de crecimiento")
    if need_prime:
        parts.append("ser Prime")
    return " y ".join(parts)


# The twelve INHERITED slots as the copy names them: one label per FAMILY, never
# per slot. Every slot in a family sits on the same rung of ENTOMB_LADDER and
# gives the same answer to "would this take that name", so naming four of them
# would say one thing four times and turn a short sentence into a list of twelve.
# (prefix, "put it here", "these still need"). The prefix is matched against
# ENTOMB_LADDER at call time by _family_slots, so a family that gains or loses a
# slot follows on its own.
_INHERITED_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("p", "una heredada", "las heredadas"),
    ("ea", "una de Anciano A", "las de Anciano A"),
    ("eb", "una de Anciano B", "las de Anciano B"),
)


def _family_slots(prefix: str) -> list[str]:
    """The inherited slot ids of one family, read off ENTOMB_LADDER (defined
    further down, and only ever at call time) so the families are generated from
    the ladder rather than written down twice."""
    return [sid for sid, _need in ENTOMB_LADDER
            if sid.rstrip("0123456789") == prefix]


def _entomb_requirement(slot_id: str) -> str:
    """What an inherited family still asks for, in words, generated from the
    entomb ladder: "1 entierro", "3 entierros". A slot that is not on that ladder
    has nothing to say and answers "", which the callers drop."""
    need = _ENTOMB.get(slot_id)
    if not need:
        return ""
    return f"{need} {'entierro' if need == 1 else 'entierros'}"


def _join_es(items: list[str], sep: str, last: str) -> str:
    """Spanish list: "a", "a<last>b", "a<sep>b<last>c". Two destinations still
    read exactly as they always did ("la 2ª o en la 4ª")."""
    if len(items) < 2:
        return "".join(items)
    return sep.join(items[:-1]) + last + items[-1]


def _unlockable_destinations(row=None, names=None) -> tuple[list[str], list[str]]:
    """(what to call every destination THIS dino can write right now, [what each
    of the others still needs, in words] for the ones it cannot).

    A DESTINATION IS ANY SLOT THAT WOULD ACTUALLY TAKE THE NAME — own AND
    inherited. It used to be the two permitted OWN slots and nothing else, so a
    dino with n2 and n4 still closed was told "las ranuras que sí las admiten
    todavía no están disponibles en este dinosaurio" while its four heredadas sat
    open and validate_slot_edit accepted that very write: the same ruling that
    closed n1 and n3 opens all twelve inherited slots. The claim was false on
    every entombed dino that had not yet reached the 2nd rung.

    THE ADVICE HAS TO BE A MOVE THE PLAYER CAN MAKE. n2 wants 50% growth and n4
    wants 75% AND Prime, and the inherited families want entierros, so only the
    slots that are OPEN for this row are named — that rule is unchanged and now
    covers sixteen slots instead of four.

    `names` is what a destination has to accept; None means "any of the
    unlockables this species can carry", which is the picker notice's question,
    while the refusal passes the one name it just refused. Asked through
    allowed_names_for_slot, the same function validate_slot_edit's own rules are
    built from, so the copy cannot name a slot the POST would then refuse.

    row=None means "no lock information" (a caller with no row, and the older
    behaviour): every permitted destination is named. Never raises — slot_lock
    owns its own crash containment and fails closed, so an unreadable row simply
    reports every permitted destination as not-yet-available with what it
    needs."""
    known_class = isinstance(row, dict)
    cls = str(row.get("dino_class") or "") if known_class else ""
    want = set(HIDDEN) if names is None else set(names)
    open_, shut = [], []

    def _takes(sid: str) -> bool:
        # NO ROW MEANS NO SPECIES, and a diet test without a species is not a
        # weaker test, it is the WRONG one: the generic pool carries five of the
        # seven, so a carnivore-only name would come back "nowhere to put it"
        # from a caller that never claimed to know the dino. With a row it is the
        # real question, asked through the very function validate_slot_edit's own
        # rules are built from, so the copy cannot name a slot the POST refuses.
        if not known_class:
            return slot_allows_hidden(sid)
        return bool(want & allowed_names_for_slot(cls, sid))

    for sid in _OWN_SLOT_ORDER:
        if not _takes(sid):
            continue
        ordinal = _FEM_ORDINAL[_OWN_SLOT_ORDER.index(sid) + 1]
        if row is None or slot_lock(row, sid) is None:
            open_.append(f"la {ordinal}")
        else:
            need = _own_requirement(sid)
            if need:
                shut.append(f"la {ordinal} necesita {need}")
    for prefix, here, these in _INHERITED_FAMILIES:
        family = [sid for sid in _family_slots(prefix) if _takes(sid)]
        if not family:
            continue
        if row is None or any(slot_lock(row, sid) is None for sid in family):
            open_.append(here)
        else:
            need = _entomb_requirement(family[0])
            if need:
                shut.append(f"{these} necesitan {need}")
    return open_, shut


def _where_to_put_it(row, lead: str, names=None) -> str:
    """The advice half of both sentences below, so the two can never drift.

    Either "<lead> la 2ª o en la 4ª." when at least one destination is open, or —
    when none of them is — what each one still needs, which is a fact the player
    can act on instead of a move he cannot make. The second branch is the one
    that asserts nothing is available, so it may only ever be reached once every
    destination has been asked, inherited slots included. Neither branch says a
    slot opens by itself: a parked dino's growth, Prime and entierros are frozen
    at the moment it was stored, and stating a requirement is not a promise."""
    open_, shut = _unlockable_destinations(row, names)
    if open_:
        return f" {lead} " + _join_es(open_, ", en ", " o en ") + "."
    if shut:
        return (" Las ranuras que sí las admiten todavía no están disponibles "
                "en este dinosaurio: " + _join_es(shut, ", ", " y ") + ".")
    return ""


def _hidden_reason(canon: str, row=None) -> str:
    """The player-facing refusal. Generated from HIDDEN_BLOCKED_SLOTS and from
    the growth ladder so a re-ruling cannot leave the copy claiming the old
    slots — or offering a slot this dino cannot use (see _where_to_put_it).

    IT NEVER NAMES AN UNLOCK TASK. What a player has to do to earn most of these
    is not established anywhere we can stand behind (only two of the seven have
    a known threshold), so the copy says they are unlocked in game and stops
    there rather than inventing a requirement."""
    blocked = _own_ordinals(False)
    where = ("la " + " ni en la ".join(blocked)) if blocked else "esta"
    msg = (f"{canon} hay que desbloquearla jugando, y esas no se pueden poner "
           f"en {where} ranura propia.")
    # THE NAME GOES IN, so the advice is about the ranuras that would take THIS
    # mutation and not merely the ones that take unlockables in general.
    return msg + _where_to_put_it(row, "Ponla en", {canon})


def hidden_notice(row=None) -> str:
    """One sentence the editor shows on a slot whose list is shorter, so a
    player never has to wonder where a mutation went. Generated from the same
    set, and pointed at the same reachable slots, as the refusal."""
    blocked = _own_ordinals(False)
    where = ("la " + " y la ".join(blocked)) if blocked else "esta"
    msg = (f"Algunas mutaciones hay que desbloquearlas jugando y no se pueden "
           f"poner en {where} ranura propia, así que no salen en esta lista.")
    return msg + _where_to_put_it(row, "Sí puedes ponerlas en")


def hidden_kept_notice() -> str:
    """Shown when the slot the player has open ALREADY holds one of these.

    The row keeps it — this rule gates new writes only — so the copy has to say
    that plainly, and has to be honest that swapping it out is a one-way door on
    this particular slot. Emptying stays free, as it does on all sixteen."""
    return ("Esta ranura ya lleva una de esas mutaciones. Se queda donde está "
            "mientras tú no la toques, y quitarla sigue siendo gratis, pero si "
            "la cambias por otra ya no podrás volver a ponerla aquí.")


# ── slot model ────────────────────────────────────────────────────────────────
SLOT_IDS: tuple[str, ...] = (
    "n1", "n2", "n3", "n4",
    "p1", "p2", "p3", "p4",
    "ea1", "ea2", "ea3", "ea4",
    "eb1", "eb2", "eb3", "eb4",
)


def slot_catalog_map(dino_class: str) -> dict[str, list[str]]:
    """{slot_id: [name, ...]} for ALL SIXTEEN slots — the names each one will
    actually accept. The complete, self-describing model of the rule.

    NAMES ONLY. The restriction label and the Spanish description stay in the
    single shared `catalog` list and are looked up by name, so nothing carries
    sixteen copies of every description.

    THE SERVER STAYS THE ONE AUTHORITY. This exists so the UI can filter without
    knowing the rule; validate_slot_edit still refuses the write, and this map is
    derived from the very same allowed_names_for_slot it uses.

    NOT WHAT GOES ON THE WIRE — see slot_catalog_overrides."""
    full = sorted(allowed_names_for_class(dino_class))
    trimmed = [n for n in full if n not in HIDDEN]
    # A fresh list per slot: the response is read-only, but sharing one object
    # across fourteen keys is the kind of aliasing that bites a later caller.
    return {sid: list(full if slot_allows_hidden(sid) else trimmed)
            for sid in SLOT_IDS}


def slot_catalog_overrides(dino_class: str) -> dict[str, list[str]]:
    """The same answer, but carrying ONLY the slots whose list differs from the
    shared `catalog`. ABSENT MEANS "offers the full catalog".

    WHY SPARSE. Fourteen of the sixteen lists are identical to `catalog`, and to
    each other. Sending all sixteen put ~11 KB of duplicated names on every open
    of the editor, on a route with no gzip middleware in front of it; this is
    ~0.8 KB and says exactly the same thing.

    THE FALLBACK IS NOT NEW and is not a shortcut taken here: the editor already
    had to treat a missing entry as "offer everything", because an older server
    sends no such field at all, and erring OPEN is the only safe default —
    refusing names the server never refused would take a mutation away from a
    player who is entitled to it. This just uses the path that already existed.
    Three of the picker's tests pin it (no field, missing key, malformed value).
    """
    full = sorted(allowed_names_for_class(dino_class))
    return {sid: names for sid, names in slot_catalog_map(dino_class).items()
            if names != full}


# THE ELDER COLUMN IS INTERLEAVED. DO NOT "TIDY" IT BACK TO BLOCKS.
#
# elder_mutations is 8 positional segments in the order
#   1A, 1B, 2A, 2B, 3A, 3B, 4A, 4B
# so ea{N} is segment 2*(N-1) and eb{N} is segment 2*(N-1)+1. That is not a
# convention this file gets to choose: the mod is the only decoder that reaches
# the game, and it walks `for i = 1,4 do for suffix in {"A","B"}`. Five
# independent mod sites agree, all in
# mod/lua/LaIslaNublarDataMod/Scripts/main.full.lua:
#   :197-202   LAISLANUBLAR_MUTATION_ELDER_SLOT_NAMES, literally 1A,1B,2A,2B,...
#   :437-443   entomb-diag capture,  c[(i-1)*2+si]
#   :7679-7694 ApplyElderMutations, the SOLE game-facing decoder
#   :11549-11555 propFor: ea{N} -> ElderMutationSlot{N}A, eb{N} -> {N}B
#   :14420-14428 rich telemetry capture, eparts[(i-1)*2+si]
# (plus the entomb target/guard builders at :2959-2960, :2989-2990, :3074-3075,
# which use ai=(i-1)*2+1, bi=ai+1.)
#
# Until 2026-07-26 this map was BLOCKED (ea -> segments 0-3, eb -> 4-7), so six
# of the eight labels resolved to a different game property than they claimed
# (writing "Anciano 2A" landed in ElderMutationSlot1B). It was harmless only
# because the UI hid every elder slot. STORED ROWS WERE NEVER WRONG — the mod
# wrote and read them interleaved throughout — so this is a label fix, not a
# data migration.
#
# slot -> (parked_dinos column, 0-based segment index, segment count)
_SLOT_MAP: dict[str, tuple[str, int, int]] = {}
for _i in range(4):
    _SLOT_MAP[f"n{_i + 1}"] = ("mutations", _i, 4)
    _SLOT_MAP[f"p{_i + 1}"] = ("parent_mutations", _i, 4)
    _SLOT_MAP[f"ea{_i + 1}"] = ("elder_mutations", _i * 2, 8)
    _SLOT_MAP[f"eb{_i + 1}"] = ("elder_mutations", _i * 2 + 1, 8)

# The game property each elder segment IS, derived from the same rule, so any
# other lane that needs the order reads it from here instead of re-deriving it.
ELDER_SEGMENT_PROPERTIES: tuple[str, ...] = tuple(
    prop for _n in range(1, 5)
    for prop in (f"ElderMutationSlot{_n}A", f"ElderMutationSlot{_n}B")
)


def split_segments(raw: str, count: int) -> list[str]:
    """"Titan|None|Feral" -> exactly `count` segments, blanks -> "None"."""
    parts = [p.strip() for p in str(raw or "").split("|")]
    out = []
    for i in range(count):
        v = parts[i] if i < len(parts) else ""
        out.append(v if v and v.lower() != "none" else "None")
    return out


def join_segments(parts: list[str]) -> str:
    return "|".join(parts)


def slots_from_row(row: dict) -> dict[str, str]:
    """Parked row -> {slot_id: raw value or "None"} for all 16 slots."""
    cols = {
        "mutations": split_segments(row.get("mutations"), 4),
        "parent_mutations": split_segments(row.get("parent_mutations"), 4),
        "elder_mutations": split_segments(row.get("elder_mutations"), 8),
    }
    return {sid: cols[col][idx] for sid, (col, idx, _n) in _SLOT_MAP.items()}


def slot_column(slot_id: str) -> tuple[str, int, int] | None:
    """slot id -> (column, segment index, segment count), None if unknown."""
    return _SLOT_MAP.get(slot_id)


def elder_segments_from_sets(set_a, set_b) -> list[str]:
    """An "A" set and a "B" set of up to 4 picks each -> the 8 elder segments,
    INTERLEAVED the way the mod reads them (see _SLOT_MAP).

    THE ONE PLACE any non-mod writer builds that column. server.py's
    inventory -> vault deploy used to concatenate the four A's then the four
    B's, which put a "Set A" pick into ElderMutationSlot1A/1B/2A/2B instead of
    1A/2A/3A/4A. Both writers now index through _SLOT_MAP, so they cannot drift
    apart again. Anything unreadable becomes "None" rather than raising."""
    out = ["None"] * 8
    for prefix, picks in (("ea", set_a), ("eb", set_b)):
        for i, value in enumerate(list(picks or [])[:4]):
            v = str(value or "").strip()
            out[_SLOT_MAP[f"{prefix}{i + 1}"][1]] = v if v and v.lower() != "none" else "None"
    return out


# ── growth / Prime ladder on the dino's OWN slots (n1..n4) ────────────────────
# Owner ruling 2026-07-25, verbatim: "25% first mut only. 50% first and second.
# 75% first second and third, and if prime and at 75% then first, second, third,
# and fourth. if not prime no fourth."
#
# These percentages are the OWNER'S server rule, NOT a game constant — no source
# states them (the game only names juvenile / sub-adult / adult stages), so they
# live here as data and a re-ruling is a one-line edit.
#
# UNITS: growth on a parked_dinos row is a FRACTION 0..1 (bot/database.py
# declares `growth REAL`, vault._dino_view publishes growth_pct = growth*100,
# vault.PARK_MIN_GROWTH is 0.25), so the rungs are 25 / 50 / 75 PERCENT.
#
# SCOPE: only n1..n4. Inherited (p1..p4) and elder (ea*/eb*) slots are NOT on
# this ladder — they come from nesting and entombing, not from growth, and the
# ruling says nothing about them. They stay exactly as open as they were.
#
# GROWTH IS FROZEN once a dino is parked: every UPDATE against parked_dinos
# writes only redeem_pending_*, custom_name or the three mutation columns —
# growth is written once, at INSERT (vault.park). So a slot the ladder closes
# does NOT open by itself over time; the player has to redeem the dino, grow it
# in game and park it again. Every player-facing string about a closed slot has
# to say that, never "it will open on its own".
GROWTH_LADDER: tuple[tuple[str, float, bool], ...] = (
    # (slot id, growth fraction required, Prime required)
    ("n1", 0.25, False),
    ("n2", 0.50, False),
    ("n3", 0.75, False),
    ("n4", 0.75, True),
)


# ── entomb ladder on the twelve INHERITED slots ───────────────────────────────
# Owner ruling 2026-07-26, verbatim: "if they entomb once then they can edit 4
# elder slots, if twice then 8, if 3 times then 12".
#
# LIN stores exactly twelve inherited slots in three families, and the game
# exposes only EIGHT elder properties, so 4/8/12 can only be
# parent -> elder A -> elder B. The mod's own entomb cascade walks that same
# generational order in lineage_shift mode (main.full.lua ~:2948-2984:
# MutationSlot(i) -> ParentMutationSlot(i) -> ElderMutationSlot(i)A, with
# ElderMutationSlot(i)B preserved).
#
# THIS REPLACES the 2026-07-12 ruling ("even if they arent entombed its fine it
# works") that the removed elder_set_unlocked encoded as an unconditional True.
#
# LIKE GROWTH, elder_stacks IS FROZEN once a dino is parked: it is written once,
# at INSERT (vault.save_parked); every UPDATE against parked_dinos touches only
# redeem_pending_*, custom_name or the three mutation columns. So a slot this
# ladder closes does NOT open by itself over time — the player has to redeem the
# dino, entomb it in game and park it again. No player-facing string may say
# otherwise.
#
# SCOPE: only p*/ea*/eb*. The own slots stay on GROWTH_LADDER and are NOT gated
# on entombs; these twelve are gated on entombs ONLY and never on growth.
ENTOMB_LADDER: tuple[tuple[str, int], ...] = (
    # (slot id, entombs the dino must already have)
    ("p1", 1), ("p2", 1), ("p3", 1), ("p4", 1),
    ("ea1", 2), ("ea2", 2), ("ea3", 2), ("ea4", 2),
    ("eb1", 3), ("eb2", 3), ("eb3", 3), ("eb4", 3),
)
_ENTOMB: dict[str, int] = dict(ENTOMB_LADDER)

LOCK_ENTOMB_UNREADABLE = (
    "No se pudo leer cuántas veces se ha enterrado a este dinosaurio, así que "
    "la ranura queda bloqueada. Vuelve a guardarlo en la bóveda o avisa a un "
    "admin.")


def _entomb_reason(need: int, have: int) -> str:
    veces = "vez" if need == 1 else "veces"
    return (f"Se desbloquea cuando el dinosaurio ha sido enterrado al menos "
            f"{need} {veces} (ahora: {have}).")


_INF = float("inf")


def elder_stack_count(row: dict) -> int | None:
    """The row's entomb count as a whole number >= 0, or None when it cannot be
    trusted.

    None is the FAIL-CLOSED signal: a missing, blank, non-numeric, negative,
    fractional or bool elder_stacks LOCKS all twelve inherited slots instead of
    opening them. Parsed the way is_prime_flag parses its own column, and for
    the same reason — the column is INTEGER in the bot schema but a TEXT-typed
    column or a JSON round trip hands back "2" or even "2.0", and int("2.0")
    raises. Never raises; pure and allocation-free on the integer path."""
    raw = row.get("elder_stacks") if isinstance(row, dict) else None
    if raw is None or isinstance(raw, bool):
        # A bool is not a count. True must never read as "1 entomb".
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        try:
            raw = bytes(raw).decode("utf-8", "ignore")
        except Exception:
            return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            n = float(raw)
        except (TypeError, ValueError, OverflowError):
            return None
    elif isinstance(raw, float):
        n = raw
    else:
        return None                       # list / dict / object: unreadable
    if n != n or n == _INF or n == -_INF:  # NaN / ±inf (float("1e400") is inf)
        return None
    if n < 0.0:
        return None
    try:
        whole = int(n)
    except (ValueError, OverflowError):
        return None
    # 1.5 entombs is not a thing. Refuse to guess which side of it the player
    # is on — lock, the same as any other unreadable value.
    return whole if whole == n else None


# ── the generation a row's own PARENT column already proves ───────────────────
# THE PARENT COLUMN AND NOTHING ELSE, AND NEVER PAST GENERATION 1.
#
# The elder column is NOT proof of anything and is deliberately never read here.
# The mod's FIRST entomb does not shift a generation, it FLATTENS:
# LaIslaNublarRedeemedEntombBuildTarget (main.full.lua :2935-3016) picks
# layoutMode = "first_entomb_flatten" whenever the elder column is still empty,
# and that branch writes the dino's OWN mutations into ElderMutationSlot{i}A and
# its PARENT ones into {i}B (mapped[ai]=n, mapped[bi]=p), leaves parentTarget
# entirely "None", and sets ElderReplicationStacks to 1. So elder content means
# ONE entomb, not two and not three. Reading elder A as generation 2 and elder B
# as 3 handed EVERY genuinely entombed dino all twelve slots — measured against
# a python port of BuildTarget: entombed once -> 12 open where ENTOMB_LADDER
# grants 4, entombed twice -> 12 where it grants 8. That is the 4/8/12 ruling
# this module exists to enforce, read as 12/12/12.
#
# The parent column carries no such trap, in either direction the mod can write
# it:
#   * right after the FIRST entomb it is EMPTY (the flatten branch never assigns
#     parentTarget), so a once-entombed dino proves 0 here and keeps exactly the
#     four slots the ladder gives it;
#   * from the SECOND entomb on, the lineage_shift branch fills it
#     (parentTarget[i] = the dino's own mutations) while the recorded counter is
#     already >= 2 — and 2 > 1, so max() no-ops and nothing widens.
# The derivation therefore CANNOT exceed the ladder on any row parked off a dino
# the game entombed.
#
# WHAT IT IS FOR: rows the SITE ITSELF built. /store/purchase-dino fills
# parent_mutations straight from the "Linaje Parental" picker the player just
# paid at, and stores no entomb count at all, so every one of those rows sits at
# elder_stacks 0 — four PAID mutations in four slots the ladder locks, with only
# the free (and unwalkable-back) "Quitar" left on them. A nest-inherited parent
# column reads the same way and gets the same four slots. That is the whole
# widening: four slots, on a family that already holds mutations the dino
# carries.
MAX_DERIVED_GENERATION = 1   # parent family only. NEVER raise this to reach the
                             # elder families — see the flatten note above.

# The one column a stored value may be read as proof of a lineage step. Named
# once so the memo, the derivation and slot_clear_closes cannot drift apart.
_LINEAGE_COLUMN = "parent_mutations"


def _proves_lineage(segment: str) -> bool:
    """Does ONE stored segment prove the row went through a lineage step?

    A RECOGNISED MUTATION, not merely a non-empty segment. split_segments folds
    ""/"none"/"None" down to the literal "None", but it passes everything else
    through verbatim — "0", "null", "-", "n/a", a truncated name, a stray
    fragment of some other column — and on a `!= "None"` test every one of those
    would open four paid slots on a row whose column is simply corrupt. This
    module fails closed everywhere else (see is_prime_flag's allowlist, which
    exists because a DENYLIST handed the Prime-only slot to every value it had
    not heard of), so proof is an allowlist too: the segment has to resolve
    through canonical_mutation_name to one of the 36 catalog names, camel-case
    and spacing drift included ("AcceleratedPreyDrive" counts).

    THE COST, accepted on purpose: a mod-known name this catalog does not pick
    from — "Cannibalistic", "Traumatic Thrombosis" (see the mod-parity block in
    tests_local/test_vault_mutation_edit.py) — does NOT prove a generation. That
    is the conservative side and it takes nothing away that the player could
    have used: validate_slot_edit refuses to write such a name into any slot, so
    opening the family around it would only hand him a slot he cannot put back
    what was in it. And nothing the SITE itself delivers can miss, because both
    lanes that build a parked row canonicalize through canonical_mutation_name
    before they write (server.py _store_mutation_segments and the inventory ->
    vault move)."""
    return canonical_mutation_name(segment) is not None


# Memoised on the COLUMN STRING, never on the row: slot_lock asks for this once
# per slot and the GET walks all 16, so a row would otherwise be re-split sixteen
# times per request. The argument is forced to str by the wrapper below before it
# ever reaches the cache, so an unhashable list/dict row value can never raise
# TypeError out of lru_cache. Nothing here mutates or holds a reference to the
# caller's row — the key is the plain "|"-string sqlite hands back, and the cache
# is bounded.
@lru_cache(maxsize=512)
def _lineage_generation_cached(parent_mutations: str) -> int:
    segs = split_segments(parent_mutations, 4)
    for sid, need in ENTOMB_LADDER:
        if need > MAX_DERIVED_GENERATION:
            break                          # elder families are never proof
        col, idx, _n = _SLOT_MAP[sid]
        if col == _LINEAGE_COLUMN and _proves_lineage(segs[idx]):
            return need
    return 0


def lineage_generation(parent_mutations=None) -> int:
    """0 or 1 — the entomb generation the row's PARENT column itself proves.

    1 when any of its four segments is a recognised mutation, 0 otherwise. It
    takes no elder column ON PURPOSE: the mod's first entomb writes the dino's
    own and parent mutations INTO the elder column (first_entomb_flatten, see the
    block above), so elder content proves one entomb, not two or three, and
    reading it as a generation handed every entombed dino all twelve slots.

    Anything unreadable (None, a non-string, a short string, a segment that is
    not a recognised mutation) counts as EMPTY, so the answer can only ever be a
    floor and never an inflated claim. Never raises."""
    return _lineage_generation_cached(
        parent_mutations if isinstance(parent_mutations, str) else "")


def _entomb_state(row) -> tuple[int, int | None]:
    """(entomb count THE LOCK USES, the RECORDED count or None) — the ONE place
    the inherited ladder learns how far up a row is, so slot_lock, slot_lock_map,
    unlocked_slots, validate_slot_edit and the GET can never disagree.

    THE COUNT IS max(recorded elder_stacks, lineage_generation(parent column)).
    A row whose parent column already holds a real mutation has PROVEN that
    lineage step, whatever the counter says: every row the SITE built landed at
    elder_stacks 0 (neither web lane has an entomb number to store), so a player
    who bought a dino with a "Linaje Parental" was being told the four parent
    mutations he had just paid for were locked until the dino had been entombed.

    IT ONLY EVER RAISES THE COUNT. max(), never min() — a row recorded at 3 with
    empty columns stays 3 — and it can never raise it past
    MAX_DERIVED_GENERATION, so it cannot outrun the ladder on a dino the game
    really did entomb.

    READ-TIME, DELIBERATELY NOT A BACKFILL. elder_stacks is also consumed by the
    redeem lane (vault._run_redeem hands it to the mod, which writes
    ElderReplicationStacks), so rewriting the stored counter would change what
    the GAME receives on redeem — a behaviour change nobody asked for and one
    that cannot be undone. Deriving it here changes only what the EDITOR permits;
    the stored value, and everything the redeem sends, are untouched.

    THE TWO NUMBERS ARE RETURNED SEPARATELY BECAUSE THEY MEAN DIFFERENT THINGS.
    The first opens slots. The second is the only one a player may ever be shown:
    it is how many times the dino was actually buried, and a derived 1 printed as
    "ahora: 1" on a dino nobody ever buried is simply a lie. None means the stored
    counter is unreadable, which gets its own copy rather than a fabricated 0.

    FAIL CLOSED both halves: an unreadable elder_stacks contributes 0 to the
    count, and an unreadable/unrecognised column contributes 0. Never raises —
    every helper it calls promises the same."""
    recorded = elder_stack_count(row)
    proven = (lineage_generation(row.get(_LINEAGE_COLUMN))
              if isinstance(row, dict) else 0)
    have = 0 if recorded is None else recorded
    return (have if have >= proven else proven), recorded


def effective_elder_stacks(row) -> int:
    """The entomb count the LOCK uses — max(recorded, what the parent column
    proves). Never raises; 0 when nothing is readable and nothing is proven.

    NOT WHAT THE GET PUBLISHES, and never printed at a player. It can sit one
    above the truth (a store dino that was never buried proves 1), and
    "tu dino: 1 entierro" on a dino nobody ever buried is a lie the site must not
    tell. The GET publishes elder_stack_count — the RECORDED number — and lets
    slot_locks carry which slots are open. This exists so a caller that needs the
    gate's own number reads it from the same place slot_lock does instead of
    re-deriving it."""
    have, _recorded = _entomb_state(row)
    return have


def slot_clear_closes(row: dict, slot_id: str) -> bool:
    """Would emptying this slot CLOSE slots that are open only because this row's
    parent column proved the lineage?

    Emptying is always allowed and always free — that never changes. But on a row
    whose four heredadas are open ONLY because one of them holds a mutation, the
    free one-press "Quitar" on that last one takes the proof away with it and
    shuts the whole family, and nothing can put it back: the ladder then refuses
    every write until the dino is entombed in game. Before the derivation existed
    those slots were LOCKED, so that same press went down the guarded two-press
    path with its warning; the derivation moved the irreversible case into the
    UNGUARDED one. This is what hands the UI back the guard, per slot.

    True only for a slot that is genuinely in that position: inherited, currently
    OPEN, holding a recognised mutation, and the last piece of proof the row has.
    A row whose recorded counter already carries the family answers False (the
    counter survives any clear), and so does a family with a second recognised
    mutation still in it. Never raises; when it cannot tell, it warns."""
    try:
        if not isinstance(slot_id, str) or slot_id not in _ENTOMB:
            return False                      # own slots are not on this ladder
        col, idx, count = _SLOT_MAP[slot_id]
        have, recorded = _entomb_state(row)
        floor = 0 if recorded is None else recorded
        if have <= floor:
            return False                      # the stored counter carries it
        if have < _ENTOMB[slot_id]:
            return False                      # the slot is locked anyway
        if col != _LINEAGE_COLUMN:
            return False                      # nothing else is ever proof
        segs = split_segments(row.get(col) if isinstance(row, dict) else None, count)
        if not _proves_lineage(segs[idx]):
            return False                      # this slot proves nothing itself
        segs[idx] = "None"                    # a COPY — the caller's row is not touched
        return max(floor, lineage_generation(join_segments(segs))) < have
    except Exception:                         # noqa: BLE001 - never 500 the editor
        _log.exception("[mutations] slot_clear_closes failed slot=%r", slot_id)
        # Cannot tell -> warn. One extra press costs nothing; a missing warning
        # costs a mutation the player paid for.
        return isinstance(slot_id, str) and slot_id in _ENTOMB


def growth_display_pct(growth: float | None) -> int | None:
    """A growth fraction -> the whole percent THE SITE SHOWS for it.

    ONE number on the two surfaces that sit on the same screen: the vault card
    (vault._dino_view publishes `growth_pct` straight from this helper — it kept
    its own inline copy of the arithmetic until 2026-07-27, which is also how it
    came to raise on a NaN the helper had always answered None for — and the card
    and the preview header above the editor both render it) and this editor. Truncating with int() instead made 0.58 read "58%" on the card and
    "57%" in the editor legend a few pixels below it, and refused the 75% rung
    to a dino whose own card said 75% (0.7499). Anything that needs a displayed
    growth percent for a PARKED dino calls this. (A live dino's growth on
    /mydino is a different, moving number published by a different route — see
    the note in docs/FEATURES.md; it is deliberately not on this helper.)

    None in -> None out: an unreadable growth has no percent to show, and
    slot_lock's fail-closed branch is what answers for it.

    NEVER RAISES, and that is a contract its callers lean on: server.py reads it
    OUTSIDE the try/except that wraps the rest of the mutations GET, so anything
    that escapes here 500s the editor instead of locking a slot. int(round(x))
    raises OverflowError — not ValueError — on ±infinity, and float() raises it
    on an int too big for a double (10**400), so both are caught and every
    non-finite value answers None, the same as an unreadable growth."""
    if growth is None:
        return None
    try:
        g = float(growth)
    except (TypeError, ValueError, OverflowError):
        return None
    # NaN and ±infinity have no percent to show. Checked BEFORE the multiply so
    # the answer is None (fail closed) rather than an exception out of round().
    if g != g or g == _INF or g == -_INF:
        return None
    try:
        pct = g * 100.0
        if pct != pct or pct == _INF or pct == -_INF:   # 1e307 * 100 -> inf
            return None
        return int(round(pct))
    except (TypeError, ValueError, OverflowError):
        return None


# slot -> (required DISPLAYED percent, Prime required). The rung is stored as
# the integer percent the site shows because that is what it is compared
# against — see slot_lock.
_LADDER: dict[str, tuple[int, bool]] = {
    sid: (growth_display_pct(need), prime) for sid, need, prime in GROWTH_LADDER
}

# Growth above this is out of contract (a writer that stored 75 instead of
# 0.75). Refuse to guess the unit — lock, never unlock on a value we cannot
# read. The headroom covers float noise on a full-grown 1.0.
_GROWTH_MAX = 1.001

LOCK_PRIME = "La cuarta mutación propia es solo para dinosaurios Prime."
LOCK_UNREADABLE = (
    "No se pudo leer el crecimiento de este dinosaurio, así que la ranura "
    "queda bloqueada. Vuelve a guardarlo en la bóveda o avisa a un admin.")

# The TEXT values a TEXT-typed / JSON-round-tripped is_prime can arrive as
# MEANING TRUE. Python's bool("0") is True, so this flag is parsed, never
# bool()'d — see is_prime_flag.
#
# THIS IS AN ALLOWLIST, ON PURPOSE. A denylist of falsey words ("0", "false",
# ...) hands the Prime-only fourth slot to every value it does not recognise —
# "0.00", "00", "-0", "0e0", b"0" and plain "abc" all read as Prime — which is
# the one fail-OPEN branch in a module that fails closed everywhere else.
# Unrecognised must mean NOT Prime.
#
# The set covers what this codebase actually writes and round-trips:
#   1 / 0          vault.park and bot/database.py store INTEGER (`1 if ... else 0`)
#   True / False   bot/dino.py builds the row with bool(prime)
#   "true"/"false" the mod's own JSON and pipe payloads (main.full.lua uses
#                  tostring(p.is_prime == true)), and Python's str(True) once
#                  lowercased
#   "1" / "1.0"    the same INTEGER/REAL read back out of a TEXT-typed column
# plus the short/Spanish affirmatives an admin or an env override may type by
# hand. Every one of them is a form that GENUINELY means true.
_TRUTHY_TEXT = frozenset({"1", "1.0", "true", "t", "yes", "y", "on", "si", "sí"})


def growth_fraction(row: dict) -> float | None:
    """Parked-row growth as a FRACTION 0..1, or None when it cannot be trusted.

    None is the FAIL-CLOSED signal: a missing, blank, non-numeric, NaN or
    out-of-range growth LOCKS every gated slot instead of opening them. Pure,
    allocation-free on the numeric path, never raises."""
    raw = row.get("growth") if isinstance(row, dict) else None
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
    try:
        g = float(raw)
    except (TypeError, ValueError, OverflowError):
        # OverflowError is float()'s answer to an int too big for a double
        # (10**400). Without it this function raised out of a docstring that
        # promises it never does, and slot_lock's catch-all logged a traceback
        # per call for what is just another unreadable growth.
        return None
    if g != g:                      # NaN
        return None
    if g < 0.0 or g > _GROWTH_MAX:  # negative / infinite / percent-scaled
        return None
    return 1.0 if g > 1.0 else g


def is_prime_flag(row: dict) -> bool:
    """Truth of the row's is_prime column. It is INTEGER 0/1 in the bot schema,
    but a TEXT-typed column or a JSON round-trip hands back "0"/"false" — and
    bool("0") is True in Python, which would hand a non-Prime the fourth slot.
    Anything unreadable is False (fail closed). Never raises.

    Fail-closed means the TEXT test is an ALLOWLIST (_TRUTHY_TEXT): a value this
    function does not recognise is NOT Prime. The bytes case is spelled out
    rather than left to str(), because str(b"0") is "b'0'" — a string that
    matches nothing and, under the old denylist, opened the fourth slot."""
    raw = row.get("is_prime") if isinstance(row, dict) else None
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw == raw and raw != 0   # NaN -> False
    if isinstance(raw, (bytes, bytearray, memoryview)):
        try:
            raw = bytes(raw).decode("utf-8", "ignore")
        except Exception:
            return False
    if not isinstance(raw, str):
        return False                     # list / dict / object: unreadable
    return raw.strip().lower() in _TRUTHY_TEXT


def slot_lock(row: dict, slot_id: str) -> tuple[str, str] | None:
    """(code, plain-Spanish reason) when `slot_id` is LOCKED for this row, or
    None when the slot is open.

    codes: "prime" | "growth" | "growth_unknown"   (own slots, GROWTH_LADDER)
           "entomb" | "entomb_unknown"             (inherited, ENTOMB_LADDER)

    ONE answer per slot, from one function: the own slots are gated on growth
    and Prime, the twelve inherited ones on the entomb count, and nothing is on
    both ladders.

    Pure and allocation-free on the open path — this runs on every GET across
    16 slots and on every POST — the Spanish string is only built for a slot
    that is actually locked. Never raises: a malformed row locks the gated slots
    instead of 500ing the editor."""
    try:
        on_ladder = isinstance(slot_id, str)
        req = _LADDER.get(slot_id) if on_ladder else None
        if req is None:
            need = _ENTOMB.get(slot_id) if on_ladder else None
            if need is None:
                return None                   # not a gated slot id at all
            # ONE read of the count, from _entomb_state, which is where the
            # stored counter and the generation the row's own parent column
            # proves are reconciled. Nothing else on this path may consult
            # elder_stacks directly, or the two would drift.
            have, recorded = _entomb_state(row)
            if have >= need:
                # Open. A slot the parent column itself proved is simply open —
                # there is no reason to show and nothing for the player to do.
                return None
            if recorded is None:
                # Still short, and the stored counter is junk: say so, rather
                # than quote a floor as if it were the real count.
                return ("entomb_unknown", LOCK_ENTOMB_UNREADABLE)
            # THE RECORDED COUNT, NOT THE DERIVED ONE. This sentence claims how
            # many times the dino was BURIED, so it may only ever carry the
            # number that is true of the dino: a store row that proves 1 from a
            # parent pick was still never buried, and "(ahora: 1)" on it would be
            # a lie the player can neither check nor act on.
            return ("entomb", _entomb_reason(need, recorded))
        need_pct, need_prime = req
        if need_prime and not is_prime_flag(row):
            return ("prime", LOCK_PRIME)
        # THE COMPARISON IS AGAINST THE DISPLAYED PERCENT, not the raw fraction:
        # the site tells this player his dino is at N%, so N% is what the rung
        # has to be measured against. A dino whose card says 75% gets the 75%
        # rung. (This is a hair wider than a raw-fraction test — at most half a
        # percentage point, exactly the width of the rounding the site already
        # does — and it widens nothing else: Prime is still Prime, and an
        # unreadable growth still locks every rung below.)
        shown_pct = growth_display_pct(growth_fraction(row))
        if shown_pct is None:
            return ("growth_unknown", LOCK_UNREADABLE)
        if shown_pct < need_pct:
            return ("growth",
                    f"Se desbloquea al {need_pct}% de crecimiento "
                    f"(ahora: {shown_pct}%).")
        return None
    except Exception:
        _log.exception("[mutations] slot_lock failed slot=%r", slot_id)
        # Fail closed, and with the reason that belongs to THIS slot's ladder —
        # an inherited slot must never be handed the growth copy.
        if isinstance(slot_id, str) and slot_id in _ENTOMB:
            return ("entomb_unknown", LOCK_ENTOMB_UNREADABLE)
        return ("growth_unknown", LOCK_UNREADABLE)


def slot_unlocked(row: dict, slot_id: str) -> bool:
    """True when a mutation may be WRITTEN into this slot. Clearing a slot is
    always allowed regardless — see validate_slot_edit."""
    return slot_lock(row, slot_id) is None


def unlocked_slots(row: dict) -> frozenset[str]:
    """Every slot id this row may currently write a mutation into."""
    return frozenset(sid for sid in SLOT_IDS if slot_lock(row, sid) is None)


def growth_ladder_view() -> list[dict]:
    """The ladder as data for the UI, so the site states one rule from one
    source. [{slot, index, requires_growth_pct, requires_prime}, ...]"""
    return [
        {"slot": sid, "index": i + 1,
         "requires_growth_pct": growth_display_pct(need),
         "requires_prime": bool(prime)}
        for i, (sid, need, prime) in enumerate(GROWTH_LADDER)
    ]


def entomb_ladder_view() -> list[dict]:
    """The entomb ladder as data for the UI, so the site states one rule from
    one source. [{slot, generation, requires_entombs}, ...] — `generation` is
    1 for the parent family, 2 for elder A, 3 for elder B, which is also the
    number of entombs each needs."""
    return [
        {"slot": sid, "generation": need, "requires_entombs": need}
        for sid, need in ENTOMB_LADDER
    ]


def _restore_blocked(slot_id: str, stored: str, allowed_names: set[str],
                     locked: bool, closes: bool) -> bool:
    """Could the value THIS slot holds be written back into THIS slot after it is
    GONE FROM IT? False when it could; True when it could not.

    THE CALLER SAYS HOW IT GOES: `closes` is the caller's answer to "does the
    action I am asking about shut this slot", and it is the ONE term that differs
    between the two ways a stored value is destroyed. Emptying the last-proof
    heredada shuts its whole family (slot_clear_closes), so nothing goes back in;
    OVERWRITING it does not, because every value the POST accepts is a recognised
    catalog name and a recognised name is exactly what proves the lineage
    (_proves_lineage), so the family stays open and the old value can be bought
    back. Pass the closes flag for a clear and False for an overwrite — see
    clear_blocks_restore / overwrite_blocks_restore, which is where those two
    questions are named.

    Pure, and takes everything it needs so slot_lock_map can answer for sixteen
    slots without asking any rule twice — the lock and the closes flag are
    already in its hand, and re-deriving them there re-parsed the row's own
    lineage column.

    Every way the answer can be no, in the order they cost:
      * the slot is LOCKED, or the action CLOSES it (the last-proof heredada
        being emptied): the ladder refuses every write into it afterwards;
      * the stored value is not one of the 36 catalog names at all — a legacy or
        staff-granted capture. validate_slot_edit refuses those everywhere;
      * the species cannot carry it (diet), or this particular slot will not be
        given it (the unlockable rule on n1/n3).

    THE DUPLICATE RULE IS DELIBERATELY NOT IN THAT LIST. A row holding the same
    name twice makes the re-add a duplicate, but that is walk-back-able — empty
    the other copy and it goes right back — so warning "you will never put this
    back" over it would be a promise this module cannot keep. What this answers
    is the durable question: will this RANURA ever take this NAME again."""
    if not stored or stored == "None":
        return False                      # nothing to lose
    if locked or closes:
        return True
    canon = canonical_mutation_name(stored)
    if canon is None or canon not in allowed_names:
        return True
    return canon in HIDDEN and not slot_allows_hidden(slot_id)


def _blocks_restore(row, slot_id, on_clear: bool) -> bool:
    """The shared body of the two questions below, so the rule is stated once and
    the pair cannot drift. `on_clear` chooses which action is being asked about;
    everything else is identical.

    Never raises; when it cannot tell, it warns — one extra press costs nothing,
    a missing warning costs a mutation the player cannot get back."""
    try:
        if not isinstance(slot_id, str) or slot_id not in _SLOT_MAP:
            return False
        stored = slots_from_row(row)[slot_id] if isinstance(row, dict) else "None"
        if not stored or stored == "None":
            return False
        cls = str(row.get("dino_class") or "") if isinstance(row, dict) else ""
        return _restore_blocked(
            slot_id, stored, allowed_names_for_class(cls),
            slot_lock(row, slot_id) is not None,
            bool(on_clear) and slot_clear_closes(row, slot_id))
    except Exception:                     # noqa: BLE001 - never 500 the editor
        _log.exception("[mutations] _blocks_restore failed slot=%r clear=%r",
                       slot_id, on_clear)
        return True


def clear_blocks_restore(row, slot_id) -> bool:
    """Would EMPTYING this slot make the value it holds impossible to put back
    into it? The standalone form of _restore_blocked, for callers that hold only
    a row (slot_lock_map passes what it has already computed instead)."""
    return _blocks_restore(row, slot_id, True)


def overwrite_blocks_restore(row, slot_id) -> bool:
    """The same question about the OTHER way a stored value is destroyed: would
    REPLACING it with some other mutation make it impossible to put back here?

    THE TWO ARE NOT THE SAME QUESTION, and that is the whole reason this exists.
    A one-press paid "Confirmar" overwrites the identical one-way value the free
    "Quitar" is guarded against — a legacy "Cannibalistic", a diet-illegal
    capture, one of the seven unlockables sitting in n1/n3 — and it charges for
    the privilege. But the last-proof heredada, the one case clear_blocks_restore
    flags for a reason that belongs to emptying alone, is genuinely REVERSIBLE
    here: the swap keeps the family open, so the old value can be bought back,
    and asking twice for it would be friction over a move the player can undo.
    One flag could not say both things, so the server answers both.

    Never raises; when it cannot tell, it warns."""
    return _blocks_restore(row, slot_id, False)


def slot_lock_map(row: dict) -> dict[str, dict]:
    """{slot_id: {locked, code, reason, requires_growth_pct, requires_prime,
    requires_entombs, clear_closes, clear_blocks_restore,
    overwrite_blocks_restore, holds_unlockable}} for all 16 slots, so the GET can
    tell the UI WHY a slot is closed — and, on an open one, whether emptying it
    would close slots (slot_clear_closes) or whether either way of destroying
    what it holds would throw away a value the slot will not take back
    (_restore_blocked, asked once per action). Never raises — a slot it cannot
    evaluate comes back locked, not missing."""
    # The stored values and the diet-legal pool, read ONCE for all sixteen rather
    # than per slot: the two per-slot facts below are about the value a slot
    # HOLDS, and re-splitting the row's three columns sixteen times to learn that
    # is the shape this module already refuses elsewhere (see the memo over
    # _lineage_generation_cached). A row that is not a dict simply has no stored
    # values, which is what the fail-closed branches below already answer for.
    try:
        stored_values = slots_from_row(row) if isinstance(row, dict) else {}
        allowed_names = allowed_names_for_class(
            str(row.get("dino_class") or "") if isinstance(row, dict) else "")
        # THE UNKNOWN-NAME BEACON. Parthenogenesis rolled in game for two weeks
        # while the site did not recognise it, and the only signal was players
        # filing "my slot is bugged" — a refusal-shaped state that logged
        # NOTHING. Name each never-seen unrecognised stored value ONCE per
        # process, right where every editor open passes, so the day the game
        # grows a new mutation it appears in backend.log instead of a ticket.
        # Bounded (64 names ≫ one game's worth), repr-truncated, and inside
        # this try, so junk values can never 500 the editor.
        for _sid, _val in stored_values.items():
            if (_val != "None" and canonical_mutation_name(_val) is None
                    and _val not in _UNKNOWN_STORED_SEEN
                    and len(_UNKNOWN_STORED_SEEN) < 64):
                _UNKNOWN_STORED_SEEN.add(_val)
                _log.warning(
                    "[mutations] stored name not in catalog: %.80r (slot=%s) "
                    "— if the game added a mutation, the catalog needs it",
                    _val, _sid)
    except Exception:                     # noqa: BLE001 - never 500 the editor
        _log.exception("[mutations] slot_lock_map could not read the row")
        stored_values, allowed_names = {}, set()
    out: dict[str, dict] = {}
    for sid in SLOT_IDS:
        req = _LADDER.get(sid)
        lock = slot_lock(row, sid)
        closes = lock is None and slot_clear_closes(row, sid)
        stored = stored_values.get(sid, "None")
        out[sid] = {
            "locked": lock is not None,
            "code": lock[0] if lock else None,
            "reason": lock[1] if lock else None,
            "requires_growth_pct": req[0] if req else None,
            "requires_prime": bool(req[1]) if req else False,
            "requires_entombs": _ENTOMB.get(sid),
            # Only meaningful on an OPEN slot: a locked one already takes the
            # guarded path. Computed here so the UI never has to re-derive the
            # rule that opened the slot in the first place.
            "clear_closes": closes,
            # WHETHER EMPTYING THIS SLOT CAN BE WALKED BACK. The UI asks a second
            # time before an irreversible clear, and it may not decide that for
            # itself: an OPEN n1 holding an unlockable looks freely editable and
            # is not, because the POST refuses to write that name back into n1.
            # Gating the question on "is the slot locked" left exactly that case
            # on the unguarded one-press path.
            "clear_blocks_restore": _restore_blocked(
                sid, stored, allowed_names, lock is not None, closes),
            # THE SAME QUESTION ABOUT THE PAID OVERWRITE, because it destroys the
            # very same stored value and the UI may not assume the answer is the
            # same. It differs on exactly one row shape: the last-proof heredada,
            # whose EMPTYING shuts its family and whose SWAP does not (every
            # value the POST accepts is a recognised name, and a recognised name
            # is what proves the lineage). So a clear there is one-way and a swap
            # is not, and a single flag driving both would either wave the paid
            # press through everywhere else or ask twice for a move the player
            # can undo. Both are defects; the server answers both questions.
            "overwrite_blocks_restore": _restore_blocked(
                sid, stored, allowed_names, lock is not None, False),
            # ...and whether what it holds is one of the game's unlockables. The
            # editor used to infer that from "the stored value is not in this
            # slot's offer list", which is also true of a legacy or staff-granted
            # name the catalog has never heard of — those got labelled as
            # unlockable when they are nothing of the kind. The server knows.
            "holds_unlockable": is_hidden(stored),
        }
    return out


def active_count(row: dict) -> int:
    return sum(1 for v in slots_from_row(row).values() if v != "None")


class MutationEditError(ValueError):
    """Player-facing (Spanish) validation error."""


def validate_slot_edit(row: dict, slot_id: str, mutation: str) -> tuple[str, str]:
    """Validate one slot edit against a parked row. Returns
    (canonical_new_value, current_value) — canonical_new_value is "None" for a
    clear. Raises MutationEditError with a Spanish player-facing message."""
    if slot_id not in _SLOT_MAP:
        raise MutationEditError("Ranura de mutación desconocida.")

    slots = slots_from_row(row)
    current = slots[slot_id]

    raw = str(mutation or "").strip()
    if not raw or raw.lower() == "none":
        # CLEARING IS ALWAYS ALLOWED, locked slot included, and it is free: a
        # player must never be trapped holding a mutation he cannot remove.
        # This also covers rows that predate the ladder — they keep whatever is
        # stored (nothing is wiped), they just cannot be re-edited in place.
        return "None", current

    lock = slot_lock(row, slot_id)
    if lock is not None:
        # Checked before the name/diet/duplicate rules so a locked slot always
        # answers with the lock, whatever the player tried to put in it. The
        # POST is the authority — the UI's disabled state is only a courtesy.
        raise MutationEditError(lock[1])

    canon = canonical_mutation_name(raw)
    if not canon:
        raise MutationEditError(f"«{raw}» no es una mutación reconocida.")

    cls = str(row.get("dino_class") or "")
    if canon not in allowed_names_for_class(cls):
        restr = restriction_for(canon)
        species = cls.replace("BP_", "").replace("_C", "") or "esta especie"
        if restr == "carnivore":
            raise MutationEditError(
                f"{canon} es exclusiva de carnívoros; {species} no puede llevarla.")
        if restr == "herbivore":
            raise MutationEditError(
                f"{canon} es exclusiva de herbívoros; {species} no puede llevarla.")
        raise MutationEditError(f"{canon} no está disponible para {species}.")

    norm_new = normalize_mutation_name(canon)

    # THE DUPLICATE RULE RUNS BEFORE THE UNLOCKABLE ONE (2026-07-26). Both can be
    # true at once — the dino already carries Osteophagic in n2 and the player
    # tries to add it to n1 — and the unlockable copy would then answer "ponla en
    # la 2ª", which is where it already is. That is advice the player cannot act
    # on and cannot make sense of. The duplicate is the reason he can act on, so
    # it is the reason he gets. (Own slot excluded from the scan, so re-sending
    # the value already in this ranura is still the harmless no-op it is
    # everywhere else and still reaches the exemption below.)
    for other_id, other_val in slots.items():
        if other_id == slot_id or other_val == "None":
            continue
        if normalize_mutation_name(other_val) == norm_new:
            raise MutationEditError(
                f"{canon} ya está en otra ranura de este dinosaurio; "
                "no se permiten mutaciones duplicadas.")

    # THE UNLOCKABLE RULE (owner ruling 2026-07-27) — see HIDDEN_BLOCKED_SLOTS.
    #
    # AFTER the diet check on purpose, and that ordering is deliberate and stays:
    # on a herbivore, Osteophagic is refused because that species can never carry
    # it in ANY slot, and answering with "put it in the 2nd slot instead" would
    # be advice that cannot work. One reason per rejection, and it is always the
    # one the player can act on — which is the same reason the duplicate scan
    # above now runs first.
    #
    # THE VALUE ALREADY IN THIS SLOT IS EXEMPT, so ONLY NEW WRITES are refused.
    # A dino may already hold one of these in n1/n3 — captured off a live dino
    # that earned it in game, granted by staff, or bought — and that row keeps
    # the value, keeps showing it, and keeps clearing it for free. Nothing is
    # ever wiped or migrated. The exemption also means re-sending the value that
    # is already there stays the harmless no-op it is everywhere else, instead
    # of a 400 on an edit that would change nothing.
    if canon in HIDDEN and not slot_allows_hidden(slot_id) \
            and normalize_mutation_name(current) != norm_new:
        # The row goes in, so the copy can name the ranuras THIS dino can
        # actually reach right now instead of a pair it cannot open.
        raise MutationEditError(_hidden_reason(canon, row))

    return canon, current


def apply_slot_edit(row: dict, slot_id: str, new_value: str) -> dict[str, str]:
    """New {mutations, parent_mutations, elder_mutations} strings after writing
    `new_value` into `slot_id`, all columns normalized to full 4/4/8-segment
    "|"-strings (what the redeem restore command passes to the game)."""
    col, idx, count = _SLOT_MAP[slot_id]
    out = {
        "mutations": split_segments(row.get("mutations"), 4),
        "parent_mutations": split_segments(row.get("parent_mutations"), 4),
        "elder_mutations": split_segments(row.get("elder_mutations"), 8),
    }
    out[col][idx] = new_value
    return {k: join_segments(v) for k, v in out.items()}
