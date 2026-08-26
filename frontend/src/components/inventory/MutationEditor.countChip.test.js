/**
 * The "N/M activas" chip, rendered — not grepped.
 *
 * It used to read "N/16" on every dino. Sixteen is what the model HAS, not what
 * any one dino can reach: a dino that has never been buried can only ever fill
 * its four propias, so "2/16" told the player fourteen ranuras were free when
 * two were. The denominator is now what this dino can use right now — every open
 * ranura, plus any closed one that already holds a mutation (that one is
 * genuinely in use, and emptying it stays allowed and free).
 *
 * Because every filled ranura is counted in the denominator, the left number can
 * never run past the right one — the last case here walks a spread of shapes and
 * asserts exactly that, so a future edit cannot produce a "4/0".
 *
 * The Python suite owns which ranuras the server opens (including the read-time
 * lineage derivation that opens the heredadas on a row whose counter says 0);
 * what it cannot see is the number a player ends up reading, so that lives here:
 * the REAL MutationEditor is mounted with the REAL payload shape
 * me_vault_mutations puts on the wire, and the chip is read back.
 *
 * NEGATIVE CONTROL: put the constant sixteen back as the denominator and every
 * case below except the all-open ones fails.
 *
 * (Wording note: Tailwind scans test titles and comments under src/, and a bare
 * utility word in prose ships a real CSS rule. This file says open / closed /
 * held / reads / chip, and reaches for elements by test id.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

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

/** The GET body, with the closed ranuras named outright: `closed` is the list
 *  the SERVER decided, which is the only thing this component may act on. */
function payload({ closed = [], values = {}, stacks = 3 } = {}) {
  const slots = {};
  const slotLocks = {};
  for (const s of ALL_SLOTS) {
    slots[s] = values[s] || "None";
    const shut = closed.includes(s);
    slotLocks[s] = {
      locked: shut,
      code: shut ? "entomb" : null,
      reason: shut ? "Se desbloquea cuando el dinosaurio ha sido enterrado." : null,
      requires_growth_pct: null,
      requires_prime: false,
      requires_entombs: OWN.includes(s) ? null : 1,
    };
  }
  return {
    dino_id: 1, slots, active_count: 0, max_slots: 16, elder_stacks: stacks,
    slot_locks: slotLocks,
    growth_ladder: [],
    entomb_ladder: [],
    growth_pct: 100, is_prime: true,
    unlocked: { child: true, parent: true, elder_a: true, elder_b: true },
    catalog: [{ name: "Wader", restriction: null, description: "Vadea mejor." }],
    cost_per_change: 20000, balance: 999999,
  };
}

async function mount(body) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  return { host, root };
}

const chip = (host) => host.querySelector('[data-testid="mutation-active-count"]');

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

