/**
 * The irreversible-clear confirmation, driven — not grepped.
 *
 * Removing a mutation from a CLOSED own slot cannot be walked back: the same
 * rule that closed the slot refuses every write into it again, and a parked
 * dino's growth never moves. So that one case asks a second time. Two ways of
 * asking were wrong, and a source grep passed under both, so every check here
 * mounts the real MutationEditor with the real GET payload shape and presses
 * real buttons.
 *
 *  1. A CONFIRM THAT SURVIVED A REOPEN. The confirm used to live in the
 *     picker's own state, reset by an effect keyed on [slotId, open] — but
 *     `open` is passed as a literal and slotId does not change when the player
 *     closes the picker and reopens the SAME slot, so that effect never re-ran.
 *     The reset depended entirely on the child unmounting, which is not
 *     guaranteed: AnimatePresence keeps a leaving child on screen while it
 *     fades and CANCELS that exit when a same-key child returns, handing the
 *     player back the very same instance with the confirm still armed. One
 *     press then removed the mutation with no warning at all.
 *
 *  2. A CONFIRM ON THE SAME BUTTON. Arming and removing were one relabelled
 *     button in one place, with nothing in between, so a habitual double press
 *     — two separate events in two renders — armed and then removed, having
 *     shown the warning for a few milliseconds. Measured: the second press
 *     really did call the save endpoint with "None".
 *
 * THE AnimatePresence STAND-IN BELOW IS THE POINT OF THIS FILE. The other test
 * file's pass-through stub unmounts the picker the moment it closes, which is
 * exactly the assumption bug 1 lived under — under that stub the old code looks
 * correct. This one models the leaving-child window instead, and never
 * unmounts, which is harsher than the real library: anything that passes here
 * passes with a real exit too.
 *
 * NEGATIVE CONTROL: against the unfixed tree the double-press check saw
 * meVaultMutationSet(1, "n4", "None") and the reopen check saw the warning
 * still on screen. Both were run and both were red before the repair.
 *
 * (Wording note: Tailwind scans test titles and comments under src/, and a bare
 * utility word in a sentence ships real CSS. This file says growth / raise /
 * panel, and reaches for elements by test id rather than by class name.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

// "@" is a webpack-only alias, so these two resolve through virtual mocks
// rather than a change to the shared craco config.
jest.mock("@/lib/api", () => ({ api: { meVaultMutations: jest.fn(), meVaultMutationSet: jest.fn() } }), { virtual: true });
jest.mock("@/context/SoundContext", () => ({ useSound: () => ({ play: () => {} }) }), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: () => {}, error: () => {} } }));
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));
// jest hoists this factory above the requires, so react is pulled in here.
jest.mock("framer-motion", () => {
  const R = require("react");
  return {
    motion: { div: ({ children, ...rest }) => R.createElement("div", rest, children) },
    // The leaving-child window, modelled: once a child has been rendered it is
    // never dropped, so a reopen always lands on the SAME instance and any
    // state the picker kept for itself would still be there. Real
    // AnimatePresence only holds the child for the length of the exit and
    // cancels that exit on a same-key return; holding it forever is the worst
    // case of the same behaviour.
    AnimatePresence: ({ children }) => {
      const kept = R.useRef(null);
      // toArray already drops null/undefined children, so an empty result is
      // "the parent closed it".
      if (R.Children.toArray(children).length) { kept.current = children; return children; }
      return kept.current;
    },
  };
});

const { api } = require("@/lib/api");
const { MutationEditor } = require("./MutationEditor");

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const ALL_SLOTS = ["n1", "n2", "n3", "n4", "p1", "p2", "p3", "p4",
  "ea1", "ea2", "ea3", "ea4", "eb1", "eb2", "eb3", "eb4"];
const OPEN_LOCK = { locked: false, code: null, reason: null, requires_growth_pct: null, requires_prime: false };
const PRIME_LOCK = {
  locked: true, code: "prime",
  reason: "La cuarta mutación propia es solo para dinosaurios Prime.",
  requires_growth_pct: 75, requires_prime: true,
};

/** The whole GET /me/vault/{id}/mutations body, all 16 slots described. */
function payload(values = {}, locks = {}) {
  const slots = {};
  const slotLocks = {};
  for (const s of ALL_SLOTS) {
    slots[s] = values[s] || "None";
    slotLocks[s] = locks[s] || OPEN_LOCK;
  }
  return {
    dino_id: 1, slots, active_count: 1, max_slots: 16, elder_stacks: 0,
    slot_locks: slotLocks,
    growth_ladder: [
      { slot: "n1", index: 1, requires_growth_pct: 25, requires_prime: false },
      { slot: "n2", index: 2, requires_growth_pct: 50, requires_prime: false },
      { slot: "n3", index: 3, requires_growth_pct: 75, requires_prime: false },
      { slot: "n4", index: 4, requires_growth_pct: 75, requires_prime: true },
    ],
    growth_pct: 100, is_prime: false,
    unlocked: { child: true, parent: true, elder_a: true, elder_b: true },
    catalog: [
      { name: "Hemomania", restriction: "carnivore", description: "Daño extra." },
      { name: "Nocturnal", restriction: null, description: "Visión de noche." },
    ],
    cost_per_change: 20000, balance: 999999,
  };
}

