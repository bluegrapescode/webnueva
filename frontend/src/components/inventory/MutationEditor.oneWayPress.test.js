/**
 * EVERY PRESS THAT DESTROYS A STORED MUTATION, DRIVEN — not grepped.
 *
 * THE DEFECT THIS FILE EXISTS FOR, third appearance of one shape. The question
 * before an irreversible loss was wired to the FREE "Quitar (gratis)" press
 * only. The PAID "Confirmar" press, in the same picker, overwrote the identical
 * one-way value on a SINGLE press, with nothing on screen having said so, and
 * charged 20.000 PrimeMeat for it. Worked example, driven below: a parked Rex
 * whose ea1 holds "Cannibalistic" — a real registry name the bot writes and the
 * game rolls, which mutation_catalog deliberately keeps out of PICKABLE and
 * which vault.park captures verbatim. The server already answered
 * locked=false, clear_blocks_restore=true about that ranura. The player picked
 * any catalog mutation, pressed Confirmar once, paid, and "Cannibalistic" was
 * gone for good.
 *
 * THE RULE THIS FILE PINS, at the root rather than on one more button: any press
 * that would destroy a stored value the ranura will not take back asks first —
 * the free emptying AND the paid overwrite, on all sixteen ranuras — and the
 * answer comes from the server's per-ranura reversibility fields, never from
 * which control was pressed and never from which family the ranura is in. A
 * genuinely reversible press keeps its single press, because friction over a
 * move the player can undo is a defect of its own.
 *
 * THE FIXTURES ARE THE SERVER'S OWN OUTPUT. Every lock object below was dumped
 * from the real backend/mutation_catalog.py slot_lock_map for the row named
 * against it, so a payload here cannot quietly disagree with what the route
 * puts on the wire. The exhaustive proof that those fields predict the POST
 * (every ranura × every name × both diets, cleared or overwritten for real and
 * re-offered to the real validator) lives in
 * backend/tests_local/test_vault_mutation_edit.py, sections 13/1 and 13/1b.
 *
 * NEGATIVE CONTROLS, each run red before the repair:
 *   * wire the paid press straight to onPick again -> every "the paid press
 *     asks" case here saves on the first press;
 *   * arm the paid press from clear_blocks_restore instead of
 *     overwrite_blocks_restore -> "the last proof keeps its single paid press"
 *     fails, because that swap is reversible;
 *   * replace either generated sentence with a constant -> both sensitivity
 *     cases fail, since the sentence stops naming what is being lost.
 *
 * (Wording note: Tailwind scans test titles and comments under src/ as plain
 * tokens, and a bare utility word in prose emits real CSS. This file says
 * panel / press / notice / ranura / one-way, and reaches for elements by test
 * id rather than by class name.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

jest.mock("@/lib/api", () => ({ api: { meVaultMutations: jest.fn(), meVaultMutationSet: jest.fn() } }), { virtual: true });
jest.mock("@/context/SoundContext", () => ({ useSound: () => ({ play: () => {} }) }), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: () => {}, error: () => {} } }));
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));
// The same harsh stand-in the clear-confirm suite uses: once a child has been
// rendered it is never dropped, so a reopen always lands on the SAME instance
// and any state the picker kept for itself would still be there. Real
// AnimatePresence only holds a leaving child for the length of its exit and
// cancels that exit on a same-key return; holding it forever is the worst case
// of the same behaviour, so anything that passes here passes with a real exit.
jest.mock("framer-motion", () => {
  const R = require("react");
  return {
    motion: { div: ({ children, ...rest }) => R.createElement("div", rest, children) },
    AnimatePresence: ({ children }) => {
      const kept = R.useRef(null);
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

const COST = 20000;
const UNLOCKABLE = ["Osteophagic", "Reniculate Kidneys"];
const CARNI_CATALOG = ["Hemomania", "Nocturnal", "Wader", "Osteophagic", "Reniculate Kidneys"];
const HERBI_CATALOG = ["Truculency", "Nocturnal", "Wader", "Reniculate Kidneys"];

function norm(name) {
  return String(name || "").replace(/[\s_]+/g, "").toLowerCase();
}

/** An open ranura the server had nothing to warn about. */
const FREE = {
  locked: false, code: null, reason: null, requires_growth_pct: null,
  requires_prime: false, requires_entombs: null, clear_closes: false,
  clear_blocks_restore: false, overwrite_blocks_restore: false,
  holds_unlockable: false,
};
const lock = (over) => ({ ...FREE, ...over });

