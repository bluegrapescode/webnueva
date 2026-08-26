/**
 * Copy-current-skin (2026-08-07 owner feature): turn GET /api/snapshot's raw
 * live-skin reading into the skin editor's state, so a player can pull the
 * skin their dinosaur is wearing RIGHT NOW into the designer and keep it as a
 * saved preset.
 *
 * Pure and total — every malformed shape returns {ok:false, reason} instead of
 * throwing.
 *
 * ★COLOUR MATHS — 2026-08-11 LINEAR RESTORE. This file used to convert the
 * snapshot DIRECTLY (value*255, no gamma) on the premise that "the stored float
 * IS the picker fraction". That premise is retired: CustomizerData's colour
 * slots are `FLinearColor`, which UE consumes LINEAR, so /api/apply emits ONE
 * srgb->linear encode (server.py::SkinPayloadIn.to_command) and the floats this
 * file reads back are LINEAR. Displaying them raw is what made a copied skin
 * come back too dark.
 *
 * ★The decisive evidence for the flip is internal, not theoretical: this module
 * and `components/skin3d/SpeciesViewer3D.jsx` read the SAME payload — GET
 * /api/snapshot -> `data.skin` — SkinEditor.jsx passing it to
 * snapshotToEditorSkin() and resolveLiveSkin() passing it to
 * colorsFromRawSkin(). SpeciesViewer3D renders it through lin2srgb
 * (tintMaterial's linearToHex). One app, one wire, two colour spaces is a bug
 * on its face; the two now agree, and copyLiveSkin.test.js pins that they
 * PRODUCE THE SAME HEX so they cannot drift apart again.
 *
 * ★The OUTBOUND direction is unchanged and must stay unchanged: the editor
 * posts raw picker fractions (SkinEditor's srgb01FromHex) and the backend owns
 * the single encode. Encoding here as well is the DOUBLE ENCODE that produced
 * the fleet's original "one part of the body goes dark".
 */
// The one pure module this file will import: skinPatternCatalog holds no THREE
// and no React either, so copyLiveSkin.test.js still runs without the 3D tree.
import { clampPattern } from "@/lib/skinPatternCatalog";

export const SKIN_SLOTS = ["body", "markings", "flank", "underbelly", "detail1", "male_display", "eyes"];

// Same sentinel family SpeciesViewer3D refuses: a snapshot taken between a
// server restart and the player's re-apply carries colors -999999 / pattern -8.
// A slot with ANY component at or below this is garbage, never a colour.
export const SKIN_POISON_THRESHOLD = -900000;
const PATTERN_SENTINEL = -8;

// IEC 61966-2-1, byte-identical to tintMaterial.js's `linearToSrgb`. Held as a
// LOCAL copy on purpose: this module is a pure, dependency-free helper (its own
// test imports it without pulling THREE in), so it does not import the 3D
// component tree just to reach five lines of arithmetic. copyLiveSkin.test.js
// pins PARITY with tintMaterial's `linearToHex` over a probe sweep, so the two
// copies cannot drift apart silently — that pin is the price of the duplication.
function linearToSrgb(c) {
  const v = Math.max(0, Math.min(1, c));
  return v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
}

function linArrToHex(arr) {
  // Stored LINEAR float -> the sRGB byte the picker speaks (contract above).
  // Alpha is NOT a colour: it is the editor's own per-slot slider, so it is
  // clamped and carried, never passed through the transfer function.
  const toByte = (c) => Math.round(linearToSrgb(c) * 255).toString(16).padStart(2, "0");
  return {
    c: `#${toByte(arr[0])}${toByte(arr[1])}${toByte(arr[2])}`,
    a: typeof arr[3] === "number" && Number.isFinite(arr[3]) ? Math.max(0, Math.min(1, arr[3])) : 1,
  };
}

/** "BP_Tyrannosaurus_C" -> "Tyrannosaurus" (the /api/species name key). */
export function bareClass(cls) {
  const s = String(cls || "").trim();
  if (s.startsWith("BP_") && s.endsWith("_C")) return s.slice(3, -2);
  return s;
}

/**
 * Snapshot -> editor state. `defaults` is the species' default palette in the
 * editor's own {slot:{c,a}} shape; slots the snapshot cannot vouch for keep
 * their default instead of collapsing to black.
 *
 * `species` (optional) decides how far the pattern may travel. Omitting it keeps
 * the pre-2026-08-25 ceiling of 2, so an existing caller cannot be widened by
 * accident.
 *
 * Returns {ok:true, colors, pattern, copiedSlots} or {ok:false, reason} with
 * reason ∈ {"none","poisoned"}.
 */
export function snapshotToEditorSkin(snap, defaults, species) {
  if (!snap || typeof snap !== "object" || Array.isArray(snap)) return { ok: false, reason: "none" };
  const colors = { ...(defaults || {}) };
  const copiedSlots = [];
  SKIN_SLOTS.forEach((k) => {
    const arr = snap[k];
    if (!Array.isArray(arr) || arr.length < 3) return;
    const rgb = arr.slice(0, 3).map(Number);
    if (rgb.some((c) => !Number.isFinite(c))) return;
    if (arr.some((c) => Number(c) <= SKIN_POISON_THRESHOLD)) return; // restart sentinel
    colors[k] = linArrToHex([rgb[0], rgb[1], rgb[2], Number(arr[3])]);
    copiedSlots.push(k);
  });
  if (!copiedSlots.length) return { ok: false, reason: "poisoned" };

  // The editor's pattern control runs 0..(this species' real pattern count - 1);
  // it was hard-capped at 2 until 2026-08-25, which quietly rewrote a copied
  // Pattern 5 Omniraptor as a Pattern 2 one. The sentinel (-8) and glitch-lane
  // negatives are still not editor patterns — they clamp into the editor's range
  // so what the player sees in the designer is exactly what the preset stores.
  // With no species named, the old ceiling of 2 stands.
  let pattern = Number(snap.pattern);
  if (!Number.isFinite(pattern) || pattern === PATTERN_SENTINEL) pattern = 0;
  pattern = species == null
    ? Math.max(0, Math.min(2, Math.round(pattern)))
    : clampPattern(pattern, null, species);

  return { ok: true, colors, pattern, copiedSlots };
}

