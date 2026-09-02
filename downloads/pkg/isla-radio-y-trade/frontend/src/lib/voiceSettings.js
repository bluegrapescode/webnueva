/**
 * Player-adjustable proximity-voice settings + the pure composition math.
 *
 * The bridge owns WHO you hear (the subscription set) and reports each speaker's
 * distance. voiceFalloff turns that distance into a curve FACTOR. This module
 * owns the player's own knobs and composes the final gain:
 *
 *     finalGain = mute ? 0 : clamp(master * perSpeakerVolume * curveFactor, 0, CAP)
 *
 * Governing rule: nothing here can make you hear a speaker the bridge did not
 * route, and max-hearing can only ever SHORTEN the range, never extend it. Every
 * value is clamped and every unknown falls back to a default, so a corrupt
 * localStorage entry can never push NaN into a track volume.
 *
 * Pure and dependency-free so the whole composition is unit-tested without React.
 */
import { FALLOFF_EXPONENT, FULL_VOLUME_FRACTION, MIN_FALLOFF_EXPONENT, MAX_FALLOFF_EXPONENT } from "./voiceFalloff";

// v3 (2026-07-25): the player's hearing range is stored in METRES, not as a
// fraction of the server radius. Under v2 a server retune silently rescaled
// everyone's personal choice (someone who picked "20 m" would have become 57 m
// the moment the range moved to 100 m); a distance the player picked should mean
// that distance until they change it. A v2 entry is converted on load.
export const LS_KEY = "lin_voice_settings_v3";
export const LEGACY_LS_KEY_V2 = "lin_voice_settings_v2";
// What a v2 FRACTION was a fraction OF — the only way to recover the metres the
// player actually chose. NOTE it is the HOLD radius (40 m = the 35 m range + the
// 5 m release band), not the range: v2 fed the hold radius to both the slider
// label and the cut-off, so "0.5" was displayed and heard as 20 m, not 17.5 m.
//
// ★ THIS CONSTANT MAKES THE DEPLOY ORDER LOAD-BEARING: ship the SITE BEFORE the
// bridge retune. A v2 client talking to an already-retuned 100 m bridge writes
// its fraction against a 105 m hold radius, and this conversion would then read
// it as a fraction of 40 — a permanent 0.38x shrink of that player's range (a
// 50 m choice becomes 19 m). Site-first is also the default, because
// web/frontend auto-deploys on push and voice/ never does. Once the site is out,
// no client writes fractions again and this constant is unambiguous forever.
export const V2_BASIS_RADIUS_M = 40;

// v1 applies at most unity gain. The 100-150% boost region needs a Web Audio
// GainNode (HTMLMediaElement/RemoteAudioTrack volume hard-caps at 1.0); storage
// tolerates up to 1.5 for forward-compat, but composeGain never exceeds this.
export const MAX_APPLIED_GAIN = 1;
export const MASTER_STORE_MAX = 1.5;
// Personal hearing range, in metres. 0 is the default and means "follow the
// server range" — so the range the owner sets is what every untouched player
// gets, today and after any future retune. Bounds match the bridge's own clamp.
export const HEARING_MIN_M = 5;
export const HEARING_MAX_M = 200;
export const FULL_FRAC_MIN = 0.05;
export const FULL_FRAC_MAX = 0.6;
export const PERSPEAKER_CAP = 200;

export const DEFAULT_PTT_KEY = "Space";

export const DEFAULT_SETTINGS = Object.freeze({
  master: 1.0,           // 0..1.5 stored, applied capped at MAX_APPLIED_GAIN
  exponent: FALLOFF_EXPONENT,   // 0.6..3.0 — falloff steepness
  hearingM: 0,           // 0 = the full server range; else 5..200 m, only shortens
  // 0 = follow whatever FULL_VOLUME_FRACTION is in force. It stays 0 because no
  // control sets it: persisting a COPY of the code default is what would pin a
  // player to a retired curve the next time the default is retuned — the same
  // trap that hearingM's fraction had. An explicit 0.05..0.6 still wins if a
  // control is ever added.
  fullFrac: 0,
  speakers: {},          // id -> { volume: 0..1, muted: bool }, non-default only
  // --- microphone & devices (all opt-in; these defaults == today's behavior) --
  micMode: "open",       // "open" (voice-activated) | "ptt" (hold a key to talk)
  pttKey: DEFAULT_PTT_KEY,      // KeyboardEvent.code held to transmit in PTT mode
  noiseSuppression: true,      // browser noise suppression on the mic capture
  inputDeviceId: "",     // "" = system default microphone
  outputDeviceId: "",    // "" = system default speaker
});

const fin = (n) => Number.isFinite(Number(n));
const clamp = (n, lo, hi, dflt) => (fin(n) ? Math.min(hi, Math.max(lo, Number(n))) : dflt);
/**
 * Clamp for the "0 means follow the live default" fields. Distinct from `clamp`
 * because the sentinel sits OUTSIDE the valid band: `clamp(0, 5, 200, 0)` returns
 * 5, which would silently turn "follow the server" into "5 metres". Junk and
 * anything <= 0 fall to the sentinel; everything else is clamped into range.
 */
