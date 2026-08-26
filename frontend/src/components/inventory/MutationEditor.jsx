import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Dna, Loader2, Search, X, Trash2, Coins, Lock } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

// Paid mutation editor for a parked (Bóveda) dinosaur — Dino Den style.
// Contract = GET/POST /me/vault/{id}/mutations. All SIXTEEN slots are drawn
// (owner ruling 2026-07-26 opened the twelve inherited ones): 4 propias plus
// three inherited generations of 4. A closed slot is drawn with its reason
// instead of being left out, the same treatment the own slots already get.
// Diet-restricted catalog, no duplicates (checked against ALL 16), PrimeMeat
// charge per added/changed mutation (clearing is free). The backend is the
// authority on every rule — this UI only pre-disables known rejections.
//
// The 1st and 3rd propia additionally do not OFFER the mutations the game makes
// you unlock in game (owner ruling 2026-07-27); the 2nd, the 4th and all twelve
// inherited ranuras offer everything. That answer arrives per ranura as
// meta.slot_catalog, already computed, so this file filters on a server-sent
// name list and never restates the rule. A ranura that already holds one keeps
// it: the rule refuses new writes only, and emptying stays free.
//
// THREE MORE SERVER-SENT FACTS COME WITH EACH RANURA, and they exist because
// this file must not work any of them out for itself:
//   slot_locks[slot].clear_blocks_restore — EMPTYING this ranura cannot be
//     walked back, because the save would refuse to write that same value into
//     that same ranura again. That is what arms the confirm, instead of "is the
//     ranura locked": a usable 1ª holding an unlockable is neither locked nor
//     reversible, and it was taking the single press.
//   slot_locks[slot].overwrite_blocks_restore — the same question about the
//     PAID press, which destroys the identical stored value and charges for it.
//     It is a separate answer because it differs on one row shape (the
//     last-proof heredada: emptying it shuts its family, swapping it does not),
//     and because a page that guessed would either wave the paid press through
//     or ask twice for a move the player can undo. Both are defects.
//   slot_locks[slot].holds_unlockable — what it holds really is one of those
//     mutations. Inferring it from "stored, and missing from the offer list"
//     also caught legacy and staff-granted names the catalog never carried, and
//     told the player those had to be unlocked in game.
//
// THE RULE THOSE THREE SERVE, stated once: any press that would destroy a
// stored mutation this ranura will not take back has to ask first — the free
// emptying and the paid overwrite alike, on all sixteen ranuras, decided by
// whether the value can come back and never by which button was pressed. And a
// ranura holding such a value says so on screen before anything is pressed.
//
// The twelve inherited slots are gated on how many times the dino has been
// entombed (1 -> heredadas, 2 -> Anciano A, 3 -> Anciano B), which REPLACES the
// 2026-07-12 ruling that every elder slot was always editable. That count, like
// growth, is frozen at the moment the dino was parked, so no copy here may say
// such a slot opens by itself. Requirements come from the server's own
// entomb_ladder; this file never restates a number.
//
// ONE EXCEPTION THE SERVER OWNS, NOT THIS FILE: a row whose heredadas column
// already holds a real mutation has proved that lineage step whatever its
// counter says (a dino sold with a "Linaje Parental" is that shape, and those
// four mutations were paid for), so the server opens the four heredadas on it.
// Two things follow, and both arrive as server-sent fields rather than as a rule
// restated here: `elder_stacks` stays the RECORDED count so "tu dino: N
// entierros" is never a lie, and slot_locks[slot].clear_closes marks the one
// ranura whose emptying would take the proof away and shut the family.
//
// Own slots also follow the growth/Prime ladder (owner ruling 2026-07-25):
// 25% -> 1st, 50% -> 2nd, 75% -> 3rd, 4th only on a Prime that reached 75%.
// The server sends slot_locks[slot] = {locked, reason, ...} already written in
// Spanish, plus growth_ladder for the legend — this file never restates the
// thresholds, so a re-ruling stays a one-line backend edit. A closed slot is
// still drawn, with its reason (the owner wants players to see what they are
// growing toward), and emptying it stays available and free so a mutation can
// never be trapped.
//
// Percentages come from the server (meta.growth_pct), which publishes the very
// same integer vault._dino_view puts on the card and on the preview header
// above this editor — never compute a growth percent here.
//
// A parked dino's growth is FROZEN at the moment it was stored (vault.park
// writes growth once, at INSERT; nothing updates it afterwards), so no copy in
// this file may say a closed slot opens on its own.
//
// What DOES open it depends on the server's lock code, and the copy has to
// branch on it (see LOCK_HOWTO). Only "growth" is opened by redeeming the dino,
// growing it in game and parking it again. "prime" is a property of the dino
// that growing never reaches at all, and "growth_unknown" is answered by its
// own reason sentence. Telling a non-Prime owner that growth will open it is a
// promise the rule can never keep, and acting on it means taking a real
// dinosaur back out of the vault where it can die.
// (Wording note: Tailwind scans comments, and the bare verb form of "growth"
// is itself a utility — writing it alone emits a real CSS rule. This file only
// ever uses growth / growing / grows.)
// The four families, in generational order. The inherited three carry
// ladder:"entomb", which is only a marker for "ask the server's entomb_ladder
// how many entierros this family needs" — the number itself is never written
// down here.
const GROUPS = [
  { key: "child", label: "Mutaciones Propias", slots: ["n1", "n2", "n3", "n4"] },
  { key: "parent", label: "Mutaciones Heredadas", slots: ["p1", "p2", "p3", "p4"], ladder: "entomb" },
  { key: "elder_a", label: "Mutaciones de Anciano · Grupo A", slots: ["ea1", "ea2", "ea3", "ea4"], ladder: "entomb" },
  { key: "elder_b", label: "Mutaciones de Anciano · Grupo B", slots: ["eb1", "eb2", "eb3", "eb4"], ladder: "entomb" },
];