// ── THE CASES, one line each ────────────────────────────────────────────────
// `lock` is the server's real answer for the row in `row`; `asks` says whether
// each of the two destructive presses must stop and ask, and `why` is the
// reason that is true of that row. Everything below walks this list, so a case
// can never be covered on one press and forgotten on the other.
const CASES = [
  {
    id: "reversible",
    row: 'rex n1 = "Nocturnal"',
    slot: "n1", held: "Nocturnal", diet: "carnivore",
    lock: lock({}),
    asksOnClear: false, asksOnOverwrite: false,
    why: "the ranura offers it, the species carries it: he can simply put it back",
  },
  {
    id: "unlockable-in-n1",
    row: 'rex n1 = "Osteophagic"',
    slot: "n1", held: "Osteophagic", diet: "carnivore",
    lock: lock({ clear_blocks_restore: true, overwrite_blocks_restore: true, holds_unlockable: true }),
    asksOnClear: true, asksOnOverwrite: true, kind: "value",
    why: "the 1ª does not offer the mutations the game makes you unlock, so the save refuses it back",
  },
  {
    id: "unlockable-in-n2",
    row: 'rex n2 = "Osteophagic"',
    slot: "n2", held: "Osteophagic", diet: "carnivore",
    lock: lock({ holds_unlockable: true }),
    asksOnClear: false, asksOnOverwrite: false,
    why: "the 2ª offers every name, so the very same mutation goes straight back",
  },
  {
    id: "legacy-in-n1",
    row: 'rex n1 = "Cannibalistic"',
    slot: "n1", held: "Cannibalistic", diet: "carnivore",
    lock: lock({ clear_blocks_restore: true, overwrite_blocks_restore: true }),
    asksOnClear: true, asksOnOverwrite: true, kind: "value",
    why: "the catalog never carried that name, so no ranura takes it back",
  },
  {
    id: "legacy-in-ea1",
    row: 'rex ea1 = "Cannibalistic", 3 entierros',
    slot: "ea1", held: "Cannibalistic", diet: "carnivore",
    lock: lock({ clear_blocks_restore: true, overwrite_blocks_restore: true }),
    asksOnClear: true, asksOnOverwrite: true, kind: "value",
    why: "the reported case: an inherited ranura, wide open, holding a name nothing puts back",
  },
  {
    id: "diet-illegal",
    row: 'trike p1 = "Hemomania", 1 entierro',
    slot: "p1", held: "Hemomania", diet: "herbivore",
    lock: lock({ requires_entombs: 1, clear_blocks_restore: true, overwrite_blocks_restore: true }),
    asksOnClear: true, asksOnOverwrite: true, kind: "value",
    why: "a herbivore can never be given that name again, in this ranura or any other",
  },
  {
    id: "locked",
    row: 'rex n3 = "Nocturnal" at 50% growth',
    slot: "n3", held: "Nocturnal", diet: "carnivore",
    lock: lock({
      locked: true, code: "growth",
      reason: "Se desbloquea al 75% de crecimiento (ahora: 50%).",
      requires_growth_pct: 75,
      clear_blocks_restore: true, overwrite_blocks_restore: true,
    }),
    asksOnClear: true, asksOnOverwrite: null, kind: "locked",
    why: "the ladder refuses every write into it, so nothing goes back in",
  },
  {
    id: "last-proof",
    row: 'rex p1 = "Hemomania", counter at 0',
    slot: "p1", held: "Hemomania", diet: "carnivore",
    lock: lock({ requires_entombs: 1, clear_closes: true, clear_blocks_restore: true }),
    asksOnClear: true, asksOnOverwrite: false, kind: "lineage",
    why: "emptying it shuts all four heredadas; swapping it keeps them open, so only the emptying is one way",
  },
  {
    // BOTH REASONS AT ONCE. Dumped from the real slot_lock_map for a Triceratops
    // whose heredadas column holds "Hemomania" and whose counter is 0: the
    // stored name is a recognised one (so it proves the lineage and the four are
    // open) but a herbivore can never be given it, so the ranura will not take it
    // back either. overwrite_blocks_restore is what says the second half — it
    // asks the same question with the closing term switched off.
    id: "last-proof-and-value",
    row: 'trike p1 = "Hemomania", counter at 0',
    slot: "p1", held: "Hemomania", diet: "herbivore",
    lock: lock({
      requires_entombs: 1, clear_closes: true,
      clear_blocks_restore: true, overwrite_blocks_restore: true,
    }),
    asksOnClear: true, asksOnOverwrite: true,
    kind: "lineage_value", overwriteKind: "value",
    why: "emptying shuts the four AND the value cannot come back, so the lineage sentence alone would promise a return that entombing cannot deliver",
  },
];