/** A locked 4th own slot that still holds a mutation: the irreversible case. */
const LOCKED_WITH_VALUE = () => payload({ n4: "Hemomania" }, { n4: PRIME_LOCK });

async function mount(body) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  api.meVaultMutationSet.mockResolvedValue({
    data: { slots: {}, active_count: 0, charged: 0, balance: 999999 },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  return { host, root };
}

/** One real press, in its own render pass — a double press is two of these,
 *  which is what a mouse actually delivers. */
async function press(el) {
  if (!el) throw new Error("nothing to press");
  await act(async () => {
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
}

const pick = (sel) => document.querySelector(sel);
const armButton = () => pick('[data-testid="mutation-picker-clear"]');
const confirmButton = () => pick('[data-testid="mutation-clear-confirm"]');
const warning = () => pick('[data-testid="mutation-clear-warning"]');
const openSlot = (host, sid) => press(host.querySelector(`[data-testid="mutation-edit-${sid}"]`));

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

describe("removing a mutation from a closed slot asks first, on a control of its own", () => {
  test("a double press arms and then backs out, and removes nothing", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    const btn = armButton();
    await press(btn);
    // press 1 has to be the press that reveals the warning, or the second one
    // is not walking through anything.
    expect(warning()).not.toBeNull();
    expect(btn.getAttribute("data-armed")).toBe("1");
    await press(btn);
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(warning()).toBeNull();
    expect(armButton().getAttribute("data-armed")).toBe("0");
  });

  test("the press that removes is a different element from the press that asks", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    await press(armButton());
    const confirmEl = confirmButton();
    expect(confirmEl).not.toBeNull();
    expect(confirmEl).not.toBe(armButton());
    // ...and it lives inside the warning itself, so it cannot be sitting where
    // the first press landed.
    expect(warning().contains(confirmEl)).toBe(true);
    expect(warning().contains(armButton())).toBe(false);
  });

  test("the confirm control really does remove the mutation", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    await press(armButton());
    await press(confirmButton());
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n4", "None");
  });

  test("both ways of removing say plainly that it is free", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    expect(armButton().textContent).toContain("(gratis)");
    await press(armButton());
    expect(confirmButton().textContent).toContain("(gratis)");
  });

  test("the warning states what is lost, not how many presses to give it", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    await press(armButton());
    expect(warning().textContent)
      .toContain("no podrás volver a ponerle nada mientras la ranura siga bloqueada");
    // The old copy told the player to press the same button again. That is the
    // instruction that got him a removal on a double press.
    expect(warning().textContent).not.toContain("Pulsa otra vez");
  });
});

describe("the confirmation never outlives the open it was armed in", () => {
  test("closing and reopening the SAME slot comes back unarmed", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    await press(armButton());
    expect(warning()).not.toBeNull();

    await press(pick('[data-testid="mutation-picker-close"]'));
    await openSlot(host, "n4");

    expect(warning()).toBeNull();
    expect(armButton().getAttribute("data-armed")).toBe("0");
    // The real thing this protects: the next single press must ASK, not remove.
    await press(armButton());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(warning()).not.toBeNull();
  });

  test("dismissing with the backdrop leaves nothing armed either", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    await openSlot(host, "n4");
    await press(armButton());
    // the overlay behind the card is the other way out of the picker
    await press(pick('[data-testid="mutation-picker-backdrop"]'));
    await openSlot(host, "n4");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
  });

  test("arming one closed slot does not arm another one", async () => {
    const { host } = await mount(payload(
      { n3: "Nocturnal", n4: "Hemomania" },
      {
        n3: {
          locked: true, code: "growth",
          reason: "Se desbloquea al 75% de crecimiento (ahora: 50%).",
          requires_growth_pct: 75, requires_prime: false,
        },
        n4: PRIME_LOCK,
      }));
    await openSlot(host, "n4");
    await press(armButton());
    expect(warning()).not.toBeNull();
    await press(pick('[data-testid="mutation-picker-close"]'));
    await openSlot(host, "n3");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
  });

  test("the search text does not follow the player into the next open", async () => {
    const { host } = await mount(payload({ n1: "Hemomania" }));
    await openSlot(host, "n1");
    const search = pick('[data-testid="mutation-picker-search"]');
    await act(async () => {
      search.value = "noct";
      search.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    expect(pick('[data-testid="mutation-picker-search"]').value).toBe("noct");
    await press(pick('[data-testid="mutation-picker-close"]'));
    await openSlot(host, "n1");
    expect(pick('[data-testid="mutation-picker-search"]').value).toBe("");
  });
});