// Every slot the UI draws — the active-count chip counts THESE, not the raw
// 16-slot payload, so the chip can never disagree with what is on screen.
// (All 16 are drawn now, so the two coincide; the rule stands either way.)
const VISIBLE_SLOTS = GROUPS.flatMap((g) => g.slots);

const RESTRICTION_LABEL = {
  carnivore: "Solo carnívoros",
  herbivore: "Solo herbívoros",
};

// What actually OPENS a closed slot, keyed by the server's own lock code
// (mutation_catalog.slot_lock -> "prime" | "growth" | "growth_unknown"). The
// server's reason sentence is always drawn above this; this line is the part
// that tells the player what to DO, so it may never be shown under a code where
// it is untrue. Growing only opens the "growth" rung. slot_lock answers "prime"
// BEFORE it ever looks at growth, so every non-Prime dino gets that code on its
// 4th own slot whatever its growth is, and no amount of growing changes it.
// A code with no entry here (or one we do not know) prints nothing: the reason
// above already stands on its own, and saying less is always safer than an
// instruction that cannot work.
const LOCK_HOWTO = {
  growth:
    "Cuenta el crecimiento que tenía al guardarlo y un dinosaurio guardado no crece, así que para abrir esta ranura tienes que sacarlo, hacerlo crecer en el juego y volver a guardarlo.",
  prime:
    "Ser Prime no depende del crecimiento: por mucho que lo hagas crecer, un dinosaurio que no es Prime nunca llega a tener la cuarta mutación propia. Sacarlo de la bóveda no cambia eso.",
  entomb:
    "Cuentan los entierros que tenía al guardarlo y un dinosaurio guardado no se entierra, así que para abrir esta ranura tienes que sacarlo, enterrarlo en el juego las veces que haga falta y volver a guardarlo.",
};

// ── WHAT IS TRUE WHEN A STORED MUTATION IS ABOUT TO BE DESTROYED ─────────────
// ONE place decides it, and both surfaces that say it out loud read from here:
// the standing notice a ranura carries while it holds such a value, and the
// question asked before the press that would destroy it. Two copies of this
// wording would drift, and the player would be told two different things about
// one mutation on one screen.
//
// EVERY SENTENCE IS BUILT FROM THE DATA — which case the server put this ranura
// in, plus the NAME the ranura is holding. A sentence with no name in it cannot
// tell the player what he is about to lose and reads identically for every
// mutation on the dinosaur, so naming it is not decoration: it is what makes it
// a warning instead of a noise. (Sensitivity: change the stored value and every
// sentence below changes with it. A constant string would not.)
const ONE_WAY_TEXT = {
  // The last-proof heredada. The biggest loss (four ranuras, not one), and the
  // ONLY case where the two ways of destroying the value differ — emptying
  // takes the lineage proof away, swapping keeps it — so it says both halves.
  lineage: (held) =>
    `«${held}» es la última mutación heredada que le queda, y es lo que mantiene `
    + "abiertas las cuatro ranuras heredadas. Si la quitas se cerrarán las cuatro "
    + "y no podrás volver a ponerla aquí, ni poner ninguna otra, hasta que "
    + "entierres al dinosaurio en el juego. Cambiarla por otra mutación no cierra nada.",
  // BOTH OF THE ABOVE AT ONCE, and the pair needs its own sentence because
  // either half alone is false by omission. A last-proof heredada can hold a
  // value the ranura would refuse on its own terms — a capture this species
  // cannot carry, a name the catalog never had — and then "hasta que entierres
  // al dinosaurio" promises this very mutation comes back once the four reopen.
  // It does not: the ranura will not take that name again whatever the lineage
  // does. Says the closing AND the refusal, and is honest that the swap keeps
  // the four open but loses the value just the same.
  lineage_value: (held) =>
    `«${held}» es la última mutación heredada que le queda, y es lo que mantiene `
    + "abiertas las cuatro ranuras heredadas. Si la quitas se cerrarán las cuatro, "
    + `y además esta ranura ya no admite «${held}»: aunque entierres al dinosaurio `
    + "en el juego y se vuelvan a abrir, esa mutación no podrá volver aquí. "
    + "Cambiarla por otra no cierra ninguna ranura, pero la pierdes igual.",
  // A closed ranura. "You will not be able to put anything back" is only true
  // while the ranura itself stays shut, which is how it is said.
  locked: (held) =>
    "La ranura está bloqueada y no admite nada nuevo: si quitas "
    + `«${held}» no podrás volver a ponerle nada mientras la ranura siga bloqueada.`,
  // A usable ranura holding a value it will not take back: a legacy or
  // staff-granted capture, a value this species cannot carry, or one of the
  // mutations the game makes you unlock sitting in a ranura that does not offer
  // them. The ranura stays perfectly usable for everything else and the copy has
  // to say so, or it promises a loss that is not happening.
  value: (held) =>
    `Esta ranura conserva «${held}» porque ya la tenía guardada, pero no admite `
    + "que se le ponga de nuevo: en cuanto la saques no podrás volver a ponerla "
    + "aquí. La ranura te seguirá sirviendo para otras mutaciones.",
  // The page knows the value may not come back but cannot tell WHY: a payload
  // that predates overwrite_blocks_restore (a cached GET against a newer page),
  // or a ranura the payload never described at all. Every other sentence here
  // would be stating a reason it does not have. Say exactly what is known — and
  // name no action, because the lead above already says which press it is and
  // this one now covers both of them.
  unknown: (held) =>
    `Esta ranura ya lleva «${held}» y no podemos asegurarte que puedas volver a `
    + "ponerla aquí.",
};