/** The whole GET body, with one ranura holding one value. */
function payload(c, over = {}) {
  const names = c.diet === "herbivore" ? HERBI_CATALOG : CARNI_CATALOG;
  const slots = {};
  const slotLocks = {};
  for (const s of ALL_SLOTS) {
    slots[s] = s === c.slot ? c.held : "None";
    slotLocks[s] = s === c.slot ? { ...c.lock, ...(over.lock || {}) } : lock({});
  }
  return {
    dino_id: 1,
    slots,
    active_count: 1,
    max_slots: 16,
    elder_stacks: 3,
    slot_locks: slotLocks,
    growth_ladder: [
      { slot: "n1", index: 1, requires_growth_pct: 25, requires_prime: false },
      { slot: "n2", index: 2, requires_growth_pct: 50, requires_prime: false },
      { slot: "n3", index: 3, requires_growth_pct: 75, requires_prime: false },
      { slot: "n4", index: 4, requires_growth_pct: 75, requires_prime: true },
    ],
    entomb_ladder: ALL_SLOTS.slice(4).map((s) => ({ slot: s, generation: 1, requires_entombs: 1 })),
    growth_pct: 100,
    is_prime: true,
    unlocked: { child: true, parent: true, elder_a: true, elder_b: true },
    catalog: names.map((name) => ({
      name,
      restriction: name === "Hemomania" || name === "Osteophagic" ? "carnivore"
        : (name === "Truculency" ? "herbivore" : null),
      description: `desc ${name}`,
      unlockable: UNLOCKABLE.includes(name),
    })),
    // The sparse override the route really sends: only the ranuras whose offer
    // list differs travel, and an absent one offers the whole catalog.
    slot_catalog: {
      n1: names.filter((n) => !UNLOCKABLE.includes(n)),
      n3: names.filter((n) => !UNLOCKABLE.includes(n)),
    },
    unlockable_notice: "Algunas mutaciones hay que desbloquearlas jugando.",
    unlockable_kept_notice: "Esta ranura ya lleva una de esas mutaciones.",
    cost_per_change: COST,
    balance: 999999,
    ...over.body,
  };
}

const pick = (sel) => document.querySelector(sel);
const clearBtn = () => pick('[data-testid="mutation-picker-clear"]');
const payBtn = () => pick('[data-testid="mutation-picker-confirm"]');
const panel = () => pick('[data-testid="mutation-clear-warning"]');
const panelConfirm = () => pick('[data-testid="mutation-clear-confirm"]');
const notice = () => pick('[data-testid="mutation-oneway-notice"]');

async function press(el) {
  if (!el) throw new Error("nothing to press");
  await act(async () => {
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
}

/** Mount, wait out the GET, and open one ranura's picker. */
async function open(body, slotId) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  api.meVaultMutationSet.mockResolvedValue({
    data: {
      changed: true, charged: 0, slots: body.slots, active_count: 1,
      balance: 999999, elder_stacks: 3, slot_locks: body.slot_locks,
    },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  await press(host.querySelector(`[data-testid="mutation-edit-${slotId}"]`));
  return {
    host,
    cleanup: async () => { await act(async () => root.unmount()); host.remove(); },
    selectOption: async (name) => press(pick(`[data-testid="mutation-option-${norm(name)}"]`)),
  };
}

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

// ── the free press ──────────────────────────────────────────────────────────
describe("the FREE press asks exactly where the value cannot come back", () => {
  for (const c of CASES) {
    test(`${c.id}: emptying ${c.row} ${c.asksOnClear ? "asks" : "goes through on one press"}`,
      async () => {
        const r = await open(payload(c), c.slot);
        expect(panel()).toBeNull();
        await press(clearBtn());
        if (c.asksOnClear) {
          expect(api.meVaultMutationSet).not.toHaveBeenCalled();
          expect(panel()).not.toBeNull();
          expect(panel().getAttribute("data-action")).toBe("clear");
          expect(panel().getAttribute("data-clear-kind")).toBe(c.kind);
          // ...and the press that acts is the panel's own, which is free.
          expect(panelConfirm()).not.toBe(clearBtn());
          expect(panel().contains(panelConfirm())).toBe(true);
          expect(panelConfirm().textContent).toContain("(gratis)");
          await press(panelConfirm());
        }
        expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
        expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, c.slot, "None");
        await r.cleanup();
      });
  }
});

// ── the paid press ──────────────────────────────────────────────────────────
describe("the PAID press asks in exactly the same places, and nowhere else", () => {
  for (const c of CASES.filter((x) => x.asksOnOverwrite !== null)) {
    test(`${c.id}: overwriting ${c.row} ${c.asksOnOverwrite ? "asks" : "goes through on one press"}`,
      async () => {
        const r = await open(payload(c), c.slot);
        await r.selectOption("Wader");
        expect(panel()).toBeNull();
        await press(payBtn());
        if (c.asksOnOverwrite) {
          expect(api.meVaultMutationSet).not.toHaveBeenCalled();
          expect(panel()).not.toBeNull();
          expect(panel().getAttribute("data-action")).toBe("overwrite");
          // The PAID press can land on a different sentence than the free one on
          // the row where the two answers differ — the clear closes the family,
          // the swap does not — so the case says which one it expects.
          expect(panel().getAttribute("data-clear-kind")).toBe(c.overwriteKind || c.kind);
          expect(panelConfirm()).not.toBe(payBtn());
          expect(panel().contains(panelConfirm())).toBe(true);
          await press(panelConfirm());
        }
        expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
        expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, c.slot, "Wader");
        await r.cleanup();
      });
  }

  test("a closed ranura has no paid press at all, only the free way out", async () => {
    const c = CASES.find((x) => x.id === "locked");
    const r = await open(payload(c), c.slot);
    expect(payBtn()).toBeNull();
    expect(clearBtn()).not.toBeNull();
    expect(clearBtn().disabled).toBe(false);
    await r.cleanup();
  });

  // THE ONE ROW SHAPE WHERE THE TWO ANSWERS DIVERGE, spelled out on its own
  // because a single flag driving both presses gets exactly this case wrong.
  test("the last proof asks before the free press and NOT before the paid one",
    async () => {
      const c = CASES.find((x) => x.id === "last-proof");
      const a = await open(payload(c), c.slot);
      await press(clearBtn());
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(panel().getAttribute("data-clear-kind")).toBe("lineage");
      await a.cleanup();

      jest.clearAllMocks();
      document.body.innerHTML = "";
      const b = await open(payload(c), c.slot);
      await b.selectOption("Wader");
      await press(payBtn());
      expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "p1", "Wader");
      expect(panel()).toBeNull();
      await b.cleanup();
    });
});

