/**
 * The locked-slot how-to, rendered — not grepped.
 *
 * The Python suite (backend/tests_local/test_vault_mutation_edit.py) owns the
 * ladder rule itself and reads this file's source per lock code. What it cannot
 * see is what a player ends up reading, so that lives here: the REAL
 * MutationEditor is mounted with the REAL payload shape
 * mutation_catalog.slot_lock_map + server.py me_vault_mutations put on the wire,
 * the slot button is really pressed, and the text of the panel is read back.
 *
 * WHY IT EXISTS: slot_lock answers the code "prime" BEFORE it ever looks at
 * growth, so a dino that is not Prime carries that code on its 4th own slot at
 * ANY growth. A single how-to sentence for every code therefore told that owner
 * to take his dinosaur out of the vault and raise it — a redeem that puts a real
 * animal back in the game, for a slot that stays shut. A source grep for the
 * sentence passes no matter who is shown it; only a render can tell.
 *
 * NEGATIVE CONTROL: against the unfixed tree every "no how-to" case here fails,
 * because the panel printed the growth sentence under every reason.
 *
 * (Wording note: Tailwind scans test titles and comments under src/, and the
 * bare verb form of "growth" is itself a utility — writing it alone emits a
 * real CSS rule. This file says growth / raise instead.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

// The alias "@" is a webpack-only setting, so these two resolve through virtual
// mocks rather than a change to the shared craco config. The rest are real
// packages, mocked only to keep this about the copy.
jest.mock("@/lib/api", () => ({ api: { meVaultMutations: jest.fn(), meVaultMutationSet: jest.fn() } }), { virtual: true });
jest.mock("@/context/SoundContext", () => ({ useSound: () => ({ play: () => {} }) }), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: () => {}, error: () => {} } }));
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));
// jest hoists these factories above the requires, so react is pulled in here
// rather than through the binding at the top of the file.
jest.mock("framer-motion", () => ({
  motion: { div: ({ children, ...rest }) => require("react").createElement("div", rest, children) },
  AnimatePresence: ({ children }) => children,
}));

const { api } = require("@/lib/api");
const { MutationEditor } = require("./MutationEditor");

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const GROW_IT = "hacerlo crecer en el juego y volver a guardarlo";

/** One slot_locks entry exactly as slot_lock_map builds it. */
function lockEntry(code, reason, pct, needsPrime) {
  return { locked: true, code, reason, requires_growth_pct: pct, requires_prime: !!needsPrime };
}

/** The whole GET /me/vault/{id}/mutations body, all 16 slots described. */
function payload({ n4Lock, n4Value = "None", growthPct = 100, isPrime = false }) {
  const slots = {};
  const slotLocks = {};
  for (const s of ["n1", "n2", "n3", "n4", "p1", "p2", "p3", "p4",
    "ea1", "ea2", "ea3", "ea4", "eb1", "eb2", "eb3", "eb4"]) {
    slots[s] = "None";
    slotLocks[s] = { locked: false, code: null, reason: null, requires_growth_pct: null, requires_prime: false };
  }
  slots.n4 = n4Value;
  slotLocks.n4 = n4Lock;
  return {
    dino_id: 1, slots, active_count: n4Value === "None" ? 0 : 1, max_slots: 16,
    elder_stacks: 0, slot_locks: slotLocks,
    growth_ladder: [
      { slot: "n1", index: 1, requires_growth_pct: 25, requires_prime: false },
      { slot: "n2", index: 2, requires_growth_pct: 50, requires_prime: false },
      { slot: "n3", index: 3, requires_growth_pct: 75, requires_prime: false },
      { slot: "n4", index: 4, requires_growth_pct: 75, requires_prime: true },
    ],
    growth_pct: growthPct, is_prime: isPrime,
    unlocked: { child: true, parent: true, elder_a: true, elder_b: true },
    catalog: [{ name: "Hemomania", restriction: "carnivore", description: "" }],
    cost_per_change: 20000, balance: 999999,
  };
}