// The half-sentence that names the ACTION, so the question reads as one thing
// happening now and the standing notice reads as a fact about the ranura. The
// consequence above is identical in both, which is the point.
const oneWayLead = (held, nextName) =>
  (nextName ? `Vas a cambiar «${held}» por «${nextName}».` : `Vas a quitar «${held}».`);

function norm(name) {
  return String(name || "").replace(/[\s_]+/g, "").toLowerCase();
}

// Stored values may be game-captured camel-case ("AcceleratedPreyDrive");
// display them like the catalog's spaced names.
function displayName(value, catalog) {
  if (!value || value === "None") return null;
  const hit = (catalog || []).find((c) => norm(c.name) === norm(value));
  return hit ? hit.name : String(value).replace(/(?<=[a-z])(?=[A-Z])/g, " ");
}

function SlotRow({ slotId, index, value, catalog, lock, onEdit }) {
  const name = displayName(value, catalog);
  const isLocked = !!lock?.locked;
  // A locked slot that still holds a mutation keeps its button: the only action
  // left there is removing it, which is always allowed and always free.
  const actionable = !isLocked || !!name;
  return (
    <div className={`flex items-start justify-between gap-2 glass rounded-lg px-2.5 py-2 ${isLocked ? "border border-white/10" : ""}`}
      data-testid={`mutation-slot-${slotId}`} data-locked={isLocked ? "1" : "0"}>
      <div className="min-w-0">
        <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1">
          {isLocked && <Lock size={9} className="text-crimson" />} Ranura {index}
        </p>
        <p className={`text-[11px] font-bold truncate ${name ? "" : "text-muted-foreground italic"}`}>
          {name || (isLocked ? "— Bloqueada —" : "— Ninguna —")}
        </p>
        {isLocked && lock?.reason && (
          <p className="text-[9px] text-crimson/90 leading-snug mt-0.5" data-testid={`mutation-lock-reason-${slotId}`}>
            {lock.reason}
          </p>
        )}
      </div>
      <button
        onClick={onEdit} disabled={!actionable} data-testid={`mutation-edit-${slotId}`}
        title={isLocked ? lock?.reason || "Ranura bloqueada" : undefined}
        className={`text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1.5 rounded-md border transition-colors shrink-0 ${
          isLocked
            ? "border-crimson/40 text-crimson hover:bg-crimson/10 disabled:opacity-40 disabled:hover:bg-transparent"
            : "border-gold/40 text-gold hover:bg-gold/10"
        }`}>
        {isLocked ? (name ? "Quitar" : "Bloqueada") : "Editar"}
      </button>
    </div>
  );
}