// ── the price, and the money ────────────────────────────────────────────────
describe("the paid path still shows its price and still charges once", () => {
  const c = CASES.find((x) => x.id === "legacy-in-ea1");

  test("the confirming control carries the price, not just the word yes", async () => {
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(panelConfirm().textContent).toContain(Number(COST).toLocaleString("es"));
    expect(panelConfirm().textContent).toContain("PrimeMeat");
    // ...and it is not the free wording, which would be a lie about a 20.000 press.
    expect(panelConfirm().textContent).not.toContain("(gratis)");
    await r.cleanup();
  });

  test("confirming saves exactly once, with the picked value", async () => {
    api.meVaultMutationSet.mockResolvedValue({
      data: { changed: true, charged: COST, slots: {}, active_count: 1, balance: 979999 },
    });
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    await press(panelConfirm());
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "Wader");
    await r.cleanup();
  });

  test("backing out of the paid question saves nothing at all", async () => {
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(panel()).not.toBeNull();
    await press(payBtn());                       // the pressed button is the way out
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(panel()).toBeNull();
    expect(payBtn().getAttribute("data-armed")).toBe("0");
    await r.cleanup();
  });

  test("closing the picker on an armed paid question saves nothing", async () => {
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    await press(pick('[data-testid="mutation-picker-close"]'));
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    await r.cleanup();
  });
});

// ── a double press walks through neither ────────────────────────────────────
describe("a habitual double press cannot walk through either question", () => {
  for (const c of CASES.filter((x) => x.asksOnClear)) {
    test(`${c.id}: two presses on the free button arm and then back out`, async () => {
      const r = await open(payload(c), c.slot);
      const btn = clearBtn();
      await press(btn);
      expect(panel()).not.toBeNull();
      expect(btn.getAttribute("data-armed")).toBe("1");
      await press(btn);
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(panel()).toBeNull();
      expect(clearBtn().getAttribute("data-armed")).toBe("0");
      await r.cleanup();
    });
  }

  for (const c of CASES.filter((x) => x.asksOnOverwrite)) {
    test(`${c.id}: two presses on the paid button arm and then back out`, async () => {
      const r = await open(payload(c), c.slot);
      await r.selectOption("Wader");
      const btn = payBtn();
      await press(btn);
      expect(panel()).not.toBeNull();
      expect(btn.getAttribute("data-armed")).toBe("1");
      await press(btn);
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(panel()).toBeNull();
      await r.cleanup();
    });
  }

  test("walking from one question to the other destroys nothing on the way", async () => {
    const c = CASES.find((x) => x.id === "unlockable-in-n1");
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(clearBtn());                     // armed to empty it
    expect(panel().getAttribute("data-action")).toBe("clear");
    await press(payBtn());                       // ...now armed to overwrite it
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(panel().getAttribute("data-action")).toBe("overwrite");
    await press(clearBtn());                     // ...and back again
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(panel().getAttribute("data-action")).toBe("clear");
    await r.cleanup();
  });

  test("the question never outlives the open it was armed in", async () => {
    const c = CASES.find((x) => x.id === "legacy-in-ea1");
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(panel()).not.toBeNull();
    await press(pick('[data-testid="mutation-picker-close"]'));
    await press(r.host.querySelector('[data-testid="mutation-edit-ea1"]'));
    expect(panel()).toBeNull();
    // and the next paid press has to ASK again, not act
    await r.selectOption("Wader");
    await press(payBtn());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(panel()).not.toBeNull();
    await r.cleanup();
  });
});