describe("an open slot is not made harder to use by any of this", () => {
  test("one press still empties an open slot", async () => {
    const { host } = await mount(payload({ n1: "Hemomania" }));
    await openSlot(host, "n1");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
    expect(warning()).toBeNull();
  });

  test("an open slot's button never claims to be a question", async () => {
    const { host } = await mount(payload({ n1: "Hemomania" }));
    await openSlot(host, "n1");
    expect(armButton().getAttribute("data-armed")).toBe("0");
    expect(armButton().textContent).toContain("Quitar (gratis)");
    expect(confirmButton()).toBeNull();
  });

  test("a closed slot that holds nothing cannot be opened at all", async () => {
    const { host } = await mount(payload({}, { n4: PRIME_LOCK }));
    const btn = host.querySelector('[data-testid="mutation-edit-n4"]');
    expect(btn.disabled).toBe(true);
  });

  test("a closed slot that holds something keeps its way out", async () => {
    const { host } = await mount(LOCKED_WITH_VALUE());
    const btn = host.querySelector('[data-testid="mutation-edit-n4"]');
    expect(btn.disabled).toBe(false);
    await press(btn);
    expect(armButton().disabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// THE SECOND IRREVERSIBLE CASE (2026-07-26): an OPEN heredada that is the row's
// only proof of its own lineage.
//
// The server opens p1..p4 on a dino whose entierro counter says 0 when the
// heredadas column already holds a real mutation -- a dino bought with "Linaje
// Parental" is exactly that shape, and those four mutations were PAID for. But
// the gate is derived FROM that column, so emptying the last one takes the gate's
// own evidence with it and shuts all four, and re-adding is then refused until
// the dino is buried in game. Measured against the real backend module: p1..p4
// usable -> one press on p1 -> nothing usable, and the re-add answers "Se
// desbloquea cuando el dinosaurio ha sido enterrado al menos 1 vez (ahora: 0)".
//
// Before the derivation those ranuras were LOCKED, so the very same press went
// down the two-press path above. The derivation had moved the irreversible case
// into the one-press path, whose own comment says the player "can simply put it
// back" -- which is precisely what he cannot do here.
//
// The server decides it, per slot, and sends slot_locks[slot].clear_closes. This
// file never re-derives the rule: it feeds the flag in and presses buttons.
//
// NEGATIVE CONTROL: gate the confirmation on isLocked alone again and the first
// three cases here fail -- the press saves straight away with no warning shown.
const LINEAGE_OPEN = { ...OPEN_LOCK, requires_entombs: 1, clear_closes: true };
const LINEAGE_SIBLING = { ...OPEN_LOCK, requires_entombs: 1, clear_closes: false };

/** The store dino: counter at 0, one paid heredada in p1 holding the family up. */
const LAST_PROOF = () => payload(
  { p1: "Hemomania" },
  { p1: LINEAGE_OPEN, p2: LINEAGE_SIBLING, p3: LINEAGE_SIBLING, p4: LINEAGE_SIBLING });

describe("emptying the last heredada asks first, even though the ranura is usable", () => {
  test("the first press asks instead of removing", async () => {
    const { host } = await mount(LAST_PROOF());
    await openSlot(host, "p1");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(warning()).not.toBeNull();
    expect(armButton().getAttribute("data-armed")).toBe("1");
  });

  test("a habitual double press backs out and removes nothing", async () => {
    const { host } = await mount(LAST_PROOF());
    await openSlot(host, "p1");
    const btn = armButton();
    await press(btn);
    await press(btn);
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(warning()).toBeNull();
  });

  test("the control that removes is a different one, and it does remove", async () => {
    const { host } = await mount(LAST_PROOF());
    await openSlot(host, "p1");
    await press(armButton());
    const confirmEl = confirmButton();
    expect(confirmEl).not.toBe(armButton());
    expect(warning().contains(confirmEl)).toBe(true);
    expect(confirmEl.textContent).toContain("(gratis)");
    await press(confirmEl);
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "p1", "None");
  });

  test("the warning says what is really lost: the whole family, not one ranura",
    async () => {
      const { host } = await mount(LAST_PROOF());
      await openSlot(host, "p1");
      await press(armButton());
      expect(warning().getAttribute("data-clear-kind")).toBe("lineage");
      expect(warning().textContent).toContain("se cerrarán las cuatro");
      expect(warning().textContent).toContain("hasta que entierres al dinosaurio");
      // ...and NOT the closed-ranura wording, which promises the wrong thing
      // here: this ranura is usable right now.
      expect(warning().textContent)
        .not.toContain("mientras la ranura siga bloqueada");
    });

  test("a usable ranura still shows the catalog behind the question", async () => {
    const { host } = await mount(LAST_PROOF());
    await openSlot(host, "p1");
    await press(armButton());
    expect(warning()).not.toBeNull();
    // The whole point of it being usable: he can still swap the mutation for
    // another instead of throwing it away.
    expect(pick('[data-testid="mutation-option-nocturnal"]')).not.toBeNull();
    expect(pick('[data-testid="mutation-picker-confirm"]')).not.toBeNull();
  });

  test("a sibling ranura in the same family keeps its one-press emptying", async () => {
    const { host } = await mount(payload(
      { p1: "Hemomania", p2: "Nocturnal" },
      { p1: LINEAGE_SIBLING, p2: LINEAGE_SIBLING }));
    await openSlot(host, "p2");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "p2", "None");
  });

  test("the flag never arms anything on a ranura that holds nothing", async () => {
    const { host } = await mount(payload({}, { p1: LINEAGE_OPEN }));
    expect(host.querySelector('[data-testid="mutation-edit-p1"]').disabled).toBe(false);
    await openSlot(host, "p1");
    expect(armButton().disabled).toBe(true);
    expect(warning()).toBeNull();
  });

  test("the question does not survive a close and a reopen", async () => {
    const { host } = await mount(LAST_PROOF());
    await openSlot(host, "p1");
    await press(armButton());
    expect(warning()).not.toBeNull();
    await press(pick('[data-testid="mutation-picker-close"]'));
    await openSlot(host, "p1");
    expect(warning()).toBeNull();
    await press(armButton());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
  });
});

describe("the save hands back the ranura state it just changed", () => {
  test("the locks that come back with the save replace the ones the GET sent",
    async () => {
      const { host } = await mount(payload(
        { p1: "Hemomania", p2: "Nocturnal" },
        { p1: LINEAGE_SIBLING, p2: LINEAGE_SIBLING }));
      // Emptying p1 leaves p2 as the only proof, so the server now flags p2.
      api.meVaultMutationSet.mockResolvedValue({
        data: {
          slots: { ...LAST_PROOF().slots, p1: "None", p2: "Nocturnal" },
          active_count: 1, charged: 0, balance: 999999, elder_stacks: 0,
          slot_locks: { ...LAST_PROOF().slot_locks, p2: LINEAGE_OPEN },
        },
      });
      await openSlot(host, "p1");
      await press(armButton());
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "p1", "None");
      // The next press on p2 must now ASK. Holding the map the GET sent is what
      // would let it remove on one press.
      await openSlot(host, "p2");
      await press(armButton());
      expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
      expect(warning()).not.toBeNull();
      expect(warning().getAttribute("data-clear-kind")).toBe("lineage");
    });

  test("a save that carries no locks leaves the ones already on screen alone",
    async () => {
      const { host } = await mount(payload(
        { p1: "Hemomania", p2: "Nocturnal" },
        { p1: LINEAGE_SIBLING, p2: LINEAGE_OPEN }));
      api.meVaultMutationSet.mockResolvedValue({
        data: {
          slots: { ...LAST_PROOF().slots, p1: "None", p2: "Nocturnal" },
          active_count: 1, charged: 0, balance: 1,
        },
      });
      await openSlot(host, "p1");
      await press(armButton());
      await openSlot(host, "p2");
      await press(armButton());
      expect(warning()).not.toBeNull();
    });
});
