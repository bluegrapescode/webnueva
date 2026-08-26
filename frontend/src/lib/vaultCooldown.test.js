/**
 * Body Drop cooldown gate.
 *
 * Two halves, both against real things:
 *  1. the REAL bodyDropButtonState driven by REAL /me/vault summary payloads —
 *     the full key set vault.summary() actually returns, not a two-key stub, so
 *     a fixture with the wrong contract cannot score a false green;
 *  2. the REAL VaultSection.jsx read off disk, proving the button is actually
 *     wired to that decision. The decision being right is worthless if the JSX
 *     still computes `disabled` inline.
 *
 * NEGATIVE CONTROL: against the unfixed tree, half 1 fails (bodyDropButtonState
 * does not exist) and "the Body Drop button renders the decision, not its own
 * inline gate" fails on the old inline `disabled={busy === "bodydrop" || ...}`
 * expression, which is still present in VaultSection.jsx.
 */
const fs = require("fs");
const path = require("path");

import {
  bodyDropButtonState, parkButtonState, cooldownSeconds,
  BODYDROP_COOLDOWN_FIELD, COOLDOWN_SANITY_MAX_S,
} from "./vaultCooldown";

// A real /me/vault summary: every key vault.summary() emits, for an online
// carnivore that can body drop right now.
function summary(overrides) {
  return {
    is_admin: false,
    slots_used: 3,
    slots_cap: 10,
    slots_remaining: 7,
    unlimited: false,
    online: true,
    live: {
      species: "Deinosuchus", class: "BP_Deinosuchus_C", growth: 0.42, growth_pct: 42,
      eligible_to_park: true, gate_failures: [], growth_paused: false,
    },
    dinos: [],
    slay_cooldown_s: 0,
    redeem_cooldown_s: 0,
    park_min: { growth: 0.25, health: 0.9, stamina: 0.5, hunger: 0.5 },
    bodydrop_max: { hunger: 0.3, growth: 0.65, species_ok: true },
    growth_pause: { min: 0.75, max: 1.0, enabled: true },
    ...overrides,
  };
}

describe("cooldownSeconds — degrades open on everything unusable", () => {
  test("reads whole seconds off the documented field name", () => {
    expect(BODYDROP_COOLDOWN_FIELD).toBe("bodydrop_cooldown_s");
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: 431 }), BODYDROP_COOLDOWN_FIELD)).toBe(431);
    // the backend ships ints; tolerate a stringified one rather than disabling on NaN
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: "431" }), BODYDROP_COOLDOWN_FIELD)).toBe(431);
  });

  test("missing / null / garbage / negative all read as no cooldown", () => {
    const f = BODYDROP_COOLDOWN_FIELD;
    expect(cooldownSeconds(summary({}), f)).toBe(0);                        // field absent
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: null }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: "" }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: "pronto" }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: NaN }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: -60 }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: true }), f)).toBe(0);
    expect(cooldownSeconds(summary({ bodydrop_cooldown_s: { s: 60 } }), f)).toBe(0);
    expect(cooldownSeconds(undefined, f)).toBe(0);                          // vault still loading
    expect(cooldownSeconds(null, f)).toBe(0);                               // vault load failed
  });

  test("an implausible value is ignored, not enforced, and warns once", () => {
    const spy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const huge = COOLDOWN_SANITY_MAX_S + 1;
    try {
      // a bad clock or a bad write must never lock the button for the session
      expect(cooldownSeconds(summary({ bodydrop_cooldown_s: huge }), BODYDROP_COOLDOWN_FIELD)).toBe(0);
      expect(spy).toHaveBeenCalledTimes(1);
      cooldownSeconds(summary({ bodydrop_cooldown_s: huge }), BODYDROP_COOLDOWN_FIELD);
      expect(spy).toHaveBeenCalledTimes(1); // still once — an 8 s poll cannot flood
    } finally {
      spy.mockRestore();
    }
  });
});