describe("the chip counts against what this dino can actually reach", () => {
  test("a dino with every ranura open still reads sixteen", async () => {
    const { host } = await mount(payload({ values: { n1: "Wader", eb4: "Wader" } }));
    expect(chip(host).textContent).toBe("2/16 activas");
    expect(chip(host).getAttribute("data-available")).toBe("16");
  });

  test("a dino that has never been buried reads four, not sixteen", async () => {
    const { host } = await mount(payload({ closed: [...PARENT, ...ELDER_A, ...ELDER_B] }));
    expect(chip(host).textContent).toBe("0/4 activas");
    expect(chip(host).textContent).not.toContain("16");
  });

  test("the regression row: counter says zero, four paid heredadas are open", async () => {
    // The backend derives generation 1 from the parent column, so it sends p1..p4
    // open and the eight Anciano ones closed. Four propias plus four heredadas is
    // eight reachable, and all four heredadas are already in use.
    const { host } = await mount(payload({
      closed: [...ELDER_A, ...ELDER_B],
      stacks: 1,
      values: { p1: "Wader", p2: "Nocturnal", p3: "Hemomania", p4: "Featherweight" },
    }));
    expect(chip(host).textContent).toBe("4/8 activas");
  });

  test("a mutation held in a closed ranura counts on BOTH sides", async () => {
    const { host } = await mount(payload({
      closed: [...PARENT, ...ELDER_A, ...ELDER_B],
      values: { ea2: "Wader" },
    }));
    // four propias plus the one closed ranura that is holding something
    expect(chip(host).textContent).toBe("1/5 activas");
  });

  test("a dino with nothing open at all and nothing held reads zero of zero", async () => {
    const { host } = await mount(payload({ closed: ALL_SLOTS }));
    expect(chip(host).textContent).toBe("0/0 activas");
    expect(chip(host).getAttribute("data-available")).toBe("0");
  });

  test("a dino with every ranura closed but every one full reads sixteen of sixteen",
    async () => {
      const values = {};
      for (const s of ALL_SLOTS) values[s] = "Wader";
      const { host } = await mount(payload({ closed: ALL_SLOTS, values }));
      expect(chip(host).textContent).toBe("16/16 activas");
    });

  test("the chip says nothing at all until the server has answered", async () => {
    api.meVaultMutations.mockReturnValue(new Promise(() => {}));
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = ReactDOM.createRoot(host);
    await act(async () => {
      root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
    });
    expect(chip(host).textContent).toBe("— activas");
    expect(chip(host).getAttribute("data-available")).toBe("");
  });

  test("the used count can never run past the reachable count", async () => {
    const shapes = [
      { closed: [], values: {} },
      { closed: [...PARENT, ...ELDER_A, ...ELDER_B], values: { p1: "Wader", eb3: "Wader" } },
      { closed: ALL_SLOTS, values: { n1: "Wader", n2: "Wader", ea4: "Wader" } },
      { closed: [...ELDER_B], values: { eb1: "Wader", eb2: "Wader" } },
      { closed: ALL_SLOTS, values: {} },
      { closed: [...OWN], values: { n3: "Wader" } },
    ];
    for (const shape of shapes) {
      const { host, root } = await mount(payload(shape));
      const [used, reachable] = chip(host).textContent.split(" ")[0].split("/").map(Number);
      const held = Object.keys(shape.values).length;
      const openOrHeld = ALL_SLOTS.filter(
        (s) => !shape.closed.includes(s) || !!shape.values[s]).length;
      expect({ shape: shape.closed.length, used, reachable })
        .toEqual({ shape: shape.closed.length, used: held, reachable: openOrHeld });
      expect(used).toBeLessThanOrEqual(reachable);
      await act(async () => root.unmount());
      document.body.innerHTML = "";
    }
  });

  test("the chip explains its own denominator on hover", async () => {
    const { host } = await mount(payload({ closed: [...ELDER_A, ...ELDER_B] }));
    expect(chip(host).getAttribute("title"))
      .toContain("Ranuras que puedes usar en este dinosaurio ahora mismo");
    expect(chip(host).getAttribute("title")).not.toContain("—");
  });
});

describe("the store dino the whole read-time derivation exists for", () => {
  // Counter at 0, four heredadas usable because the column itself proved the
  // lineage step, the eight Anciano ranuras still shut. Eight reachable, and the
  // one paid mutation sitting in p1 is one of them.
  const STORE_DINO = { closed: [...ELDER_A, ...ELDER_B], values: { p1: "Hemomania" },
    stacks: 0 };

  test("its chip counts the eight it can really use, not sixteen", async () => {
    const { host } = await mount(payload(STORE_DINO));
    expect(chip(host).textContent).toBe("1/8 activas");
    expect(chip(host).getAttribute("data-available")).toBe("8");
  });

  test("a closed Anciano ranura that holds something is still counted as in use",
    async () => {
      const { host } = await mount(payload({
        ...STORE_DINO, values: { p1: "Hemomania", eb2: "Nocturnal" } }));
      expect(chip(host).textContent).toBe("2/9 activas");
    });
});