/** Mount the editor, wait out its GET, press the n4 button, read the panel. */
async function openN4(body) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  const btn = host.querySelector('[data-testid="mutation-edit-n4"]');
  if (!btn.disabled) {
    await act(async () => {
      btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });
  }
  const panel = document.querySelector('[data-testid="mutation-picker-lock"]');
  const howto = document.querySelector('[data-testid="mutation-lock-howto"]');
  const result = {
    buttonEnabled: !btn.disabled,
    panelText: panel ? panel.textContent : "",
    howtoText: howto ? howto.textContent.trim() : null,
    howtoCode: howto ? howto.getAttribute("data-lock-code") : null,
  };
  await act(async () => root.unmount());
  host.remove();
  return result;
}

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

describe("a closed own slot tells the player only what is true for ITS lock code", () => {
  // A Prime parked at 50% clears the Prime half of the 4th rung and fails the
  // growth half, which is the only way to see code "growth" on n4.
  test('code "growth" is the one case where growing really does open it', async () => {
    const reason = "Se desbloquea al 75% de crecimiento (ahora: 50%).";
    const r = await openN4(payload({
      n4Lock: lockEntry("growth", reason, 75, true),
      n4Value: "Hemomania", growthPct: 50, isPrime: true,
    }));
    expect(r.panelText).toContain(reason);
    expect(r.howtoCode).toBe("growth");
    expect(r.howtoText).toContain(GROW_IT);
  });

  // A closed slot with nothing in it has no action left at all, so its button
  // stays dead and the panel is never reached — the how-to only ever has to be
  // right for a slot that still holds something.
  test("a closed EMPTY slot offers no way in, so no advice is reachable", async () => {
    const r = await openN4(payload({
      n4Lock: lockEntry("prime", "La cuarta mutación propia es solo para dinosaurios Prime.", 75, true),
      n4Value: "None",
    }));
    expect(r.buttonEnabled).toBe(false);
    expect(r.panelText).toBe("");
  });

  test('code "prime" never sends the owner off to raise a dino it will not help', async () => {
    const reason = "La cuarta mutación propia es solo para dinosaurios Prime.";
    const r = await openN4(payload({
      n4Lock: lockEntry("prime", reason, 75, true), n4Value: "Hemomania", growthPct: 100,
    }));
    expect(r.panelText).toContain(reason);
    expect(r.panelText).not.toContain(GROW_IT);
    expect(r.howtoCode).toBe("prime");
    // It has to say the useless thing is useless, not merely stay quiet.
    expect(r.howtoText).toMatch(/crecimiento/);
    expect(r.howtoText).toMatch(/nunca/);
  });

  test('code "growth_unknown" leans on its own reason and adds no growth advice', async () => {
    const reason = "No se pudo leer el crecimiento de este dinosaurio, así que la ranura queda "
      + "bloqueada. Vuelve a guardarlo en la bóveda o avisa a un admin.";
    const r = await openN4(payload({
      n4Lock: lockEntry("growth_unknown", reason, 75, true), n4Value: "Hemomania",
    }));
    expect(r.panelText).toContain("Vuelve a guardarlo en la bóveda o avisa a un admin.");
    expect(r.panelText).not.toContain(GROW_IT);
    expect(r.howtoText).toBeNull();
  });

  test("a code from a newer server prints no advice at all instead of the wrong one", async () => {
    const r = await openN4(payload({
      n4Lock: lockEntry("entombed", "Bloqueada por entierro.", null, false), n4Value: "Hemomania",
    }));
    expect(r.panelText).toContain("Bloqueada por entierro.");
    expect(r.panelText).not.toContain(GROW_IT);
    expect(r.howtoText).toBeNull();
  });

  test("a code that collides with an inherited object key cannot crash the panel", async () => {
    for (const code of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      const r = await openN4(payload({
        n4Lock: lockEntry(code, "Ranura bloqueada.", null, false), n4Value: "Hemomania",
      }));
      expect(r.panelText).toContain("Ranura bloqueada.");
      expect(r.howtoText).toBeNull();
    }
  });

  test("every lock keeps the promise that what is stored stays put", async () => {
    for (const code of ["growth", "prime", "growth_unknown"]) {
      const r = await openN4(payload({
        n4Lock: lockEntry(code, "Ranura bloqueada.", 75, true), n4Value: "Hemomania",
      }));
      expect(r.buttonEnabled).toBe(true);
      expect(r.panelText).toContain("Lo que ya tiene guardado sigue ahí mientras tú no lo quites.");
    }
  });
});