// ---------------------------------------------------------------------------
// Exact-copy sidecar (owner report 2026-08-08: a copied glitch skin "changes
// some parts"). Everything above is display-gamut math — faithful for skins
// the editor itself made, RE-AUTHORING for glitch-space payloads (channels
// beyond 0..1, alpha rails, out-of-band patterns), which is what a hatched or
// crate glitch skin wears. The copy therefore ALSO extracts the snapshot
// verbatim; the backend witnesses it against the live dino, stores it on the
// preset, and replays it byte-for-byte on an exact apply.
// Mirrors web/backend/skin_exact.py — keep the two in lockstep.
// ---------------------------------------------------------------------------

// 2026-08-23: raised 999999 -> 1e12 to match the backend's GLITCH_CHANNEL_MAX
// (skin_exact.CHANNEL_ABS_MAX). The stale 999999 made the BROWSER refuse worn
// glitch magnitudes (owner's real Rex: body -7952343.5) before the backend was
// ever asked — the "copy skin doesn't apply" half that lived client-side.
export const RAW_CHANNEL_ABS_MAX = 1.0e12;
export const RAW_PATTERN_ABS_MAX = 32;
export const EDITOR_PATTERN_MAX = 2;
// ★OPEN COUPLING, DELIBERATELY NOT MOVED IN THE 2026-08-11 SHIP. 0.02 was sized
// to cover the retired emitter's variation jitter (0.001..0.01), so it is stale
// by construction now that to_command snaps variation to an EXACT SkinVariation
// key {2.0, 8.0, 16.0}: a snapshot echoing our own 8.0 Medium reads as "lossy"
// and arms the exact-copy door on a copy the pickers CAN hold. That is
// fail-safe (an exact replay of the live bytes is byte-faithful, and the
// clamped copy still lands in the editor either way), so it is reported rather
// than guessed at — the right predicate is "not the key a plain re-apply would
// emit", and settling it needs a measurement of what /api/snapshot actually
// reports for variation. TWIN: backend skin_exact.py::EDITOR_VARIATION_TOL —
// move the two together or not at all.
export const EDITOR_VARIATION_TOL = 0.02;

/**
 * Snapshot -> verbatim raw sidecar, or null when an EXACT copy cannot be
 * vouched for (missing slot or alpha, non-finite, restart poison, value out of
 * the replay window). Null never blocks the clamped editor copy above — it
 * only means "no sidecar", exactly the pre-sidecar behaviour.
 *
 * opts.allowGlitch (2026-08-23 Glitch Lab): skip the CHANNEL sentinel refusal
 * only — the caller verified Glitch Lab entitlement server-side first
 * (/api/glitch-access), and the backend re-verifies at save. Pattern -8 stays
 * refused always (restart sentinel, never an aesthetic). For everyone else
 * the old refusals apply verbatim.
 */
export function extractRawSnapshot(snap, opts) {
  const allowGlitch = !!(opts && opts.allowGlitch);
  if (!snap || typeof snap !== "object" || Array.isArray(snap)) return null;
  const pattern = Number(snap.pattern);
  if (!Number.isFinite(pattern) || Math.round(pattern) !== pattern) return null;
  if (pattern === -8 || Math.abs(pattern) > RAW_PATTERN_ABS_MAX) return null;
  const variation = Number(snap.variation);
  if (!Number.isFinite(variation) || Math.abs(variation) > RAW_CHANNEL_ABS_MAX) return null;
  const raw = { pattern, variation };
  for (const k of SKIN_SLOTS) {
    const arr = snap[k];
    if (!Array.isArray(arr) || arr.length < 4) return null;
    const vals = arr.slice(0, 4).map(Number);
    for (const c of vals) {
      if (!Number.isFinite(c)) return null;
      if (c <= SKIN_POISON_THRESHOLD && !allowGlitch) return null;
      if (Math.abs(c) > RAW_CHANNEL_ABS_MAX) return null;
    }
    raw[k] = vals;
  }
  return raw;
}

/**
 * True when the editor's clamped conversion would DIFFER from the live bytes —
 * any channel or alpha outside [0,1], a pattern the editor's 0..2 control
 * cannot hold, or a variation beyond the apply lane's own jitter. This is the
 * signal to arm the exact-apply door instead of trusting the pickers.
 */
export function rawIsLossy(raw) {
  if (!raw || typeof raw !== "object") return false;
  const pattern = Number(raw.pattern);
  if (Number.isFinite(pattern) && !(pattern >= 0 && pattern <= EDITOR_PATTERN_MAX)) return true;
  const variation = Number(raw.variation);
  if (Number.isFinite(variation) && Math.abs(variation) > EDITOR_VARIATION_TOL) return true;
  for (const k of SKIN_SLOTS) {
    const arr = raw[k];
    if (!Array.isArray(arr)) continue;
    for (const c of arr) {
      const v = Number(c);
      if (Number.isFinite(v) && !(v >= 0 && v <= 1)) return true;
    }
  }
  return false;
}
