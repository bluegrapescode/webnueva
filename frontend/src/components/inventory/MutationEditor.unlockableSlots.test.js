/**
 * The per-ranura offer list, RENDERED — not grepped.
 *
 * Owner ruling 2026-07-27: the 1st and 3rd propia do not offer the mutations
 * the game makes you unlock in game; the 2nd, the 4th and all twelve inherited
 * ranuras offer everything. The Python suite
 * (backend/tests_local/test_vault_mutation_edit.py, section 12) owns the rule
 * and the seven names. What it cannot see is what a player ends up looking at,
 * so that lives here: the REAL MutationEditor is mounted with the REAL payload
 * shape server.py me_vault_mutations puts on the wire, the ranura button is
 * really pressed, and the option rows are read back out of the DOM.
 *
 * WHY IT EXISTS. A shorter list is only correct if the missing rows are ABSENT.
 * Drawing them faded, or with the "En uso" badge the duplicate rule uses, would
 * tell the player something false about a mutation he may well be entitled to
 * somewhere else on the same dinosaur. A source grep cannot tell those two
 * outcomes apart; a render can.
 *
 * IT ALSO PINS THE ROW WE MUST NOT BREAK. A parked dino can already hold one of
 * these in its 1st ranura — captured off a live dino that earned it, granted by
 * staff, or bought — and that value has to stay on screen and stay free to
 * remove. Only new writes are refused.
 *
 * NEGATIVE CONTROL: against a tree where the picker still reads meta.catalog
 * directly, every "not offered" case here fails.
 *
 * (Wording note: Tailwind scans test titles and comments under src/ as plain
 * tokens, and the bare adjective for "not shown" is itself a utility that emits
 * a real CSS rule. This file says unlockable throughout, and so does the wire.)
 */
const React = require("react");
const ReactDOM = require("react-dom/client");

jest.mock("@/lib/api", () => ({ api: { meVaultMutations: jest.fn(), meVaultMutationSet: jest.fn() } }), { virtual: true });
jest.mock("@/context/SoundContext", () => ({ useSound: () => ({ play: () => {} }) }), { virtual: true });
jest.mock("sonner", () => ({ toast: { success: () => {}, error: () => {} } }));
jest.mock("lucide-react", () => new Proxy({}, { get: () => () => null }));
jest.mock("framer-motion", () => ({
  motion: { div: ({ children, ...rest }) => require("react").createElement("div", rest, children) },
  AnimatePresence: ({ children }) => children,
}));

const { api } = require("@/lib/api");
const { MutationEditor } = require("./MutationEditor");

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const ALL_SLOTS = ["n1", "n2", "n3", "n4", "p1", "p2", "p3", "p4",
  "ea1", "ea2", "ea3", "ea4", "eb1", "eb2", "eb3", "eb4"];

// The seven names mutation_catalog.HIDDEN carries, and three ordinary ones for
// contrast. Spelled exactly as the catalog spells them.
const UNLOCKABLE = ["Osteophagic", "Enhanced Digestion", "Reinforced Tendons",
  "Reniculate Kidneys", "Multichambered Lungs", "Augmented Tapetum",
  "Heightened Ghrelin"];
const ORDINARY = ["Hemomania", "Nocturnal", "Wader"];
const EVERY = [...ORDINARY, ...UNLOCKABLE];

const NOTICE = "Algunas mutaciones hay que desbloquearlas jugando y no se pueden poner en "
  + "la 1ª y la 3ª ranura propia, así que no salen en esta lista. Sí puedes ponerlas en "
  + "la 2ª o en la 4ª.";
const KEPT = "Esta ranura ya lleva una de esas mutaciones. Se queda donde está mientras tú "
  + "no la toques, y quitarla sigue siendo gratis, pero si la cambias por otra ya no podrás "
  + "volver a ponerla aquí.";

function norm(name) {
  return String(name || "").replace(/[\s_]+/g, "").toLowerCase();
}

/**
 * The whole GET body. `slotCatalog: false` drops the field entirely, which is
 * what an older server sends.
 */