const clampOrFollow = (n, lo, hi) => (fin(n) && Number(n) > 0 ? Math.min(hi, Math.max(lo, Number(n))) : 0);

export const clampMaster = (n) => clamp(n, 0, MASTER_STORE_MAX, DEFAULT_SETTINGS.master);
export const clampExponent = (n) => clamp(n, MIN_FALLOFF_EXPONENT, MAX_FALLOFF_EXPONENT, DEFAULT_SETTINGS.exponent);
/** Personal hearing range in metres. Junk or anything <= 0 means "follow the server". */
export const clampHearingM = (n) => Math.round(clampOrFollow(n, HEARING_MIN_M, HEARING_MAX_M));
/** Inner full-volume zone. 0 (the default) means "follow the current code default". */
export const clampFullFrac = (n) => clampOrFollow(n, FULL_FRAC_MIN, FULL_FRAC_MAX);
/** The full-volume fraction actually in force for a settings object. */
export const effectiveFullFrac = (settings) =>
  clampFullFrac((settings || DEFAULT_SETTINGS).fullFrac) || FULL_VOLUME_FRACTION;
export const clampSpeakerVolume = (n) => clamp(n, 0, 1, 1);
export const clampMicMode = (v) => (v === "ptt" ? "ptt" : "open");
export const clampPttKey = (v) => {
  const s = typeof v === "string" ? v.trim() : "";
  return s && s.length <= 32 ? s : DEFAULT_PTT_KEY;
};
export const clampDeviceId = (v) => (typeof v === "string" && v.length <= 250 ? v : "");
export const clampBool = (v, dflt) => (typeof v === "boolean" ? v : dflt);

function sanitizeSpeakers(raw) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  let count = 0;
  for (const key of Object.keys(raw)) {
    if (count >= PERSPEAKER_CAP) break;
    const e = raw[key];
    if (!e || typeof e !== "object") continue;
    const volume = clampSpeakerVolume(e.volume);
    const muted = !!e.muted;
    // Prune entries that are just the default (volume 1, unmuted) so the map
    // does not grow without bound as players tweak and reset.
    if (volume === 1 && !muted) continue;
    out[String(key)] = { volume, muted };
    count += 1;
  }
  return out;
}

/** Build a validated settings object from anything (parsed JSON, partial, junk). */
export function normalizeSettings(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  return {
    master: clampMaster(r.master),
    exponent: clampExponent(r.exponent),
    hearingM: clampHearingM(r.hearingM),
    fullFrac: clampFullFrac(r.fullFrac),
    speakers: sanitizeSpeakers(r.speakers),
    micMode: clampMicMode(r.micMode),
    pttKey: clampPttKey(r.pttKey),
    noiseSuppression: clampBool(r.noiseSuppression, true),
    inputDeviceId: clampDeviceId(r.inputDeviceId),
    outputDeviceId: clampDeviceId(r.outputDeviceId),
  };
}

/**
 * LiveKit AudioCaptureOptions from settings. Echo cancellation and auto-gain
 * stay ON always (turning them off causes feedback/loudness complaints); only
 * noise suppression and the chosen input device are user-controlled. A blank
 * device id is omitted so the browser default is used.
 */
export function audioCaptureOptions(settings) {
  const s = settings || DEFAULT_SETTINGS;
  const opts = {
    noiseSuppression: clampBool(s.noiseSuppression, true),
    echoCancellation: true,
    autoGainControl: true,
  };
  const id = clampDeviceId(s.inputDeviceId);
  if (id) opts.deviceId = id;
  return opts;
}

/**
 * Convert a stored v2 entry into a v3 one. Applied on every load until the
 * player next saves anything (which writes a real v3 entry); it is pure and
 * idempotent, so re-running it costs nothing and can never drift.
 *
 * The only field that changed meaning is the hearing range: v2 stored a fraction
 * of the live hold radius (see V2_BASIS_RADIUS_M).
 *  - fraction 1.0 (the default — the player never touched the slider) becomes 0,
 *    "follow the server range", so they get the owner's new range in full.
 *  - anything shorter becomes the METRES it was showing them, so a player who
 *    deliberately narrowed their range keeps that distance instead of having it
 *    rescaled out from under them.
 * `fullFrac` is deliberately NOT carried over: it never had a control, so a
 * stored value is only ever a copy of an old default and would pin that player
 * to a retired curve.
 */
export function migrateV2(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  const out = { ...r };
  // normalizeSettings rebuilds from a fixed field list, so retired keys need no
  // delete — EXCEPT fullFrac, which is still a live field: dropping it here is
  // what resets a stored copy of the old curve to "follow the current default".
  delete out.fullFrac;
  // Guarded so this is TRULY idempotent: only a legacy FRACTION rewrites the
  // range. Ungated, a second pass read Number(undefined) -> NaN -> 0 and reset
  // the player's chosen range back to the full server range — widening someone's
  // range unasked is the one direction this migration exists to prevent.
  if (Object.prototype.hasOwnProperty.call(r, "hearingFraction")) {
    const frac = Number(r.hearingFraction);
    out.hearingM = (fin(frac) && frac > 0 && frac < 0.999) ? clampHearingM(frac * V2_BASIS_RADIUS_M) : 0;
  }
  return normalizeSettings(out);
}

