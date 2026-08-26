/**
 * The twelve inherited slots, rendered — not grepped.
 *
 * Owner ruling 2026-07-26: one entierro opens the four heredadas, two open
 * Anciano A, three open Anciano B. Until then the editor drew six of the
 * sixteen slots and the other ten were simply left out of the page, so nothing
 * about them could be wrong on screen. Now they are all drawn, and a closed one
 * has to explain itself, keep its way out, and never invent a requirement of
 * its own — every number on screen comes from the server's entomb_ladder.
 *
 * The Python suite (backend/tests_local/test_vault_mutation_edit.py) owns the
 * rule itself; what it cannot see is what a player ends up reading and pressing,
 * so that lives here: the REAL MutationEditor is mounted with the REAL payload
 * shape slot_lock_map + me_vault_mutations put on the wire, real buttons are
 * pressed, and the panel is read back.
 *
 * NEGATIVE CONTROL: with the inherited families removed from GROUPS every
 * "is drawn" case here fails; with the requirement written into the component
 * instead of read from entomb_ladder, the "server moves the number" case fails.
 *
 * (Wording note: Tailwind scans test titles and comments under src/, and a bare
 * utility word in a sentence ships a real CSS rule. This file says drawn /
 * closed / open / panel / emptied, and reaches for elements by test id.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

// "@" is a webpack-only alias, so these two resolve through virtual mocks
// rather than a change to the shared craco config.
jest.mock("@/lib/api", () => ({ api: { meVaultMutations: jest.fn(), meVaultMutationSet: jest.fn() } }), { virtual: true });
jest.mock("@/context/SoundContext", () => ({ useSound: () => ({ play: () => {} }) }), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: () => {}, error: () => {} } }));
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));
jest.mock("framer-motion", () => {
  const R = require("react");
  return {
    motion: { div: ({ children, ...rest }) => R.createElement("div", rest, children) },
    AnimatePresence: ({ children }) => children,
  };
});

const { api } = require("@/lib/api");
const { MutationEditor } = require("./MutationEditor");

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const OWN = ["n1", "n2", "n3", "n4"];
const PARENT = ["p1", "p2", "p3", "p4"];
const ELDER_A = ["ea1", "ea2", "ea3", "ea4"];
const ELDER_B = ["eb1", "eb2", "eb3", "eb4"];
const ALL_SLOTS = [...OWN, ...PARENT, ...ELDER_A, ...ELDER_B];
const NEEDS = { p: 1, ea: 2, eb: 3 };

/** mutation_catalog._entomb_reason, in the exact Spanish the server sends. */
function entombReason(need, have) {
  return `Se desbloquea cuando el dinosaurio ha sido enterrado al menos ${need} `
    + `${need === 1 ? "vez" : "veces"} (ahora: ${have}).`;
}

/** The whole GET /me/vault/{id}/mutations body for a dino with `stacks`
 *  entierros, built the way mutation_catalog.slot_lock_map builds it. */
function payload({ stacks = 0, values = {}, ladder = true } = {}) {
  const slots = {};
  const slotLocks = {};
  for (const s of ALL_SLOTS) {
    slots[s] = values[s] || "None";
    const need = NEEDS[s.replace(/\d/g, "")] || null;
    const closed = need !== null && (stacks === null || stacks < need);
    slotLocks[s] = {
      locked: closed,
      code: closed ? (stacks === null ? "entomb_unknown" : "entomb") : null,
      reason: closed
        ? (stacks === null
          ? "No se pudo leer cuántas veces se ha enterrado a este dinosaurio, así que la "
            + "ranura queda bloqueada. Vuelve a guardarlo en la bóveda o avisa a un admin."
          : entombReason(need, stacks))
        : null,
      requires_growth_pct: null,
      requires_prime: false,
      requires_entombs: need,
    };
  }
  return {
    dino_id: 1, slots, active_count: 0, max_slots: 16, elder_stacks: stacks,
    slot_locks: slotLocks,
    growth_ladder: [
      { slot: "n1", index: 1, requires_growth_pct: 25, requires_prime: false },
      { slot: "n2", index: 2, requires_growth_pct: 50, requires_prime: false },
      { slot: "n3", index: 3, requires_growth_pct: 75, requires_prime: false },
      { slot: "n4", index: 4, requires_growth_pct: 75, requires_prime: true },
    ],
    entomb_ladder: ladder
      ? ALL_SLOTS.filter((s) => NEEDS[s.replace(/\d/g, "")])
        .map((s) => ({ slot: s, generation: NEEDS[s.replace(/\d/g, "")],
          requires_entombs: NEEDS[s.replace(/\d/g, "")] }))
      : [],
    growth_pct: 100, is_prime: true,
    unlocked: { child: true, parent: stacks >= 1, elder_a: stacks >= 2, elder_b: stacks >= 3 },
    catalog: [
      { name: "Hemomania", restriction: "carnivore", description: "Daño extra." },
      { name: "Nocturnal", restriction: null, description: "Visión de noche." },
      { name: "Wader", restriction: null, description: "Vadea mejor." },
    ],
    cost_per_change: 20000, balance: 999999,
  };
}