function payload({ values = {}, slotCatalog = true } = {}) {
  const slots = {};
  const slotLocks = {};
  for (const s of ALL_SLOTS) {
    slots[s] = values[s] || "None";
    // The two per-ranura facts the server derives about the value a ranura
    // HOLDS, modelled exactly as mutation_catalog.slot_lock_map computes them:
    // holds_unlockable is is_hidden(stored) (so a camel-case capture counts and
    // a name the catalog never carried does not), and clear_blocks_restore is
    // "this ranura would refuse to take that value back". Every ranura here is
    // open, so the only thing that can block a restore is the offer list.
    const held = slots[s];
    const isUnlockable = UNLOCKABLE.some((n) => norm(n) === norm(held));
    const inCatalog = EVERY.some((n) => norm(n) === norm(held));
    const trimmed = slotCatalog && (s === "n1" || s === "n3");
    slotLocks[s] = {
      locked: false, code: null, reason: null, requires_growth_pct: null,
      requires_prime: false, requires_entombs: null, clear_closes: false,
      holds_unlockable: isUnlockable,
      clear_blocks_restore: held !== "None" && (!inCatalog || (trimmed && isUnlockable)),
    };
  }
  const body = {
    dino_id: 1,
    slots,
    active_count: Object.values(slots).filter((v) => v !== "None").length,
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
    // The shared catalog stays FULL: it is what the editor looks a STORED value
    // up in to render its name and its description.
    catalog: EVERY.map((name) => ({
      name,
      restriction: name === "Hemomania" || name === "Osteophagic" || name === "Augmented Tapetum"
        ? "carnivore" : null,
      description: `desc ${name}`,
      unlockable: UNLOCKABLE.includes(name),
    })),
    cost_per_change: 20000,
    balance: 999999,
  };
  if (slotCatalog) {
    // Exactly what mutation_catalog.slot_catalog_overrides puts on the wire: the
    // SPARSE form, carrying only the ranuras whose list differs. The other
    // fourteen are absent and mean "offer the whole catalog" — the same path an
    // older server's missing field takes, which is why that path is pinned below.
    body.slot_catalog = {
      n1: EVERY.filter((n) => !UNLOCKABLE.includes(n)),
      n3: EVERY.filter((n) => !UNLOCKABLE.includes(n)),
    };
    body.unlockable_notice = NOTICE;
    body.unlockable_kept_notice = KEPT;
  }
  return body;
}