// ── what the panel is allowed to save ───────────────────────────────────────
describe("the panel can only ever save what its own sentence described", () => {
  const c = CASES.find((x) => x.id === "legacy-in-ea1");

  // The two layers that keep them in step are independent on purpose, and this
  // is where the second one shows: a mutation is picked, but the press that was
  // armed is the FREE one, so the only thing the panel may save is the emptying.
  // A panel reading the picker's live selection would empty nothing and charge
  // 20.000 for a swap the player never asked for.
  test("an armed free press saves the emptying, never the mutation on screen",
    async () => {
      const r = await open(payload(c), c.slot);
      await r.selectOption("Wader");
      await press(clearBtn());
      expect(panel().getAttribute("data-action")).toBe("clear");
      expect(panel().textContent).toContain("Vas a quitar");
      expect(panel().textContent).not.toContain("Wader");
      await press(panelConfirm());
      expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "None");
      await r.cleanup();
    });

  test("changing the pick while armed cancels the question", async () => {
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(panel()).not.toBeNull();
    await r.selectOption("Nocturnal");
    expect(panel()).toBeNull();
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    await r.cleanup();
  });

  test("...and re-arming saves the NEW pick, the one the sentence names", async () => {
    const r = await open(payload(c), c.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    await r.selectOption("Nocturnal");
    await press(payBtn());
    expect(panel().textContent).toContain("Nocturnal");
    expect(panel().textContent).not.toContain("Wader");
    await press(panelConfirm());
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "Nocturnal");
    await r.cleanup();
  });
});

// ── the standing notice ─────────────────────────────────────────────────────
// The ONLY sentence that warned a change is one way had been narrowed to "holds
// one of the seven the game makes you unlock, in the 1ª or the 3ª". That left
// every other one-way value with nothing on screen at all: a legacy capture, a
// value the species cannot carry, anything sitting in a closed ranura — and on
// the fourteen ranuras that are not the 1ª or the 3ª there was no such copy in
// the first place.
describe("a ranura says a value cannot come back BEFORE anything is pressed", () => {
  for (const c of CASES) {
    const oneWay = c.asksOnClear;
    test(`${c.id}: the notice is ${oneWay ? "there" : "absent"} on open`, async () => {
      const r = await open(payload(c), c.slot);
      if (oneWay) {
        expect(notice()).not.toBeNull();
        expect(notice().textContent).toContain(c.held);
        expect(notice().getAttribute("data-clear-kind")).toBe(c.kind);
      } else {
        expect(notice()).toBeNull();
      }
      await r.cleanup();
    });
  }

  test("it reaches ranuras far outside the 1ª and the 3ª", async () => {
    for (const id of ["legacy-in-ea1", "diet-illegal", "locked", "last-proof"]) {
      const c = CASES.find((x) => x.id === id);
      const r = await open(payload(c), c.slot);
      expect(notice()).not.toBeNull();
      await r.cleanup();
      document.body.innerHTML = "";
    }
  });

  test("a closed ranura carries it too, where there is no offer list at all", async () => {
    const c = CASES.find((x) => x.id === "locked");
    const r = await open(payload(c), c.slot);
    expect(pick('[data-testid="mutation-picker-lock"]')).not.toBeNull();
    expect(notice()).not.toBeNull();
    expect(notice().textContent).toContain("Nocturnal");
    await r.cleanup();
  });

  test("the same fact is never said twice at once", async () => {
    const c = CASES.find((x) => x.id === "unlockable-in-n1");
    const r = await open(payload(c), c.slot);
    expect(notice()).not.toBeNull();
    await press(clearBtn());
    // while the question is up, the panel carries the sentence instead
    expect(notice()).toBeNull();
    expect(panel().textContent).toContain("Osteophagic");
    await press(clearBtn());
    expect(notice()).not.toBeNull();
    await r.cleanup();
  });

  test("the notice and the question say the same thing about the same ranura", async () => {
    const c = CASES.find((x) => x.id === "legacy-in-ea1");
    const r = await open(payload(c), c.slot);
    const standing = notice().textContent;
    await press(clearBtn());
    expect(panel().textContent).toContain(standing);
    await r.cleanup();
  });
});