async function mount(body) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  api.meVaultMutationSet.mockResolvedValue({
    data: { slots: body.slots, active_count: 0, charged: 0, balance: 999999 },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  return { host, root };
}

async function press(el) {
  if (!el) throw new Error("nothing to press");
  await act(async () => {
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
}

const pick = (sel) => document.querySelector(sel);
const slotRow = (host, sid) => host.querySelector(`[data-testid="mutation-slot-${sid}"]`);
const slotButton = (host, sid) => host.querySelector(`[data-testid="mutation-edit-${sid}"]`);
const groupText = (host, key) =>
  host.querySelector(`[data-testid="mutation-group-${key}"]`).textContent;

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

describe("all sixteen slots are on the page, closed ones included", () => {
  test("a never-entombed dino still gets every family drawn", async () => {
    const { host } = await mount(payload({ stacks: 0 }));
    for (const key of ["child", "parent", "elder_a", "elder_b"]) {
      expect(host.querySelector(`[data-testid="mutation-group-${key}"]`)).not.toBeNull();
    }
    const missing = ALL_SLOTS.filter((s) => !slotRow(host, s));
    expect(missing).toEqual([]);
  });

  test("its twelve inherited slots are marked closed and its four own ones are not",
    async () => {
      const { host } = await mount(payload({ stacks: 0 }));
      const closed = ALL_SLOTS.filter((s) => slotRow(host, s).getAttribute("data-locked") === "1");
      expect(closed).toEqual([...PARENT, ...ELDER_A, ...ELDER_B]);
    });

  test("each rung really opens the families the owner said it does", async () => {
    const expected = {
      0: [],
      1: PARENT,
      2: [...PARENT, ...ELDER_A],
      3: [...PARENT, ...ELDER_A, ...ELDER_B],
      7: [...PARENT, ...ELDER_A, ...ELDER_B],
    };
    for (const stacks of [0, 1, 2, 3, 7]) {
      const { host, root } = await mount(payload({ stacks }));
      const open = [...PARENT, ...ELDER_A, ...ELDER_B]
        .filter((s) => slotRow(host, s).getAttribute("data-locked") === "0");
      expect({ stacks, open }).toEqual({ stacks, open: expected[stacks] });
      await act(async () => root.unmount());
      document.body.innerHTML = "";
    }
  });

  test("a closed inherited slot prints the server's own reason next to it", async () => {
    const { host } = await mount(payload({ stacks: 1 }));
    expect(host.querySelector('[data-testid="mutation-lock-reason-ea1"]').textContent)
      .toContain(entombReason(2, 1));
    expect(host.querySelector('[data-testid="mutation-lock-reason-eb4"]').textContent)
      .toContain(entombReason(3, 1));
    // an open family has nothing to explain
    expect(host.querySelector('[data-testid="mutation-lock-reason-p1"]')).toBeNull();
  });
});

describe("the requirement on screen is the server's number, not one of ours", () => {
  test("each family names how many entierros it needs", async () => {
    const { host } = await mount(payload({ stacks: 0 }));
    expect(groupText(host, "parent")).toContain("1 entierro");
    expect(groupText(host, "elder_a")).toContain("2 entierros");
    expect(groupText(host, "elder_b")).toContain("3 entierros");
    // the own family is on the other ladder and says nothing about entierros
    expect(groupText(host, "child")).not.toContain("entierro");
  });

  test("moving the ladder on the wire moves what the page says", async () => {
    const body = payload({ stacks: 0 });
    body.entomb_ladder = body.entomb_ladder.map((r) => ({ ...r, requires_entombs: 5 }));
    const { host } = await mount(body);
    expect(groupText(host, "parent")).toContain("5 entierros");
    expect(groupText(host, "elder_b")).toContain("5 entierros");
  });

  test("a server that sends no ladder makes the page say nothing about entierros",
    async () => {
      const { host } = await mount(payload({ stacks: 0, ladder: false }));
      expect(host.querySelector('[data-testid="mutation-entomb-legend-parent"]')).toBeNull();
      expect(groupText(host, "parent")).not.toContain("entierro");
      // and the slots are still there, still closed, still explained
      expect(slotRow(host, "p1").getAttribute("data-locked")).toBe("1");
      expect(host.querySelector('[data-testid="mutation-lock-reason-p1"]').textContent)
        .toContain("enterrado");
    });

  test("the legend counts the entierros the dino actually has", async () => {
    const { host } = await mount(payload({ stacks: 1 }));
    const legend = host.querySelector('[data-testid="mutation-entomb-legend-elder_a"]').textContent;
    // BOTH words, and they are not interchangeable: after the participle it is
    // "enterrado al menos 2 veces", while the dino's own tally is a count of
    // "entierros". Saying "enterrado al menos 2 entierros" shipped once and sat
    // directly above a per-slot reason that said "2 veces" correctly.
    expect(legend).toContain("al menos 2 veces");
    expect(legend).not.toContain("al menos 2 entierros");
    expect(legend).toContain("tu dino: 1 entierro");
    expect(legend).not.toContain("tu dino: 1 entierros");
  });

  test("an unreadable count is never printed as zero", async () => {
    const { host } = await mount(payload({ stacks: null }));
    const legend = host.querySelector('[data-testid="mutation-entomb-legend-parent"]').textContent;
    expect(legend).not.toContain("tu dino");
    expect(legend).not.toContain("0 entierros");
    expect(slotRow(host, "p1").getAttribute("data-locked")).toBe("1");
  });
});

describe("the count chip and the duplicate list stay honest at sixteen", () => {
  test("the chip counts every slot on the page, own and inherited", async () => {
    const { host } = await mount(payload({
      stacks: 3, values: { n1: "Hemomania", p2: "Nocturnal", eb4: "Wader" },
    }));
    expect(host.querySelector('[data-testid="mutation-active-count"]').textContent)
      .toBe("3/16 activas");
  });

  test("an empty dino reads 0 of 16", async () => {
    const { host } = await mount(payload({ stacks: 3 }));
    expect(host.querySelector('[data-testid="mutation-active-count"]').textContent)
      .toBe("0/16 activas");
  });

  test("a mutation sitting in a closed inherited slot still counts as in use",
    async () => {
      const { host } = await mount(payload({ stacks: 0, values: { eb3: "Nocturnal" } }));
      await press(slotButton(host, "n1"));
      const option = pick('[data-testid="mutation-option-nocturnal"]');
      expect(option.disabled).toBe(true);
      expect(option.textContent).toContain("En uso");
      // ...and one that is nowhere is still pickable
      expect(pick('[data-testid="mutation-option-wader"]').disabled).toBe(false);
    });
});

describe("nothing is ever trapped in a closed inherited slot", () => {
  test("a closed inherited slot that holds something keeps its way out", async () => {
    const { host } = await mount(payload({ stacks: 0, values: { ea1: "Hemomania" } }));
    const btn = slotButton(host, "ea1");
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toContain("Quitar");
    await press(btn);
    expect(pick('[data-testid="mutation-picker-clear"]').disabled).toBe(false);
  });

  test("a closed inherited slot holding nothing cannot be opened at all", async () => {
    const { host } = await mount(payload({ stacks: 0 }));
    expect(slotButton(host, "ea1").disabled).toBe(true);
  });

  test("emptying it asks first, and a double press backs out instead", async () => {
    const { host } = await mount(payload({ stacks: 0, values: { eb2: "Hemomania" } }));
    await press(slotButton(host, "eb2"));
    const arm = pick('[data-testid="mutation-picker-clear"]');
    await press(arm);
    expect(pick('[data-testid="mutation-clear-warning"]')).not.toBeNull();
    await press(arm);
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(pick('[data-testid="mutation-clear-warning"]')).toBeNull();
  });

  test("the second control really does empty it, free", async () => {
    const { host } = await mount(payload({ stacks: 0, values: { eb2: "Hemomania" } }));
    await press(slotButton(host, "eb2"));
    await press(pick('[data-testid="mutation-picker-clear"]'));
    const confirm = pick('[data-testid="mutation-clear-confirm"]');
    expect(confirm.textContent).toContain("(gratis)");
    await press(confirm);
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "eb2", "None");
  });

  test("an OPEN inherited slot empties on one press, with no question", async () => {
    const { host } = await mount(payload({ stacks: 3, values: { ea2: "Hemomania" } }));
    await press(slotButton(host, "ea2"));
    expect(pick('[data-testid="mutation-clear-warning"]')).toBeNull();
    await press(pick('[data-testid="mutation-picker-clear"]'));
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea2", "None");
  });

  test("an open inherited slot can still be given a new mutation, for the price",
    async () => {
      const { host } = await mount(payload({ stacks: 2 }));
      await press(slotButton(host, "ea3"));
      await press(pick('[data-testid="mutation-option-wader"]'));
      await press(pick('[data-testid="mutation-picker-confirm"]'));
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "ea3", "Wader");
    });
});

describe("the advice under a closed inherited slot is true for its own code", () => {
  test('code "entomb" sends the player to bury the dino, not to raise it', async () => {
    const { host } = await mount(payload({ stacks: 0, values: { p1: "Hemomania" } }));
    await press(slotButton(host, "p1"));
    const howto = pick('[data-testid="mutation-lock-howto"]');
    expect(howto.getAttribute("data-lock-code")).toBe("entomb");
    expect(howto.textContent).toContain("enterrarlo en el juego");
    expect(howto.textContent).not.toContain("hacerlo crecer en el juego");
    expect(pick('[data-testid="mutation-picker-lock"]').textContent)
      .toContain("Lo que ya tiene guardado sigue ahí mientras tú no lo quites.");
  });

  test('code "entomb_unknown" leans on its own reason and adds no advice', async () => {
    const { host } = await mount(payload({ stacks: null, values: { p1: "Hemomania" } }));
    await press(slotButton(host, "p1"));
    expect(pick('[data-testid="mutation-picker-lock"]').textContent)
      .toContain("Vuelve a guardarlo en la bóveda o avisa a un admin.");
    expect(pick('[data-testid="mutation-lock-howto"]')).toBeNull();
  });

  test("a closed inherited slot never offers the catalog", async () => {
    const { host } = await mount(payload({ stacks: 0, values: { ea4: "Hemomania" } }));
    await press(slotButton(host, "ea4"));
    expect(pick('[data-testid="mutation-picker-lock"]')).not.toBeNull();
    expect(pick('[data-testid="mutation-option-wader"]')).toBeNull();
    expect(pick('[data-testid="mutation-picker-confirm"]')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// THE LEGEND WHEN THE COLUMN, NOT THE COUNTER, OPENED THE FAMILY (2026-07-26).
//
// The server opens p1..p4 on a dino whose entierro counter reads 0 when its
// heredadas column already holds a real mutation -- a dino bought with "Linaje
// Parental". It keeps publishing the RECORDED count, because that is the only
// honest answer to "how many times was this dino buried"; the derived one can
// sit a rung above the truth and must never be printed. Which leaves the legend
// having to explain four usable ranuras sitting under a requirement the dino
// does not meet: "se abren con 1 entierro · tu dino: 0 entierros" over four
// usable ranuras is a straight contradiction, and it was what the page said.
//
// NEGATIVE CONTROL: take the branch out and the first two cases here fail on the
// contradictory sentence.

/** The store-dino shape: counter at 0, the heredadas usable anyway. */
function lineagePayload(values = { p1: "Hemomania" }) {
  const body = payload({ stacks: 0, values });
  for (const s of ["p1", "p2", "p3", "p4"]) {
    body.slot_locks[s] = {
      ...body.slot_locks[s],
      locked: false, code: null, reason: null,
      clear_closes: s === "p1" && Object.keys(values).length === 1,
    };
  }
  body.unlocked = { ...body.unlocked, parent: true };
  return body;
}

describe("the legend never contradicts the ranuras drawn under it", () => {
  test("a family the column opened says so, instead of quoting the counter",
    async () => {
      const { host } = await mount(lineagePayload());
      const legend = host.querySelector('[data-testid="mutation-entomb-legend-parent"]');
      expect(legend.getAttribute("data-lineage")).toBe("1");
      expect(legend.textContent)
        .toContain("Ya están abiertas porque este dinosaurio ya trae mutaciones heredadas");
      expect(legend.textContent).not.toContain("tu dino: 0 entierros");
      expect(slotRow(host, "p1").getAttribute("data-locked")).toBe("0");
    });

  test("it still names the real requirement, and warns what emptying costs",
    async () => {
      const { host } = await mount(lineagePayload());
      const legend = host.querySelector('[data-testid="mutation-entomb-legend-parent"]').textContent;
      expect(legend).toContain("al menos 1 vez");
      expect(legend).not.toContain("al menos 1 entierro");
      expect(legend).toContain("se cerrarán las cuatro");
    });

  test("the families the counter really did shut keep the plain sentence",
    async () => {
      const { host } = await mount(lineagePayload());
      const elderA = host.querySelector('[data-testid="mutation-entomb-legend-elder_a"]');
      expect(elderA.getAttribute("data-lineage")).toBe("0");
      expect(elderA.textContent).toContain("al menos 2 veces");
      expect(elderA.textContent).toContain("tu dino: 0 entierros");
    });

  test("a dino that really was buried keeps the counter sentence", async () => {
    const { host } = await mount(payload({ stacks: 1 }));
    const legend = host.querySelector('[data-testid="mutation-entomb-legend-parent"]');
    expect(legend.getAttribute("data-lineage")).toBe("0");
    expect(legend.textContent).toContain("tu dino: 1 entierro");
    expect(legend.textContent).not.toContain("Ya están abiertas");
  });

  test("the count the page prints is the one the server sent, never a derived one",
    async () => {
      const { host } = await mount(lineagePayload());
      const all = host.querySelector('[data-testid="mutation-editor"]').textContent;
      expect(all).not.toContain("tu dino: 1 entierro");
      expect(all).toContain("tu dino: 0 entierros");
    });
});

describe("an unreadable counter still explains a family that is usable anyway", () => {
  test("the column's sentence wins over a requirement with no count to quote",
    async () => {
      const body = payload({ stacks: null, values: { p1: "Hemomania" } });
      for (const s of ["p1", "p2", "p3", "p4"]) {
        body.slot_locks[s] = { ...body.slot_locks[s], locked: false, code: null,
          reason: null, clear_closes: s === "p1" };
      }
      const { host } = await mount(body);
      const legend = host.querySelector('[data-testid="mutation-entomb-legend-parent"]');
      expect(legend.getAttribute("data-lineage")).toBe("1");
      expect(legend.textContent).toContain("Ya están abiertas");
      expect(legend.textContent).not.toContain("tu dino");
      // ...while the families that really are shut keep their own copy
      expect(host.querySelector('[data-testid="mutation-entomb-legend-elder_a"]')
        .getAttribute("data-lineage")).toBe("0");
      expect(slotRow(host, "ea1").getAttribute("data-locked")).toBe("1");
    });
});