// `pending` / onArm / onCancelPending / onConfirmPending come from the PARENT on
// purpose — see the note over MutationEditor's own useState. `openToken` changes
// on every open, so the reset below really re-runs; keying it on `open` did not,
// because `open` is passed as a literal and never changes.
function PickerModal({ open, openToken, slotId, slotValue, meta, lock, usedNorms, busy,
  pending, onArm, onCancelPending, onConfirmPending, onPick, onClear, onClose }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  useEffect(() => { setQuery(""); setSelected(null); }, [slotId, openToken]);
  // Memoised so the `|| []` fallback does not hand `offered` a brand-new array
  // identity on every render, which would defeat its useMemo below.
  const catalog = useMemo(() => meta?.catalog || [], [meta?.catalog]);
  const cost = meta?.cost_per_change ?? 0;
  const balance = meta?.balance ?? 0;
  const isLocked = !!lock?.locked;
  // Resolved by VALUE TYPE, not truthiness: a code this build does not know —
  // or an inherited key such as "constructor" — must resolve to nothing at all,
  // never to a non-string that React would choke on.
  const lockHowto = typeof LOCK_HOWTO[lock?.code] === "string" ? LOCK_HOWTO[lock.code] : null;
  const currentNorm = norm(slotValue === "None" ? "" : slotValue);
  // ── THE RULE, AND IT IS ABOUT THE VALUE, NEVER ABOUT THE BUTTON ─────────────
  // ANY press that would destroy a stored mutation this ranura will not take
  // back has to ask first. There are exactly TWO such presses and for a long
  // time only one of them asked:
  //   * the free "Quitar", which empties the ranura;
  //   * the paid "Confirmar", which overwrites the very same stored value with
  //     the picked one and CHARGES for it. It went through on a single press
  //     with nothing on screen having said what it was about to destroy — so a
  //     parked dino whose ea1 held "Cannibalistic" (a real registry name the
  //     catalog deliberately never offers, captured verbatim at park time) lost
  //     it forever, for 20.000 PrimeMeat, in one click.
  // So the question is asked by the ANSWER — can this stored value come back
  // into this ranura — and never by which control was pressed or which family
  // the ranura belongs to. Both presses arm the SAME warning panel, and the
  // panel's own control is the only thing that acts; the pressed button becomes
  // the way out. That matters because a habitual double press is two separate
  // events in two renders: relabelling the pressed button in place meant the
  // second press landed on the armed button and destroyed the mutation with the
  // warning on screen for a few milliseconds. Pressing either spot twice now
  // arms and then cancels, which is the harmless outcome.
  //
  // Emptying itself is always allowed and always costs nothing, a closed ranura
  // included, so a mutation can never be trapped. The question is advice, never
  // a gate.
  //
  // THREE cases, not one:
  //  1. A CLOSED slot. The same rule that closed it refuses every write into it
  //     again, and a parked dino's growth and entierros never move.
  //  2. An OPEN heredada that is the row's LAST PROOF of its own lineage. Those
  //     four slots can be open only because one of them holds a mutation (the
  //     server derives the lineage step from that column when the stored
  //     entierro counter says 0 — a dino bought with "Linaje Parental" is
  //     exactly this shape). Emptying the last one takes the proof with it and
  //     shuts all four, and nothing puts it back until the dino is buried in
  //     game. The server decides this, per slot, and sends it as
  //     slot_locks[slot].clear_closes — this file never re-derives the rule.
  //  3. An OPEN slot holding a value THIS ranura would not accept back. The 1ª
  //     and the 3ª propia keep a mutation that has to be unlocked in game if it
  //     was already stored there, but the save refuses to write that name into
  //     them ever again — so the ranura reads as freely editable while the
  //     emptying is one-way. A legacy or staff-granted name the catalog does not
  //     carry behaves the same. Gating the question on "is the ranura locked"
  //     left every one of those on the unguarded single press.
  //     THE ANSWER COMES FROM THE SERVER, per ranura, as
  //     slot_locks[slot].clear_blocks_restore: it already knows what each ranura
  //     offers and what each ranura locks, and this file must not re-derive
  //     either. A payload without the field behaves exactly as before.
  // Every other OPEN slot keeps its one-press emptying, because there the player
  // can simply put it back.
  const hasValue = !!slotValue && slotValue !== "None";
  // A RANURA THE PAYLOAD NEVER DESCRIBED HAS NO ANSWER TO GIVE, AND NO ANSWER
  // MUST ASK. With no entry in slot_locks at all, every question below read
  // false — not locked, not closing, not blocking a restore, and the paid press
  // unanswered — so a ranura holding a one-way value took the single unguarded
  // press on BOTH controls, which is the exact defect this panel exists to stop.
  // The server fails closed on anything it cannot read (_blocks_restore warns
  // when it cannot tell) and so does this. It is only ever about a MISSING
  // ENTRY: an entry that exists without the newer fields is an older payload and
  // keeps the documented fallback below, which its own case pins.
  const lockMissing = lock == null;
  const clearClosesSlots = !isLocked && !!lock?.clear_closes;
  const clearBlocksRestore = lockMissing || !!lock?.clear_blocks_restore;
  const clearIsIrreversible = hasValue && (isLocked || clearClosesSlots || clearBlocksRestore);
  // THE VALUE'S OWN ANSWER, separated from the lineage's. overwrite_blocks_restore
  // asks the same "can it come back" with the closing term switched off, so on an
  // OPEN ranura a true there is the value being refused on its own terms and
  // nothing else.
  const valueBlocksRestore = !!lock?.overwrite_blocks_restore;
  // Which case, for the wording. A closing clear is named first because it is the
  // biggest loss (four ranuras, not one), and a closed ranura before a usable one
  // because "you will not be able to put anything back" is only true while the
  // ranura itself stays shut. The closing case then splits: when the value is one
  // this ranura would refuse anyway, the plain lineage sentence tells the player
  // that burying the dinosaur brings it back, and that is not true of THAT value.
  const clearKind = lockMissing ? "unknown"
    : (clearClosesSlots
      ? (valueBlocksRestore ? "lineage_value" : "lineage")
      : (isLocked ? "locked" : "value"));

  // THE SAME QUESTION FOR THE PAID PRESS, AND IT IS A DIFFERENT ANSWER ON ONE
  // ROW SHAPE, which is why the server sends it separately instead of the page
  // reusing the clear's flag. Emptying the last-proof heredada shuts its whole
  // family, so nothing goes back in; SWAPPING it keeps the family open (every
  // value the save accepts is a recognised name, and a recognised name is what
  // proves the lineage), so the old mutation can be bought back and that press
  // must stay a single one. Asking twice where the player can simply put the
  // value back is a defect of its own.
  //
  // AN OLDER PAYLOAD (a cached GET against this page) carries no answer. Fall
  // back to the clear's flag, minus the one term that provably cannot apply to a
  // swap, and say plainly that the reason is not known — see ONE_WAY_TEXT.
  const overwriteAnswered = lock != null && lock.overwrite_blocks_restore !== undefined
    && lock.overwrite_blocks_restore !== null;
  const overwriteIsIrreversible = hasValue && (overwriteAnswered
    ? !!lock.overwrite_blocks_restore
    : clearBlocksRestore);
  // A swap never closes a family and never happens on a closed ranura, so the
  // only truthful reason left is the value itself — unless the payload never
  // answered and the clear's flag came from the closing rule, or there was no
  // entry to read at all, where the page genuinely cannot tell which reason it is
  // looking at.
  const overwriteKind = (!overwriteAnswered && (clearClosesSlots || lockMissing))
    ? "unknown" : "value";

  // WHAT IS ARMED RIGHT NOW, and the value that press would write. The value
  // travels with the question, so the control in the panel can only ever save
  // exactly what the sentence above it described — a selection changed after
  // arming cancels the question rather than quietly re-aiming it.
  const armedForClear = pending?.action === "clear";
  const armedForOverwrite = pending?.action === "overwrite";

  // WHICH names THIS slot accepts comes from the server (meta.slot_catalog),
  // never from a rule restated here. Owner ruling 2026-07-27: the 1st and 3rd
  // propia do not offer the mutations the game makes you unlock, while the 2nd,
  // the 4th and all twelve inherited ranuras offer everything. The server sends
  // the finished answer per ranura, so this file cannot drift from the POST that
  // enforces it — and so a re-ruling stays a one-line backend edit.
  // (Wording note: Tailwind scans this file as plain tokens, comments included,
  // and the bare adjective for "not shown" is itself a utility. Say unlockable.)
  //
  // A payload without the field (an older server) falls back to the full
  // catalog. Erring open is the only safe default: refusing names the server
  // never refused would take away mutations a player is entitled to, and the
  // POST is the authority either way.
  const allowedNorms = useMemo(() => {
    const names = meta?.slot_catalog?.[slotId];
    return Array.isArray(names) ? new Set(names.map(norm)) : null;
  }, [meta, slotId]);

  const offered = useMemo(
    () => (allowedNorms ? catalog.filter((c) => allowedNorms.has(norm(c.name))) : catalog),
    [catalog, allowedNorms]);

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return offered.filter((c) => !q || c.name.toLowerCase().includes(q) || (c.description || "").toLowerCase().includes(q));
  }, [offered, query]);

  // The missing names are simply not drawn — never drawn disabled, and never
  // labelled "En uso", which would say something false about them. This one
  // server-written sentence is what explains the shorter list instead.
  const narrowed = offered.length < catalog.length;
  // ...and if the ranura ALREADY holds one of them, say that it stays. The rule
  // gates new writes only; nothing stored is ever removed or taken off screen.
  //
  // WHETHER IT IS ONE OF THEM IS THE SERVER'S ANSWER (slot_locks[slot]
  // .holds_unlockable), not a set difference done here. "Stored, and not in this
  // ranura's offer list" is also true of a name the catalog has never carried —
  // a legacy capture, or something staff granted — and those were being told
  // they had to be unlocked in game, which is simply false about them. The
  // second half stays, because the sentence also promises the ranura will not
  // take it back, and that is only true where the ranura does not offer it.
  const keepsUnlockable = !!lock?.holds_unlockable
    && !!currentNorm && !offered.some((c) => norm(c.name) === currentNorm);

  if (!open) return null;
  const selectedIsCurrent = selected && norm(selected) === currentNorm;
  const canAfford = balance >= cost;
  // The name the player reads, not the raw stored string: a game capture arrives
  // camel-case ("ReniculateKidneys") and has to appear the way the catalog
  // spells it, in the sentence as much as in the ranura row.
  const heldName = displayName(slotValue, catalog);
  const pendingKind = armedForOverwrite ? overwriteKind : clearKind;
  const pendingText = pending && heldName
    ? `${oneWayLead(heldName, armedForOverwrite ? displayName(pending.value, catalog) : null)} `
      + `${(ONE_WAY_TEXT[pendingKind] || ONE_WAY_TEXT.value)(heldName)}`
    : null;

  // Portal to <body>: the preview card's backdrop blur (.glass-strong) makes
  // the card the containing block for fixed descendants, so without the portal
  // this inset-0 overlay anchors to the ~692px card and gets clipped by the
  // card's hidden overflow (no Confirmar) whenever 80vh exceeds the card.
  // (Wording note: Tailwind scans comments — avoid literal utility tokens.)
  return createPortal(
    <motion.div className="fixed inset-0 z-[125] flex items-center justify-center p-4"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="mutation-picker">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose}
        data-testid="mutation-picker-backdrop" />
      <div className="relative glass-strong rounded-2xl w-full max-w-md max-h-[80vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-white/10 shrink-0">
          <div>
            <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5"><Dna size={11} /> {isLocked ? "Ranura bloqueada" : "Editar Mutación"}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {isLocked
                ? "Solo puedes quitar la mutación que ya tiene. Quitar siempre es gratis."
                : <>Cada mutación nueva o cambiada cuesta <span className="text-gold font-bold">{Number(cost).toLocaleString("es")} PrimeMeat</span> · Saldo: <span className="font-bold">{Number(balance).toLocaleString("es")}</span></>}
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg glass hover:bg-white/10 transition-colors" data-testid="mutation-picker-close"><X size={16} /></button>
        </div>

        {/* THE STANDING NOTICE. A ranura holding a value it will not take back
            says so BEFORE anything is pressed, on all sixteen and whatever the
            reason. It used to be narrowed to "holds one of the seven the game
            makes you unlock, in the 1ª or the 3ª", which left every other
            one-way value with nothing on screen at all — a legacy capture, a
            value the species cannot carry, anything sitting in a closed ranura.
            It sits OUTSIDE the locked/open split for the same reason. While a
            question is armed the panel below carries the very same sentence with
            the action named, so it is never said twice at once. */}
        {clearIsIrreversible && !pending && heldName && (
          <div className="mx-5 mt-3 rounded-lg px-3 py-2.5 bg-crimson/10 border border-crimson/30 shrink-0"
            data-testid="mutation-oneway-notice" data-clear-kind={clearKind}>
            <p className="text-[10px] text-crimson/90 leading-snug">
              {(ONE_WAY_TEXT[clearKind] || ONE_WAY_TEXT.value)(heldName)}
            </p>
          </div>
        )}

        {/* THE ONE STRUCTURAL CONFIRM, and both destructive presses arm it — the
            free emptying and the paid overwrite. One panel, one control that
            acts, one place the wording comes from; the pressed button turns into
            the way out. The sentence branches because the cases are not the same
            promise: a closed ranura stays closed, a last-proof heredada closes
            its whole family the moment it is emptied, and a usable ranura
            holding a value it will not take back stays perfectly usable for
            everything else. */}
        {pending && pendingText && (
          <div className="mx-5 mt-3 rounded-lg px-3 py-3 bg-crimson/15 border border-crimson/40 shrink-0"
            data-testid="mutation-clear-warning" data-clear-kind={pendingKind}
            data-action={pending.action}>
            <p className="text-[11px] font-bold text-crimson leading-snug">{pendingText}</p>
            <p className="text-[10px] text-muted-foreground mt-1">
              Si estás seguro, confírmalo con este botón. El de abajo lo deja como está.
            </p>
            <button
              onClick={onConfirmPending} disabled={busy}
              data-testid="mutation-clear-confirm"
              className="mt-2 w-full inline-flex items-center justify-center gap-1.5 text-[11px] font-bold px-3 py-2 rounded-lg bg-crimson text-background hover:brightness-110 transition-all disabled:opacity-40">
              {armedForOverwrite
                ? <><Coins size={12} /> Sí, cambiarla ({Number(cost).toLocaleString("es")} PrimeMeat)</>
                : <><Trash2 size={12} /> Sí, quitarla (gratis)</>}
            </button>
          </div>
        )}

        {isLocked ? (
          <div className="px-5 py-4 flex-1 min-h-0 overflow-y-auto space-y-2" data-testid="mutation-picker-lock">
            <div className="flex items-start gap-2.5 rounded-lg px-3 py-3 bg-crimson/10 border border-crimson/30">
              <Lock size={14} className="text-crimson shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-[12px] font-bold text-crimson">{lock?.reason || "Ranura bloqueada."}</p>
                {lockHowto && (
                  <p className="text-[10px] text-muted-foreground mt-1"
                    data-testid="mutation-lock-howto" data-lock-code={lock?.code || ""}>
                    {lockHowto}
                  </p>
                )}
                <p className="text-[10px] text-muted-foreground mt-1">
                  Lo que ya tiene guardado sigue ahí mientras tú no lo quites.
                </p>
              </div>
            </div>
          </div>
        ) : (<>
        <div className="px-5 py-2.5 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2 glass rounded-lg px-2.5">
            <Search size={13} className="text-muted-foreground shrink-0" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar mutación…"
              className="w-full bg-transparent outline-none text-[12px] py-2" data-testid="mutation-picker-search" />
          </div>
        </div>

        {narrowed && (meta?.unlockable_notice || meta?.unlockable_kept_notice) && (
          <div className="mx-3 mt-2 rounded-lg px-3 py-2 glass border border-white/10 shrink-0"
            data-testid="mutation-unlockable-notice"
            data-kept={keepsUnlockable ? "1" : "0"}>
            {meta?.unlockable_notice && (
              <p className="text-[10px] text-muted-foreground leading-snug">{meta.unlockable_notice}</p>
            )}
            {keepsUnlockable && meta?.unlockable_kept_notice && (
              <p className="text-[10px] text-gold leading-snug mt-1"
                data-testid="mutation-unlockable-kept">{meta.unlockable_kept_notice}</p>
            )}
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 space-y-1">
          {list.map((c) => {
            const inUse = usedNorms.has(norm(c.name)) && norm(c.name) !== currentNorm;
            const isCurrent = norm(c.name) === currentNorm;
            const isSelected = selected === c.name;
            return (
              <button key={c.name} disabled={inUse}
                // Picking a different mutation while the paid question is armed
                // cancels the question. The armed value travels with it, so the
                // panel could not have saved the new pick behind the old
                // sentence — but leaving a question on screen that describes a
                // mutation the player has since moved off is its own lie.
                onClick={() => {
                  if (armedForOverwrite) onCancelPending();
                  setSelected(isSelected ? null : c.name);
                }}
                data-testid={`mutation-option-${norm(c.name)}`}
                className={`w-full text-left rounded-lg px-3 py-2 transition-colors border ${
                  isSelected ? "border-gold/60 bg-gold/10" : "border-transparent hover:bg-white/5"
                } ${inUse ? "opacity-40 cursor-not-allowed" : ""}`}>
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-bold">{c.name}</span>
                  {c.restriction && (
                    <span className="text-[8px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-crimson/15 text-crimson border border-crimson/30">
                      {RESTRICTION_LABEL[c.restriction] || c.restriction}
                    </span>
                  )}
                  {isCurrent && <span className="text-[8px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-gold/20 text-gold border border-gold/40">Actual</span>}
                  {inUse && <span className="text-[8px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded glass border border-white/15">En uso</span>}
                </div>
                {c.description && <p className="text-[10px] text-muted-foreground mt-0.5">{c.description}</p>}
              </button>
            );
          })}
          {!list.length && <p className="text-[11px] text-muted-foreground text-center py-6">Sin resultados para esa búsqueda.</p>}
        </div>
        </>)}

        <div className="px-5 py-3.5 border-t border-white/10 shrink-0 space-y-2">
          {!isLocked && selected && !selectedIsCurrent && !canAfford && (
            <p className="text-[10px] text-crimson font-bold">PrimeMeat insuficiente para este cambio.</p>
          )}
          <div className={isLocked ? "" : "grid grid-cols-2 gap-2"}>
            {/* Neither of these two ever destroys anything on an irreversible
                ranura: the first press asks, a second press on the same spot
                backs out. Only the warning panel's own control acts. */}
            <button
              onClick={() => (clearIsIrreversible
                ? (armedForClear ? onCancelPending() : onArm("clear", "None"))
                : onClear())}
              disabled={busy || !hasValue}
              data-testid="mutation-picker-clear"
              data-armed={armedForClear ? "1" : "0"}
              className="w-full inline-flex items-center justify-center gap-1.5 text-[11px] font-bold px-3 py-2 rounded-lg bg-crimson/15 text-crimson border border-crimson/30 hover:bg-crimson/25 transition-all disabled:opacity-40">
              {armedForClear
                ? "No, dejarla como está"
                : <><Trash2 size={12} /> Quitar (gratis)</>}
            </button>
            {!isLocked && (
              <button
                // THE PAID PRESS TAKES THE SAME PATH AS THE FREE ONE when it
                // would destroy a value the ranura will not take back. It stays
                // a single press otherwise, which is every ordinary swap.
                onClick={() => {
                  if (!selected) return;
                  if (!overwriteIsIrreversible) { onPick(selected); return; }
                  if (armedForOverwrite) onCancelPending();
                  else onArm("overwrite", selected);
                }}
                disabled={busy || !selected || selectedIsCurrent || !canAfford}
                data-testid="mutation-picker-confirm"
                data-armed={armedForOverwrite ? "1" : "0"}
                className="inline-flex items-center justify-center gap-1.5 text-[11px] font-bold px-3 py-2 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-40">
                {armedForOverwrite ? "No, dejarla como está" : <>
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Coins size={12} />}
                  Confirmar — {Number(cost).toLocaleString("es")}
                </>}
              </button>
            )}
          </div>
        </div>
      </div>
    </motion.div>,
    document.body
  );
}