// ── the wording is generated, not written down ──────────────────────────────
describe("the sentence says what is true of THIS ranura and THIS value", () => {
  test("two different stored values give two different sentences", async () => {
    const base = CASES.find((x) => x.id === "legacy-in-ea1");
    const seen = [];
    for (const held of ["Cannibalistic", "Traumatic Thrombosis"]) {
      const r = await open(payload({ ...base, held }), base.slot);
      await press(clearBtn());
      expect(panel().textContent).toContain(held);
      seen.push(panel().textContent);
      await r.cleanup();
      document.body.innerHTML = "";
      jest.clearAllMocks();
    }
    expect(seen[0]).not.toBe(seen[1]);
    expect(seen[0]).not.toContain("Traumatic Thrombosis");
    expect(seen[1]).not.toContain("Cannibalistic");
  });

  test("the standing notice names the value too", async () => {
    const base = CASES.find((x) => x.id === "legacy-in-ea1");
    const seen = [];
    for (const held of ["Cannibalistic", "Traumatic Thrombosis"]) {
      const r = await open(payload({ ...base, held }), base.slot);
      expect(notice().textContent).toContain(held);
      seen.push(notice().textContent);
      await r.cleanup();
      document.body.innerHTML = "";
    }
    expect(seen[0]).not.toBe(seen[1]);
  });

  // What the game captures is camel-case ("ReniculateKidneys"), and the sentence
  // has to name it the way the catalog spells it — the same name the ranura row
  // above shows — or the player is being warned about something he cannot see.
  test("a game-captured camel-case value is named the way the catalog spells it",
    async () => {
      const base = CASES.find((x) => x.id === "unlockable-in-n1");
      const c = { ...base, held: "ReniculateKidneys" };
      const r = await open(payload(c), c.slot);
      expect(notice().textContent).toContain("Reniculate Kidneys");
      expect(notice().textContent).not.toContain("«ReniculateKidneys»");
      await press(clearBtn());
      expect(panel().textContent).toContain("Vas a quitar «Reniculate Kidneys»");
      await r.cleanup();
    });

  test("each case gets the sentence that is true of it, and not the other two",
    async () => {
      const want = {
        "unlockable-in-n1": ["no podrás volver a ponerla aquí"],
        locked: ["no podrás volver a ponerle nada mientras la ranura siga bloqueada"],
        "last-proof": ["se cerrarán las cuatro", "hasta que entierres al dinosaurio"],
        // BOTH FACTS, because both are true of it and each half alone misleads.
        "last-proof-and-value": [
          "se cerrarán las cuatro",
          "ya no admite",
          "no podrá volver aquí",
        ],
      };
      const never = {
        "unlockable-in-n1": ["mientras la ranura siga bloqueada", "se cerrarán las cuatro"],
        locked: ["se cerrarán las cuatro"],
        "last-proof": ["mientras la ranura siga bloqueada"],
        // ...and never the promise the plain lineage sentence makes: entombing
        // the dinosaur reopens the four ranuras, but it does not bring THIS
        // value back, so the copy may not offer that as the way out.
        "last-proof-and-value": [
          "y no podrás volver a ponerla aquí, ni poner ninguna otra, hasta que",
          "mientras la ranura siga bloqueada",
        ],
      };
      for (const id of Object.keys(want)) {
        const c = CASES.find((x) => x.id === id);
        const r = await open(payload(c), c.slot);
        await press(clearBtn());
        for (const s of want[id]) expect(panel().textContent).toContain(s);
        for (const s of never[id]) expect(panel().textContent).not.toContain(s);
        await r.cleanup();
        document.body.innerHTML = "";
        jest.clearAllMocks();
      }
    });

  // ── THE COMBINED ROW, SIDE BY SIDE WITH THE PLAIN ONE ─────────────────────
  // Same ranura, same held name, same closing family. The ONE thing that differs
  // is the server's answer about the value itself (overwrite_blocks_restore), and
  // the sentence has to move with it: the plain last proof really does come back
  // once the dinosaur is buried again, and the herbivore's carnivore-only capture
  // never does. One sentence for both told the second player to go and bury a
  // dinosaur to get a mutation back that this ranura will not take at any point.
  test("the closing sentence promises a return ONLY where entombing delivers one",
    async () => {
      const plain = CASES.find((x) => x.id === "last-proof");
      const both = CASES.find((x) => x.id === "last-proof-and-value");

      const a = await open(payload(plain), plain.slot);
      await press(clearBtn());
      const plainText = panel().textContent;
      await a.cleanup();
      document.body.innerHTML = "";
      jest.clearAllMocks();

      const b = await open(payload(both), both.slot);
      await press(clearBtn());
      const bothText = panel().textContent;
      await b.cleanup();

      // both keep the biggest fact: the four ranuras close
      expect(plainText).toContain("se cerrarán las cuatro");
      expect(bothText).toContain("se cerrarán las cuatro");
      // ...and only the reversible one offers entombing as the way back
      expect(plainText).toContain("hasta que entierres al dinosaurio");
      expect(bothText).toContain("aunque entierres al dinosaurio");
      expect(bothText).toContain("no podrá volver aquí");
      expect(plainText).not.toBe(bothText);
      // the two rows are otherwise identical, so a constant sentence fails here
      expect(plainText).toContain("Hemomania");
      expect(bothText).toContain("Hemomania");
    });

  test("the question names the action: quitar for one press, cambiar for the other",
    async () => {
      const c = CASES.find((x) => x.id === "legacy-in-ea1");
      const a = await open(payload(c), c.slot);
      await press(clearBtn());
      expect(panel().textContent).toContain("Vas a quitar «Cannibalistic»");
      await a.cleanup();
      document.body.innerHTML = "";
      jest.clearAllMocks();
      const b = await open(payload(c), c.slot);
      await b.selectOption("Wader");
      await press(payBtn());
      expect(panel().textContent).toContain("Vas a cambiar «Cannibalistic» por «Wader»");
      await b.cleanup();
    });
});