describe("bodyDropButtonState", () => {
  test("on cooldown: disabled, minutes rounded UP, Spanish label", () => {
    const s = bodyDropButtonState(summary({ bodydrop_cooldown_s: 431 }), null);
    expect(s.disabled).toBe(true);
    expect(s.minutes).toBe(8);                     // ceil(431/60), same as the backend's (r+59)//60
    expect(s.label).toBe("Espera 8 min");
    expect(s.title).toContain("8 min");
  });

  test("the last second still reads as one minute, and zero re-enables", () => {
    expect(bodyDropButtonState(summary({ bodydrop_cooldown_s: 1 }), null).label).toBe("Espera 1 min");
    expect(bodyDropButtonState(summary({ bodydrop_cooldown_s: 60 }), null).minutes).toBe(1);
    const free = bodyDropButtonState(summary({ bodydrop_cooldown_s: 0 }), null);
    expect(free.disabled).toBe(false);
    expect(free.label).toBe("Body Drop");
  });

  test("a missing field is exactly today's button — never a broken one", () => {
    const before = bodyDropButtonState(summary({}), null);
    expect(before.disabled).toBe(false);
    expect(before.label).toBe("Body Drop");
    expect(before.title).toBe("El servidor deja caer un cuerpo fresco junto a ti para que puedas comer.");
    // and the same holds for the shapes the panel sees while loading / after a failed load
    expect(bodyDropButtonState(undefined, null).label).toBe("Body Drop");
    expect(bodyDropButtonState(null, null).label).toBe("Body Drop");
  });

  test("the pre-existing offline and carnivore gates are untouched and still win the tooltip", () => {
    const offline = bodyDropButtonState(summary({ online: false, bodydrop_cooldown_s: 431 }), null);
    expect(offline.disabled).toBe(true);
    expect(offline.title).toBe("Debes estar en partida para pedir un Body Drop.");

    const herbivore = bodyDropButtonState(
      summary({ bodydrop_max: { hunger: 0.3, growth: 0.65, species_ok: false } }), null);
    expect(herbivore.disabled).toBe(true);
    expect(herbivore.title).toBe("Body Drop alimenta solo a carnívoros.");

    // backend never spoke on species -> do not gate on it (an absent bodydrop_max
    // once disabled this button for everyone on a sibling build)
    const noSpeciesInfo = bodyDropButtonState(summary({ bodydrop_max: undefined }), null);
    expect(noSpeciesInfo.disabled).toBe(false);
  });

  test("an in-flight drop keeps the spinner label, never a stale countdown", () => {
    const s = bodyDropButtonState(summary({ bodydrop_cooldown_s: 431 }), "bodydrop");
    expect(s.disabled).toBe(true);
    expect(s.label).toBe("Body Drop");
  });

  test("another action in flight does not touch this button", () => {
    expect(bodyDropButtonState(summary({}), "park").disabled).toBe(false);
  });
});

describe("VaultSection.jsx wiring", () => {
  const src = fs.readFileSync(
    path.resolve(__dirname, "../components/inventory/VaultSection.jsx"), "utf8");

  test("the Body Drop button renders the decision, not its own inline gate", () => {
    expect(src).toContain('bodyDropButtonState');
    expect(src).toContain('from "@/lib/vaultCooldown"');
    expect(src).toContain("bodyDropButtonState(vault, busy)");
    expect(src).toContain("disabled={bodyDrop.disabled}");
    expect(src).toContain("title={bodyDrop.title}");
    expect(src).toContain("{bodyDrop.label}");
    // the old inline gate must be gone, or the cooldown is decided in two places
    expect(src).not.toContain('disabled={busy === "bodydrop" ||');
    expect(src).not.toContain("<Drumstick size={15} />} Body Drop");
  });
});

// ── park wait (owner rule 2026-07-31) ────────────────────────────────────────
describe("parkButtonState", () => {
  test("no cooldown -> live button, normal label", () => {
    const s = parkButtonState({ park_cooldown_s: 0 }, null);
    expect(s.disabled).toBe(false);
    expect(s.label).toBe("Aparcar mi dinosaurio");
  });

  test("inside the wait -> disabled and says how long, in seconds", () => {
    const s = parkButtonState({ park_cooldown_s: 45 }, null);
    expect(s.disabled).toBe(true);
    expect(s.label).toBe("Espera 45 s");
    expect(s.title).toContain("45 s");
  });

  test("over a minute rounds up to minutes", () => {
    expect(parkButtonState({ park_cooldown_s: 61 }, null).label).toBe("Espera 2 min");
    expect(parkButtonState({ park_cooldown_s: 120 }, null).label).toBe("Espera 2 min");
  });

  test("in flight shows the spinner label, not a wait", () => {
    const s = parkButtonState({ park_cooldown_s: 0 }, "park");
    expect(s.disabled).toBe(true);
    expect(s.label).toBe("Aparcar mi dinosaurio");
  });

  test("degrades OPEN on a missing/garbage/absurd field", () => {
    expect(parkButtonState({}, null).disabled).toBe(false);
    expect(parkButtonState({ park_cooldown_s: "soon" }, null).disabled).toBe(false);
    expect(parkButtonState({ park_cooldown_s: 999999 }, null).disabled).toBe(false);
    expect(parkButtonState(null, null).disabled).toBe(false);
  });
});

// Same rule as Body Drop: the park button renders the decision, it does not
// re-implement the wait inline.
test("the park button renders parkButtonState, not its own inline gate", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "components", "inventory", "VaultSection.jsx"), "utf8");
  expect(src).toContain("parkButtonState(vault, busy)");
  expect(src).toContain("disabled={park.disabled}");
  expect(src).toContain("title={park.title}");
  expect(src).toContain("{park.label}");
  expect(src).not.toContain('disabled={busy === "park"}');
});