/** Mount, wait out the GET, press one ranura's button, read the picker back. */
async function openSlot(slotId, body) {
  api.meVaultMutations.mockResolvedValue({ data: body });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  await act(async () => {
    root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
  });
  const slotRow = host.querySelector(`[data-testid="mutation-slot-${slotId}"]`);
  const btn = host.querySelector(`[data-testid="mutation-edit-${slotId}"]`);
  await act(async () => {
    btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
  const picker = document.querySelector('[data-testid="mutation-picker"]');
  const notice = document.querySelector('[data-testid="mutation-unlockable-notice"]');
  const clearBtn = document.querySelector('[data-testid="mutation-picker-clear"]');
  const optionFor = (name) => document.querySelector(`[data-testid="mutation-option-${norm(name)}"]`);
  const offered = {};
  const disabledRows = [];
  for (const name of EVERY) {
    const el = optionFor(name);
    offered[name] = !!el;
    if (el && el.disabled) disabledRows.push(name);
  }
  const press = async (el) => {
    if (!el) throw new Error("nothing to press");
    await act(async () => {
      el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    });
  };
  const result = {
    slotRowText: slotRow ? slotRow.textContent : "",
    pickerText: picker ? picker.textContent : "",
    offered,
    disabledRows,
    noticeText: notice ? notice.textContent : null,
    noticeKept: notice ? notice.getAttribute("data-kept") : null,
    clearEnabled: !!clearBtn && !clearBtn.disabled,
    clearLabel: clearBtn ? clearBtn.textContent : "",
    clickClear: async () => { await press(clearBtn); },
    press,
    // Read live: the warning and its own confirm control only exist after the
    // first press, so these are functions, never a snapshot taken too early.
    warning: () => document.querySelector('[data-testid="mutation-clear-warning"]'),
    confirmBtn: () => document.querySelector('[data-testid="mutation-clear-confirm"]'),
    armBtn: () => document.querySelector('[data-testid="mutation-picker-clear"]'),
  };
  result.cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  return result;
}

beforeEach(() => { jest.clearAllMocks(); document.body.innerHTML = ""; });

describe("the ranura the player opens decides which mutations it offers", () => {
  test("the 1st propia leaves out every unlockable name and keeps the rest", async () => {
    const r = await openSlot("n1", payload());
    for (const name of UNLOCKABLE) expect(r.offered[name]).toBe(false);
    for (const name of ORDINARY) expect(r.offered[name]).toBe(true);
    await r.cleanup();
  });

  test("the 3rd propia behaves exactly like the 1st", async () => {
    const r = await openSlot("n3", payload());
    for (const name of UNLOCKABLE) expect(r.offered[name]).toBe(false);
    for (const name of ORDINARY) expect(r.offered[name]).toBe(true);
    await r.cleanup();
  });

  test("the 2nd and 4th propias offer every one of them", async () => {
    for (const sid of ["n2", "n4"]) {
      const r = await openSlot(sid, payload());
      for (const name of EVERY) expect(r.offered[name]).toBe(true);
      await r.cleanup();
    }
  });

  test("all twelve inherited ranuras offer every one of them", async () => {
    for (const sid of ALL_SLOTS.slice(4)) {
      const r = await openSlot(sid, payload());
      for (const name of UNLOCKABLE) expect(r.offered[name]).toBe(true);
      await r.cleanup();
    }
  });
});

describe("a shorter list is explained, and never mislabelled", () => {
  // The whole point. A faded row, or one wearing the duplicate rule's "En uso"
  // badge, would say something false about a mutation the player can still put
  // on the very same dinosaur one ranura over.
  test("the names it does not offer are absent, not faded and not marked in use", async () => {
    const r = await openSlot("n1", payload());
    expect(r.disabledRows).toEqual([]);
    expect(r.pickerText).not.toContain("En uso");
    for (const name of UNLOCKABLE) expect(r.pickerText).not.toContain(name);
    await r.cleanup();
  });

  test("a sentence from the server says why the list is shorter", async () => {
    const r = await openSlot("n1", payload());
    expect(r.noticeText).toContain(NOTICE);
    // It has to point at the ranuras that DO take them, not just refuse.
    expect(r.noticeText).toContain("2ª");
    expect(r.noticeText).toContain("4ª");
    await r.cleanup();
  });

  test("a ranura that offers everything shows no such sentence", async () => {
    for (const sid of ["n2", "n4", "p1", "eb4"]) {
      const r = await openSlot(sid, payload());
      expect(r.noticeText).toBeNull();
      await r.cleanup();
    }
  });
});

describe("a value already stored in a closed ranura is never broken", () => {
  test("the 1st propia still shows the unlockable it already holds", async () => {
    const r = await openSlot("n1", payload({ values: { n1: "Reniculate Kidneys" } }));
    expect(r.slotRowText).toContain("Reniculate Kidneys");
    await r.cleanup();
  });

  test("it can still be removed, and the button says removal is free", async () => {
    api.meVaultMutationSet.mockResolvedValue({
      data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
    });
    const r = await openSlot("n1", payload({ values: { n1: "Reniculate Kidneys" } }));
    expect(r.clearEnabled).toBe(true);
    expect(r.clearLabel).toContain("gratis");
    // Removing it is still allowed and still free, but it is now the guarded
    // two-press path (see the block below for why), so the confirming press is
    // the one that saves.
    await r.clickClear();
    await r.press(r.confirmBtn());
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
    await r.cleanup();
  });

  test("...and the panel says it stays put and that swapping it is one way", async () => {
    const r = await openSlot("n1", payload({ values: { n1: "Reniculate Kidneys" } }));
    expect(r.noticeKept).toBe("1");
    expect(r.noticeText).toContain(KEPT);
    await r.cleanup();
  });

  test("a ranura holding an ordinary name gets no such extra line", async () => {
    const r = await openSlot("n1", payload({ values: { n1: "Nocturnal" } }));
    expect(r.noticeKept).toBe("0");
    expect(r.noticeText).not.toContain(KEPT);
    await r.cleanup();
  });

  // Camel-case is what the game captures, so the stored value can arrive as
  // "ReniculateKidneys" and still has to be recognised as the one being held.
  test("a game-captured camel-case value is recognised as the held one", async () => {
    const r = await openSlot("n1", payload({ values: { n1: "ReniculateKidneys" } }));
    expect(r.slotRowText).toContain("Reniculate Kidneys");
    expect(r.noticeKept).toBe("1");
    await r.cleanup();
  });
});

// ---------------------------------------------------------------------------
// THE THIRD IRREVERSIBLE CLEAR (2026-07-26). A 1ª propia that is OPEN and holds
// one of the seven drew the plain one-press "Quitar (gratis)": the confirmation
// was armed by the ranura being LOCKED, and this one is not. But the save
// refuses to write that name back into the 1ª forever after, so the press threw
// the mutation away with no question asked, on a ranura the page was presenting
// as freely editable. Same shape, third time: a clear the player cannot walk
// back, sitting on the unguarded path.
//
// The question the guard now asks is whether the clear is REVERSIBLE, and the
// server answers it per ranura (slot_locks[slot].clear_blocks_restore) off the
// two things it already computes: what that ranura offers and what that ranura
// locks. This file never re-derives it; it feeds the flag in and presses.
//
// NEGATIVE CONTROL: gate the confirmation on isLocked / clear_closes again and
// the first four checks here fail — the press saves straight away.
describe("emptying a usable ranura that will not take the value back asks first", () => {
  const HELD = () => payload({ values: { n1: "Reniculate Kidneys" } });

  test("the ranura really is open, and the first press asks instead of removing",
    async () => {
      const r = await openSlot("n1", HELD());
      expect(document.querySelector('[data-testid="mutation-slot-n1"]')
        .getAttribute("data-locked")).toBe("0");
      expect(r.warning()).toBeNull();
      await r.clickClear();
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(r.warning()).not.toBeNull();
      expect(r.armBtn().getAttribute("data-armed")).toBe("1");
      await r.cleanup();
    });

  test("a habitual double press backs out and removes nothing", async () => {
    const r = await openSlot("n1", HELD());
    await r.clickClear();
    await r.press(r.armBtn());
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(r.warning()).toBeNull();
    await r.cleanup();
  });

  test("the control that removes is the panel's own, and it does remove", async () => {
    api.meVaultMutationSet.mockResolvedValue({
      data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
    });
    const r = await openSlot("n1", HELD());
    await r.clickClear();
    const confirmEl = r.confirmBtn();
    expect(confirmEl).not.toBe(r.armBtn());
    expect(r.warning().contains(confirmEl)).toBe(true);
    expect(r.warning().contains(r.armBtn())).toBe(false);
    expect(confirmEl.textContent).toContain("(gratis)");
    await r.press(confirmEl);
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
    await r.cleanup();
  });

  test("the 3rd propia behaves the same way", async () => {
    const r = await openSlot("n3", payload({ values: { n3: "Multichambered Lungs" } }));
    await r.clickClear();
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    expect(r.warning()).not.toBeNull();
    await r.cleanup();
  });

  test("the warning tells the truth about a usable ranura, not the closed copy",
    async () => {
      const r = await openSlot("n1", HELD());
      await r.clickClear();
      expect(r.warning().getAttribute("data-clear-kind")).toBe("value");
      expect(r.warning().textContent).toContain("no podrás volver a ponerla aquí");
      // The ranura is NOT closed: he can still put something else in it, so
      // neither of the other two warnings may be shown here.
      expect(r.warning().textContent)
        .not.toContain("mientras la ranura siga bloqueada");
      expect(r.warning().textContent).not.toContain("se cerrarán las cuatro");
      // ...and the catalog stays on screen behind the question, because
      // swapping it for another mutation is still a thing he can do.
      expect(document.querySelector('[data-testid="mutation-option-nocturnal"]'))
        .not.toBeNull();
      await r.cleanup();
    });

  test("a value the same ranura WOULD take back keeps its single press", async () => {
    api.meVaultMutationSet.mockResolvedValue({
      data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
    });
    const r = await openSlot("n1", payload({ values: { n1: "Nocturnal" } }));
    expect(r.warning()).toBeNull();
    await r.clickClear();
    expect(api.meVaultMutationSet).toHaveBeenCalledTimes(1);
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
    expect(r.warning()).toBeNull();
    await r.cleanup();
  });

  test("the same name in a ranura that DOES offer it keeps its single press",
    async () => {
      api.meVaultMutationSet.mockResolvedValue({
        data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
      });
      const r = await openSlot("n2", payload({ values: { n2: "Reniculate Kidneys" } }));
      expect(r.warning()).toBeNull();
      await r.clickClear();
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n2", "None");
      await r.cleanup();
    });

  test("an older payload without the field behaves exactly as it did before",
    async () => {
      api.meVaultMutationSet.mockResolvedValue({
        data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
      });
      const body = payload({ values: { n1: "Reniculate Kidneys" } });
      for (const s of ALL_SLOTS) delete body.slot_locks[s].clear_blocks_restore;
      const r = await openSlot("n1", body);
      await r.clickClear();
      expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
      await r.cleanup();
    });

  // The flag is the server's, so the page has to obey it wherever it lands -
  // including a ranura this build would never expect to see it on.
  test("the page obeys the flag itself, not a rule of its own about ranuras",
    async () => {
      const body = payload({ values: { eb4: "Nocturnal" } });
      body.slot_locks.eb4.clear_blocks_restore = true;
      const r = await openSlot("eb4", body);
      await r.clickClear();
      expect(api.meVaultMutationSet).not.toHaveBeenCalled();
      expect(r.warning().getAttribute("data-clear-kind")).toBe("value");
      await r.cleanup();
    });

  test("the question does not survive a close and a reopen", async () => {
    const body = HELD();
    api.meVaultMutations.mockResolvedValue({ data: body });
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = ReactDOM.createRoot(host);
    await act(async () => {
      root.render(React.createElement(MutationEditor, { dino: { id: 1 }, onChanged: () => {} }));
    });
    const press = async (el) => {
      await act(async () => {
        el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
      });
    };
    await press(host.querySelector('[data-testid="mutation-edit-n1"]'));
    await press(document.querySelector('[data-testid="mutation-picker-clear"]'));
    expect(document.querySelector('[data-testid="mutation-clear-warning"]')).not.toBeNull();
    await press(document.querySelector('[data-testid="mutation-picker-close"]'));
    await press(host.querySelector('[data-testid="mutation-edit-n1"]'));
    expect(document.querySelector('[data-testid="mutation-clear-warning"]')).toBeNull();
    await press(document.querySelector('[data-testid="mutation-picker-clear"]'));
    expect(api.meVaultMutationSet).not.toHaveBeenCalled();
    await act(async () => root.unmount());
    host.remove();
  });
});

// ---------------------------------------------------------------------------
// THE LABEL. "Stored, and not in this ranura's offer list" is ALSO true of a
// name the catalog has never carried - a legacy capture, or something staff
// granted - and the extra line told the player those had to be unlocked in
// game, which is false about them. Which names are unlockable is the server's
// answer (slot_locks[slot].holds_unlockable), never a set difference here.
//
// NEGATIVE CONTROL: derive it from the offer list again and the first check
// below fails, because the legacy name is missing from that list too.
describe("only a real unlockable is labelled as one", () => {
  test("a legacy name the catalog never carried gets no unlockable line",
    async () => {
      const body = payload({ values: { n1: "Cannibalistic" } });
      const r = await openSlot("n1", body);
      // It is genuinely absent from the ranura's list, which is the very thing
      // the old derivation read as "this one is unlockable".
      expect(body.slot_catalog.n1).not.toContain("Cannibalistic");
      expect(r.noticeKept).toBe("0");
      expect(r.noticeText).not.toContain(KEPT);
      await r.cleanup();
    });

  test("...and it still renders, and is still removable", async () => {
    api.meVaultMutationSet.mockResolvedValue({
      data: { changed: true, charged: 0, slots: {}, active_count: 0, balance: 999999 },
    });
    const r = await openSlot("n1", payload({ values: { n1: "Cannibalistic" } }));
    expect(r.slotRowText).toContain("Cannibalistic");
    expect(r.clearEnabled).toBe(true);
    // Nothing can put it back either, so it takes the guarded path too.
    await r.clickClear();
    await r.press(r.confirmBtn());
    expect(api.meVaultMutationSet).toHaveBeenCalledWith(1, "n1", "None");
    await r.cleanup();
  });

  test("a real unlockable in the same ranura still gets the line", async () => {
    const r = await openSlot("n1", payload({ values: { n1: "Reniculate Kidneys" } }));
    expect(r.noticeKept).toBe("1");
    expect(r.noticeText).toContain(KEPT);
    await r.cleanup();
  });

  test("the page takes the server's word for it, both ways", async () => {
    // Server says no: no line, even though the value is missing from the list.
    const off = payload({ values: { n1: "Reniculate Kidneys" } });
    off.slot_locks.n1.holds_unlockable = false;
    const r1 = await openSlot("n1", off);
    expect(r1.noticeKept).toBe("0");
    await r1.cleanup();
    // Server says yes, but the ranura offers it: no line either, because the
    // second half of that sentence (it cannot come back) would not be true.
    const on = payload({ values: { n2: "Reniculate Kidneys" } });
    on.slot_locks.n2.holds_unlockable = true;
    const r2 = await openSlot("n2", on);
    expect(r2.noticeKept).toBeNull();
    await r2.cleanup();
  });
});

describe("the server stays the only source of the rule", () => {
  // Erring OPEN is the only safe default: refusing names the server never
  // refused would take away mutations a player is entitled to, and the POST
  // re-checks every rule anyway.
  test("a payload with no per-ranura field falls back to the full catalog", async () => {
    const r = await openSlot("n1", payload({ slotCatalog: false }));
    for (const name of EVERY) expect(r.offered[name]).toBe(true);
    expect(r.noticeText).toBeNull();
    await r.cleanup();
  });

  // The rule lives in one place. If the server ever re-rules, the page follows
  // without an edit here — so a payload that closes a DIFFERENT ranura has to
  // be obeyed as-is.
  test("the page obeys whichever ranuras the server trims, not a rule of its own", async () => {
    const body = payload();
    delete body.slot_catalog.n1;
    body.slot_catalog.n2 = EVERY.filter((n) => n !== "Osteophagic");
    const open1 = await openSlot("n1", body);
    expect(open1.offered.Osteophagic).toBe(true);
    expect(open1.noticeText).toBeNull();
    await open1.cleanup();
    const open2 = await openSlot("n2", body);
    expect(open2.offered.Osteophagic).toBe(false);
    expect(open2.noticeText).toContain(NOTICE);
    await open2.cleanup();
  });

  test("a ranura the server did not describe at all still offers everything", async () => {
    const body = payload();
    delete body.slot_catalog.n1;
    const r = await openSlot("n1", body);
    for (const name of EVERY) expect(r.offered[name]).toBe(true);
    await r.cleanup();
  });

  // The wire form is sparse, but the complete sixteen-key form says exactly the
  // same thing and must keep working — a server that sends it, or a cached
  // payload from before the trim, cannot change what the player sees.
  test("the complete sixteen-key form is read identically to the sparse one", async () => {
    const body = payload();
    for (const s of ALL_SLOTS) {
      body.slot_catalog[s] = (s === "n1" || s === "n3")
        ? EVERY.filter((n) => !UNLOCKABLE.includes(n))
        : [...EVERY];
    }
    const r1 = await openSlot("n1", body);
    for (const name of UNLOCKABLE) expect(r1.offered[name]).toBe(false);
    expect(r1.noticeText).toContain(NOTICE);
    await r1.cleanup();
    const r2 = await openSlot("n2", body);
    for (const name of EVERY) expect(r2.offered[name]).toBe(true);
    expect(r2.noticeText).toBeNull();
    await r2.cleanup();
  });

  test("a malformed per-ranura entry cannot empty the picker", async () => {
    for (const junk of [null, "Osteophagic", 7, { n1: true }]) {
      const body = payload();
      body.slot_catalog.n1 = junk;
      const r = await openSlot("n1", body);
      for (const name of EVERY) expect(r.offered[name]).toBe(true);
      await r.cleanup();
    }
  });
});