// ── payloads this page has to survive ───────────────────────────────────────
describe("the server stays the only source of the answer", () => {
  const c = CASES.find((x) => x.id === "legacy-in-ea1");

  test("a payload that predates the paid field still asks, and says so honestly",
    async () => {
      const body = payload(c);
      for (const s of ALL_SLOTS) delete body.slot_locks[s].overwrite_blocks_restore;
      const r = await open(body, c.slot);
      await r.selectOption("Wader");
      await press(payBtn());
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(panel()).not.toBeNull();
      await r.cleanup();
    });

  test("...and on the one shape it cannot read, it says it cannot be sure", async () => {
    const lp = CASES.find((x) => x.id === "last-proof");
    const body = payload(lp);
    for (const s of ALL_SLOTS) delete body.slot_locks[s].overwrite_blocks_restore;
    const r = await open(body, lp.slot);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(panel().getAttribute("data-clear-kind")).toBe("unknown");
    expect(panel().textContent).toContain("no podemos asegurarte");
    // ...and never the closing wording, which is false about a swap.
    expect(panel().textContent).not.toContain("se cerrarán las cuatro");
    await r.cleanup();
  });

  // ── A RANURA THE PAYLOAD NEVER DESCRIBED ──────────────────────────────────
  // An absent lock OBJECT (not an absent field) made every question read false
  // at once: not locked, not closing, no clear_blocks_restore and no
  // overwrite_blocks_restore. So a ranura holding a one-way value took the
  // single unguarded press on BOTH controls — the fail-open shape this panel
  // exists to stop, arrived at from the one direction nothing tested. A missing
  // answer must ask, the way the server warns whenever it cannot tell.
  describe("a ranura missing from slot_locks entirely fails CLOSED", () => {
    const without = (id) => {
      const body = payload(CASES.find((x) => x.id === id));
      delete body.slot_locks[CASES.find((x) => x.id === id).slot];
      return body;
    };

    test("the premise: the payload really has no entry for that ranura", () => {
      const body = without("legacy-in-ea1");
      expect(body.slot_locks.ea1).toBeUndefined();
      expect("ea1" in body.slot_locks).toBe(false);
      expect(body.slots.ea1).toBe("Cannibalistic");
    });

    test("the free press asks instead of emptying it on one press", async () => {
      const r = await open(without("legacy-in-ea1"), "ea1");
      await press(clearBtn());
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(panel()).not.toBeNull();
      expect(panel().getAttribute("data-action")).toBe("clear");
      await press(panelConfirm());
      expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "None");
      await r.cleanup();
    });

    test("the paid press asks too, and charges nothing until it is answered",
      async () => {
        const r = await open(without("legacy-in-ea1"), "ea1");
        await r.selectOption("Wader");
        await press(payBtn());
        expect(api.meVaultMutationSet).not.toHaveBeenCalled();
        expect(panel()).not.toBeNull();
        expect(panel().getAttribute("data-action")).toBe("overwrite");
        await press(panelConfirm());
        expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "Wader");
        await r.cleanup();
      });

    test("the ranura says so before anything is pressed, and claims no reason",
      async () => {
        const r = await open(without("legacy-in-ea1"), "ea1");
        expect(notice()).not.toBeNull();
        expect(notice().textContent).toContain("Cannibalistic");
        expect(notice().getAttribute("data-clear-kind")).toBe("unknown");
        expect(notice().textContent).toContain("no podemos asegurarte");
        // ...and never a reason the payload never gave it.
        expect(notice().textContent).not.toContain("se cerrarán las cuatro");
        expect(notice().textContent).not.toContain("mientras la ranura siga bloqueada");
        expect(notice().textContent).not.toContain("La ranura te seguirá sirviendo");
        await r.cleanup();
      });

    test("both presses say the same unknown thing, each naming its own action",
      async () => {
        const a = await open(without("legacy-in-ea1"), "ea1");
        await press(clearBtn());
        expect(panel().getAttribute("data-clear-kind")).toBe("unknown");
        expect(panel().textContent).toContain("Vas a quitar «Cannibalistic»");
        await a.cleanup();
        document.body.innerHTML = "";
        jest.clearAllMocks();
        const b = await open(without("legacy-in-ea1"), "ea1");
        await b.selectOption("Wader");
        await press(payBtn());
        expect(panel().getAttribute("data-clear-kind")).toBe("unknown");
        expect(panel().textContent).toContain("Vas a cambiar «Cannibalistic» por «Wader»");
        await b.cleanup();
      });

    test("a ranura with no entry AND nothing stored still arms nothing",
      async () => {
        const c = { ...CASES[0], slot: "eb4", held: "None" };
        const body = payload(c);
        delete body.slot_locks.eb4;
        const r = await open(body, "eb4");
        expect(notice()).toBeNull();
        expect(clearBtn().disabled).toBe(true);
        await r.selectOption("Wader");
        await press(payBtn());
        expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "eb4", "Wader");
        expect(panel()).toBeNull();
        await r.cleanup();
      });

    test("a whole payload with no slot_locks at all behaves the same way",
      async () => {
        const body = payload(CASES.find((x) => x.id === "legacy-in-ea1"));
        delete body.slot_locks;
        const r = await open(body, "ea1");
        expect(notice()).not.toBeNull();
        await press(clearBtn());
        expect(api.meVaultMutationSet).not.toHaveBeenCalled();
        expect(panel()).not.toBeNull();
        await r.cleanup();
      });
  });

  test("a payload with neither field behaves exactly as it always did", async () => {
    const body = payload(c);
    for (const s of ALL_SLOTS) {
      delete body.slot_locks[s].overwrite_blocks_restore;
      delete body.slot_locks[s].clear_blocks_restore;
    }
    const r = await open(body, c.slot);
    expect(notice()).toBeNull();
    await r.selectOption("Wader");
    await press(payBtn());
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea1", "Wader");
    await r.cleanup();
  });

  test("the page obeys the flag wherever the server puts it", async () => {
    // an ordinary name, in an ordinary ranura, that the server says cannot come back
    const body = payload({ ...CASES[0], slot: "eb4", held: "Nocturnal" });
    body.slot_locks.eb4 = lock({ clear_blocks_restore: true, overwrite_blocks_restore: true });
    const r = await open(body, "eb4");
    expect(notice()).not.toBeNull();
    await r.selectOption("Wader");
    await press(payBtn());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(panel().getAttribute("data-clear-kind")).toBe("value");
    await r.cleanup();
  });

  test("the locks that come back with a save replace the ones the GET sent", async () => {
    // p2 reads as ordinary until p1 is emptied; then it is the last proof and
    // its own free press has to start asking.
    const body = payload(CASES.find((x) => x.id === "last-proof"));
    body.slots.p2 = "Nocturnal";
    body.slot_locks.p1 = lock({ requires_entombs: 1 });
    body.slot_locks.p2 = lock({ requires_entombs: 1 });
    const r = await open(body, "p1");
    api.meVaultMutationSet.mockResolvedValue({
      data: {
        changed: true, charged: 0, active_count: 1, balance: 999999, elder_stacks: 0,
        slots: { ...body.slots, p1: "None" },
        slot_locks: {
          ...body.slot_locks,
          p2: lock({ requires_entombs: 1, clear_closes: true, clear_blocks_restore: true }),
        },
      },
    });
    await press(clearBtn());                     // p1 was ordinary: one press
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "p1", "None");
    await press(r.host.querySelector('[data-testid="mutation-edit-p2"]'));
    expect(notice()).not.toBeNull();
    await press(clearBtn());
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(panel().getAttribute("data-clear-kind")).toBe("lineage");
    await r.cleanup();
  });
});