/** Load once from localStorage; any failure returns defaults, never throws. */
export function loadSettings(storage) {
  try {
    const store = storage || (typeof window !== "undefined" ? window.localStorage : null);
    if (!store) return normalizeSettings(null);
    const raw = store.getItem(LS_KEY);
    if (raw) return normalizeSettings(JSON.parse(raw));
    // No v3 entry yet: adopt this player's v2 settings instead of resetting them.
    // A v2 entry that is missing or unreadable simply falls through to defaults.
    const legacy = store.getItem(LEGACY_LS_KEY_V2);
    if (legacy) return migrateV2(JSON.parse(legacy));
    return normalizeSettings(null);
  } catch (e) {
    return normalizeSettings(null);
  }
}

export function saveSettings(settings, storage) {
  try {
    const store = storage || (typeof window !== "undefined" ? window.localStorage : null);
    if (!store) return;
    store.setItem(LS_KEY, JSON.stringify(normalizeSettings(settings)));
  } catch (e) { /* private mode / quota — settings still apply in-memory */ }
}

/** The final applied gain for one speaker given its distance CURVE factor. */
export function composeGain(curveFactor, settings, speakerId) {
  const s = settings || DEFAULT_SETTINGS;
  const spk = speakerId != null && s.speakers ? s.speakers[String(speakerId)] : null;
  if (spk && spk.muted) return 0;
  const per = spk && fin(spk.volume) ? Number(spk.volume) : 1;
  const master = fin(s.master) ? Number(s.master) : 1;
  const curve = fin(curveFactor) ? Number(curveFactor) : 1;
  return Math.min(MAX_APPLIED_GAIN, Math.max(0, master * per * curve));
}

/**
 * The curve options voiceFalloff needs, derived from settings + the live server
 * range. Pass the AUDIBLE radius (not the hold radius): the player's slider tops
 * out at the range the owner set, and the few metres of release band above it
 * stay a routing detail they never see.
 */
export function curveConfig(settings, serverRadiusM) {
  const s = settings || DEFAULT_SETTINGS;
  const radius = Number(serverRadiusM) > 0 ? Number(serverRadiusM) : 0;
  const chosen = clampHearingM(s.hearingM);
  return {
    exponent: clampExponent(s.exponent),
    fullFrac: effectiveFullFrac(s),
    // Max hearing can only ever SHORTEN. 0 = "no client cap" (the player has not
    // chosen one), which leaves the bridge's own hold radius as the hard cut.
    maxHearingM: chosen > 0 ? (radius > 0 ? Math.min(chosen, radius) : chosen) : 0,
  };
}

/**
 * Everything the hearing-range slider renders, derived in one place so the page
 * is just markup. `serverRadiusM` is the live AUDIBLE range from the bridge.
 *
 *   value   where the handle sits, in metres (a stored 0 shows the full range)
 *   min/max the bounds — max is the server range, because a player can only
 *           ever shorten, never extend, what the server routes
 *   toStore(v) what to persist for a slider position: dragging to the top stores
 *           0, "follow the server", so a later retune lifts that player with it
 *           instead of pinning them to today's number.
 */
export function hearingSliderModel(settings, serverRadiusM) {
  const s = settings || DEFAULT_SETTINGS;
  // Capped at HEARING_MAX_M so the track can never contain positions that
  // clampHearingM would fold onto one stored value — a slider whose top 49
  // notches all read "200 m" would look broken. The bridge clamps its own range
  // to the same ceiling today; this keeps the UI honest if that ever moves.
  const raw = Number(serverRadiusM) > 0 ? Number(serverRadiusM) : 0;
  const radius = Math.max(1, Math.min(HEARING_MAX_M, Math.round(raw)));
  const chosen = clampHearingM(s.hearingM);
  const value = chosen > 0 ? Math.min(chosen, radius) : radius;
  return {
    value,
    min: Math.min(HEARING_MIN_M, radius),
    max: radius,
    display: `${value} m`,
    toStore: (v) => (Number(v) >= radius ? 0 : clampHearingM(v)),
  };
}

/** Immutable helper: return a new settings object with one speaker updated. */
export function withSpeaker(settings, speakerId, patch) {
  const s = normalizeSettings(settings);
  const id = String(speakerId);
  const cur = s.speakers[id] || { volume: 1, muted: false };
  const next = { volume: clampSpeakerVolume(patch.volume != null ? patch.volume : cur.volume),
                 muted: patch.muted != null ? !!patch.muted : cur.muted };
  const speakers = { ...s.speakers };
  if (next.volume === 1 && !next.muted) delete speakers[id];
  else speakers[id] = next;
  return { ...s, speakers };
}