export function MutationEditor({ dino, onChanged }) {
  const { play } = useSound();
  const [meta, setMeta] = useState(null); // GET response: catalog/cost/balance/slots/unlocked
  const [slots, setSlots] = useState(null);
  const [editingSlot, setEditingSlot] = useState(null);
  // The "are you sure" behind an irreversible press lives HERE, in the parent
  // that stays mounted, and openPicker below wipes it on every open. It used to
  // live inside PickerModal, where it survived a close and a reopen of the SAME
  // slot: closing the picker is not a remount — framer-motion keeps the child
  // on screen while it fades out and cancels that exit when the same child
  // comes back, so the picker reopened with its confirm still armed and the
  // very next press removed the mutation without ever showing the warning.
  //
  // IT CARRIES THE VALUE, not just a boolean, because two different presses arm
  // it now: {action:"clear", value:"None"} and {action:"overwrite", value:<the
  // picked name>}. The panel's control saves `pending.value` and nothing else,
  // so what is written is always exactly what the sentence above it described —
  // a selection that moved after arming cannot be saved behind the old wording,
  // and the picker cancels the question in that case anyway.
  const [pending, setPending] = useState(null);
  // Counts opens, so the picker's own scratch state (search text, selection) is
  // reset by an effect that really does re-run instead of by an unmount that
  // may never come.
  const [pickerOpens, setPickerOpens] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setMeta(null); setSlots(null); setEditingSlot(null); setPending(null);
    if (!dino?.id) return undefined;
    api.meVaultMutations(dino.id)
      .then((r) => { if (alive) { setMeta(r.data); setSlots(r.data.slots); } })
      .catch(() => { if (alive) setMeta(undefined); });
    return () => { alive = false; };
  }, [dino?.id]);

  if (!dino) return null;

  const catalog = meta?.catalog || [];
  // Count only the slots the page draws. The duplicate pre-check below is the
  // other way round on purpose: it spans every slot the payload carries, drawn
  // or not, so the picker matches the backend's no-dup rule exactly.
  const activeCount = slots
    ? VISIBLE_SLOTS.filter((sid) => slots[sid] && slots[sid] !== "None").length
    : null;
  const usedNorms = new Set(
    Object.entries(slots || {})
      .filter(([, v]) => v && v !== "None")
      .map(([, v]) => norm(v)));
  // Server-sent lock state. A slot the server did not describe is treated as
  // open — the POST re-checks every rule anyway, so a stale bundle can only
  // cost the player a rejected click, never an unpaid write.
  const lockFor = (sid) => (meta?.slot_locks || {})[sid] || null;
  // THE DENOMINATOR ON THE COUNT CHIP: how many of the sixteen are this dino's
  // to use right now — every open one, plus any closed one that already holds a
  // mutation (that one is genuinely in use, and emptying it stays available and
  // free). A hardcoded sixteen was a promise the rules never make: a dino that
  // has never been buried can only ever fill four of them, so "dos de dieciséis"
  // read as fourteen free ranuras where two existed. Because every filled slot
  // is counted here, the left number can never exceed the right one.
  const availableCount = slots
    ? VISIBLE_SLOTS.filter(
      (sid) => !lockFor(sid)?.locked || (slots[sid] && slots[sid] !== "None")).length
    : null;
  // One legend built from the server's own ladder, so the page never restates
  // the thresholds. "1ª 25% · 2ª 50% · 3ª 75% · 4ª 75% Prime"
  const ladderLine = (meta?.growth_ladder || [])
    .map((r) => `${r.index}ª ${r.requires_growth_pct}%${r.requires_prime ? " Prime" : ""}`)
    .join(" · ");
  // How many entierros a family needs, read from the server's own ladder by the
  // family's first slot id. The number is never written down in this file, so a
  // re-ruling stays a one-line backend edit. A family the server did not
  // describe simply gets no requirement line.
  // Two different words for the same number, because Spanish needs both: the
  // COUNT is "1 entierro / 2 entierros" (a heading chip, "tu dino: 0 entierros"),
  // but after the participle it is "enterrado al menos 1 vez / 2 veces". Using
  // the noun there read "ha sido enterrado al menos 2 entierros", which sat
  // forty pixels above a per-slot reason that said "2 veces" correctly.
  const entombWord = (n) => (n === 1 ? "entierro" : "entierros");
  const entombTimes = (n) => (n === 1 ? "vez" : "veces");
  const entombReqFor = (g) => {
    if (g.ladder !== "entomb") return null;
    const hit = (meta?.entomb_ladder || []).find((r) => r.slot === g.slots[0]);
    return typeof hit?.requires_entombs === "number" && hit.requires_entombs > 0
      ? hit.requires_entombs
      : null;
  };
  // null when the server could not read the column — never print "0 entierros"
  // for a value nobody could parse.
  const stacks = typeof meta?.elder_stacks === "number" ? meta.elder_stacks : null;

  // EVERY way into the picker goes through here, so no route into it can skip
  // the reset: an armed confirm never outlives the open it was armed in.
  const openPicker = (slotId) => {
    setPending(null);
    setPickerOpens((n) => n + 1);
    setEditingSlot(slotId);
    play("open");
  };
  const closePicker = () => { setPending(null); setEditingSlot(null); };

  const doSet = async (slotId, mutation) => {
    setBusy(true);
    try {
      const r = await api.meVaultMutationSet(dino.id, slotId, mutation);
      setSlots(r.data.slots);
      // THE LOCKS COME BACK WITH THE SAVE, and they must replace what the GET
      // sent: an edit can move them. The four heredadas of a dino whose entierro
      // counter says 0 are open only because that column still holds a mutation,
      // so emptying the last one shuts all four — a page still holding the old
      // map would draw them as usable and would offer the plain one-press
      // emptying on the next one, which is the very case the warning panel
      // exists for. Absent fields keep what was already there, so an older
      // server build simply behaves as before.
      setMeta((m) => (m ? {
        ...m,
        balance: r.data.balance ?? m.balance,
        slot_locks: r.data.slot_locks ?? m.slot_locks,
        elder_stacks: r.data.elder_stacks !== undefined ? r.data.elder_stacks : m.elder_stacks,
      } : m));
      play("success");
      if (r.data.charged > 0) {
        toast.success(`Mutación aplicada (−${Number(r.data.charged).toLocaleString("es")} PrimeMeat)`);
      } else {
        toast.success(mutation && mutation !== "None" ? "Mutación aplicada" : "Ranura vaciada");
      }
      setEditingSlot(null);
      setPending(null);
      onChanged?.();
    } catch (e) {
      play("error");
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" && detail ? detail : "No se pudo editar la mutación");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="mutation-editor">
      <div className="flex items-center justify-between mb-2">
        <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5">
          <Dna size={11} /> Mutaciones
        </p>
        <span className="text-[10px] font-extrabold text-gold tabular-nums" data-testid="mutation-active-count"
          data-available={availableCount === null ? "" : String(availableCount)}
          title="Ranuras que puedes usar en este dinosaurio ahora mismo: las abiertas, más las que ya tienen una mutación guardada.">
          {activeCount === null || availableCount === null
            ? "—"
            : `${activeCount}/${availableCount}`} activas
        </span>
      </div>

      {meta === undefined && (
        <p className="text-[11px] text-muted-foreground">No se pudo cargar el editor de mutaciones.</p>
      )}
      {meta === null && (
        <p className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Cargando mutaciones…</p>
      )}

      {meta && slots && (
        <div className="space-y-3">
          {GROUPS.map((g) => {
            const req = entombReqFor(g);
            // A family the server left usable even though this dino's entierro
            // count is below the requirement. That happens when the row itself
            // carries inherited mutations (a dino bought with "Linaje Parental",
            // for one): the server reads the lineage from the column. Saying
            // "se abren con 1 entierro · tu dino: 0 entierros" over four usable
            // ranuras is a straight contradiction, so that case gets its own
            // sentence and the entierro count is never restated as a reason.
            // `stacks === null` (the server could not read the column) counts
            // as below the requirement: if the family is usable anyway, it is
            // the column that opened it, and that is the sentence to print.
            const lineageOpened = !!req && (stacks === null || stacks < req)
              && g.slots.some((sid) => !lockFor(sid)?.locked);
            return (
            <div key={g.key} data-testid={`mutation-group-${g.key}`}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                {g.label}{req ? ` · ${req} ${entombWord(req)}` : ""}
              </p>
              {req && (
                <p className="text-[9px] text-muted-foreground mb-1.5 leading-snug"
                  data-testid={`mutation-entomb-legend-${g.key}`}
                  data-lineage={lineageOpened ? "1" : "0"}>
                  {lineageOpened ? (
                    <>
                      Ya están abiertas porque este dinosaurio ya trae mutaciones heredadas.
                      Normalmente se abren cuando ha sido enterrado al menos {req} {entombTimes(req)}.
                      {" "}Si quitas la última que le queda, se cerrarán las cuatro.
                    </>
                  ) : (
                    <>
                      Se abren cuando el dinosaurio ha sido enterrado al menos {req} {entombTimes(req)}.
                      {stacks !== null && (
                        <span className="text-gold font-bold"> · tu dino: {stacks} {entombWord(stacks)}</span>
                      )}
                    </>
                  )}
                </p>
              )}
              {g.key === "child" && ladderLine && (
                <p className="text-[9px] text-muted-foreground mb-1.5 leading-snug" data-testid="mutation-ladder-legend">
                  Se desbloquean con el crecimiento que tenía al guardarlo: {ladderLine}
                  {meta.growth_pct !== null && meta.growth_pct !== undefined && (
                    <span className="text-gold font-bold"> · tu dino: {meta.growth_pct}%{meta.is_prime ? " Prime" : ""}</span>
                  )}
                </p>
              )}
              {/* One slot per row at every width. The two-up variant keyed off
                  the VIEWPORT, but this editor sits in a narrow ~327px area of
                  the vault card, so on a desktop it split that into two ~150px
                  cards: mutation names truncated to "Augmente...", and a closed
                  row squeezed its reason into a 44px ribbon nine lines tall.
                  The narrow-viewport rendering was always the readable one, and
                  it is now what every width gets. (Wording note: Tailwind scans
                  comments, so this one names no utility.) */}
              <div className="grid grid-cols-1 gap-1.5">
                {g.slots.map((sid, i) => (
                  <SlotRow key={sid} slotId={sid} index={i + 1} value={slots[sid]} catalog={catalog}
                    lock={lockFor(sid)}
                    onEdit={() => openPicker(sid)} />
                ))}
              </div>
            </div>
            );
          })}
        </div>
      )}

      <AnimatePresence>
        {editingSlot && (
          <PickerModal
            open openToken={pickerOpens}
            slotId={editingSlot} slotValue={slots?.[editingSlot] ?? "None"} meta={meta}
            lock={lockFor(editingSlot)}
            usedNorms={usedNorms} busy={busy}
            pending={pending}
            onArm={(action, value) => setPending({ action, value })}
            onCancelPending={() => setPending(null)}
            // THE ONE THING THE CONFIRMING CONTROL CAN DO: save the value the
            // question was armed with. Reading the picker's live selection here
            // instead would let a changed pick be saved behind the old sentence.
            onConfirmPending={() => pending && doSet(editingSlot, pending.value)}
            onPick={(name) => doSet(editingSlot, name)}
            onClear={() => doSet(editingSlot, "None")}
            onClose={closePicker}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

export default MutationEditor;