// ── nothing that was reversible got harder ──────────────────────────────────
describe("no friction is added where the player can simply put the value back", () => {
  test("an empty ranura arms nothing, on either press", async () => {
    const c = { ...CASES[0], held: "None" };
    const r = await open(payload(c), c.slot);
    expect(notice()).toBeNull();
    expect(clearBtn().disabled).toBe(true);
    await r.selectOption("Wader");
    await press(payBtn());
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "Wader");
    expect(panel()).toBeNull();
    await r.cleanup();
  });

  test("an ordinary swap on an ordinary ranura is still one press", async () => {
    for (const id of ["reversible", "unlockable-in-n2"]) {
      const c = CASES.find((x) => x.id === id);
      const r = await open(payload(c), c.slot);
      await r.selectOption("Wader");
      await press(payBtn());
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, c.slot, "Wader");
      expect(panel()).toBeNull();
      await r.cleanup();
      document.body.innerHTML = "";
      jest.clearAllMocks();
    }
  });

  test("the paid button keeps its own price and its own disabled rules", async () => {
    const c = CASES.find((x) => x.id === "legacy-in-ea1");
    const r = await open(payload(c, { body: { balance: 10 } }), c.slot);
    expect(payBtn().textContent).toContain(Number(COST).toLocaleString("es"));
    expect(payBtn().disabled).toBe(true);        // nothing picked yet
    await r.selectOption("Wader");
    expect(payBtn().disabled).toBe(true);        // ...and now: no PrimeMeat
    await press(payBtn());
    expect(panel()).toBeNull();
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    await r.cleanup();
  });
});
