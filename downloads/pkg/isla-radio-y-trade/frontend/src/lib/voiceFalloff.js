/**
 * Proximity-voice DISTANCE FALLOFF (client side).
 *
 * The voice bridge decides WHO you hear (it is the sole subscriber and only ever
 * subscribes players inside the audible radius). This module decides HOW LOUD
 * each of them is, by the real per-speaker distance the bridge now reports on
 * GET /positions. LiveKit has no server-side per-listener volume, so without this
 * every subscribed voice arrived at 100% — somebody near the edge of the range as
 * loud as somebody on top of you.
 *
 * The protocol is authoritative-gated and fail-safe in ONE direction only:
 *  - authoritative reply with a per-speaker distance  -> fade by that distance,
 *    and HARD-CUT to 0 past the hold radius (so any speaker that ever leaks past
 *    the routing is silenced here as defence-in-depth).
 *  - authoritative reply but a speaker's distance is momentarily unknown, OR a
 *    NON-authoritative reply (bridge degraded / feed stalled / token issue / poll
 *    failed) -> FULL volume. The fade can be missing, it can never mute a call.
 *
 * The curve is parameterized so the player's own settings (steepness, max hearing
 * distance) drive it; VoiceContext composes master + per-speaker volume + mute on
 * top of the factor this module produces.
 */

// Only a fallback: the live value arrives from the bridge on every /positions
// reply, so a retune stays ONE number on the box. Kept in step with the bridge
// default so the very first render (before the first poll) shows the truth.
export const DEFAULT_AUDIBLE_RADIUS_M = 100;
// The bridge's release band is always the range + 5. Only used to seed the hard
// cut before the first poll answers; seeding it with the AUDIBLE radius would
// have the client cutting 5 m short of the server for that first instant.
export const DEFAULT_HOLD_RADIUS_M = DEFAULT_AUDIBLE_RADIUS_M + 5;
// Inner slice of the radius that stays at FULL volume, as a fraction of it. A
// fraction rescales when the range is retuned, which is the whole hazard: at the
// old 0.5 the flat zone would have gone 17 m -> 50 m with the range, i.e. half
// the map equally loud — the "everyone talking at once" problem the range was
// once cut for. NEAR_ZONE_MAX_M is what actually holds the line, because the
// range is retunable on the box with no site deploy (see docs/CONFIG.md) and no
// test runs on that path.
export const FULL_VOLUME_FRACTION = 0.2;
export const NEAR_ZONE_MAX_M = 25;
// Curve shape. 1.0 = a gentle linear fade from the full-volume zone to silence at
// the cut-off (at 100 m range / 105 m hold: ~88% at 30 m, ~65% at 50 m, ~41% at
// 70 m, ~18% at 90 m). Higher drops sooner; the steepness slider spans 0.6–3.0.
export const FALLOFF_EXPONENT = 1.0;
export const MIN_FALLOFF_EXPONENT = 0.6;
export const MAX_FALLOFF_EXPONENT = 3.0;

export const DEFAULT_POLL_MS = 1000;
export const MIN_POLL_MS = 750; // bridge allows 10 req/s per identity; we use ~1
export const MAX_POLL_MS = 5000;
export const ERROR_BACKOFF_MS = 5000;
export const TOKEN_REMINT_MIN_MS = 30000;

const fin = (n) => Number.isFinite(Number(n));

/**
 * Volume factor (0..1) for a distance in metres.
 *   cutR    hard cut-off — 0 at and beyond this (defaults to the audible radius).
 *   opts.nearRadiusM  sizes the full-volume inner zone (defaults to cutR); pass
 *                     the audible radius so shortening the cut does not also shrink
 *                     the close-range full-volume bubble.
 *   opts.exponent     curve steepness. opts.fullFrac  inner-zone fraction.
 * Any unusable input fails SAFE to 1 (never invents silence).
 */
export function volumeForDistance(distanceM, cutR = DEFAULT_AUDIBLE_RADIUS_M, opts = {}) {
  const d = Number(distanceM);
  const cut = Number(cutR);
  if (!fin(d) || !fin(cut) || cut <= 0) return 1;
  if (d <= 0) return 1;
  if (d >= cut) return 0; // hard cut wins over everything below
  const exponent = fin(opts.exponent) && Number(opts.exponent) > 0 ? Number(opts.exponent) : FALLOFF_EXPONENT;
  let fullFrac = fin(opts.fullFrac) ? Number(opts.fullFrac) : FULL_VOLUME_FRACTION;
  fullFrac = Math.min(0.9, Math.max(0, fullFrac));
  const nearBase = fin(opts.nearRadiusM) && Number(opts.nearRadiusM) > 0 ? Number(opts.nearRadiusM) : cut;
  // Capped in METRES as well as by fraction: the fraction alone would rescale the
  // flat zone with any future range retune. Never let near reach the cut either.
  const near = Math.min(nearBase * fullFrac, NEAR_ZONE_MAX_M, cut * 0.999);
  if (d <= near) return 1;
  const v = Math.pow((cut - d) / (cut - near), exponent);
  if (!Number.isFinite(v)) return 1;
  return Math.min(1, Math.max(0, v));
}

/**
 * The hard cut-off for one listener: the bridge's hold radius, shortened by the
 * player's own max-hearing if they set one. THE one place this rule lives — a
 * personal setting can only ever shorten, never extend, what the server routes,
 * and that has to be true by construction rather than by two call sites agreeing.
 */
export function resolveCut(holdRadiusM, maxHearingM) {
  const hold = Number(holdRadiusM);
  if (!fin(hold) || hold <= 0) return 0;
  const max = Number(maxHearingM);
  return fin(max) && max > 0 ? Math.min(hold, max) : hold;
}

/** Clamp a bridge-suggested poll interval into the range we are willing to run. */
export function clampPollMs(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_POLL_MS;
  return Math.min(MAX_POLL_MS, Math.max(MIN_POLL_MS, n));
}

/**
 * Volume factor per identity from ONE /positions payload.
 *
 * Gated strictly on payload.authoritative: a non-authoritative (degraded) reply
 * or a missing speakers map -> 1 for every held id (fail-safe; a bridge hiccup
 * never silences a call). For an authoritative reply:
 *   - id present with a finite distance -> faded by the curve, hard-cut at the
 *     hold radius (shortened by the user's max-hearing setting).
 *   - id present with distance null (position missing this frame) -> 1.
 *   - id ABSENT from speakers -> one-poll grace: first absent poll keeps 1, a
 *     second consecutive absent poll -> 0 (covers a track that attached a beat
 *     before the bridge's snapshot; poke() shortens the window).
 *
 * opts: { radiusFallback, absentStreak(Map), exponent, fullFrac, maxHearingM }
 */
export function volumesFromPositions(payload, identities, opts = {}) {
  const out = new Map();
  const ids = Array.from(identities || []).map(String);
  const streak = opts.absentStreak instanceof Map ? opts.absentStreak : null;
  const speakers = payload && typeof payload === "object" ? payload.speakers : null;
  const authoritative = !!(payload && payload.authoritative) && speakers && typeof speakers === "object";

  if (!authoritative) {
    for (const id of ids) out.set(id, 1);
    if (streak) streak.clear();
    return out;
  }

  const audibleR = Number(payload.audible_radius_m) > 0 ? Number(payload.audible_radius_m)
    : (Number(opts.radiusFallback) > 0 ? Number(opts.radiusFallback) : DEFAULT_AUDIBLE_RADIUS_M);
  const holdR = Number(payload.hold_radius_m) > 0 ? Number(payload.hold_radius_m) : audibleR;
  const cut = resolveCut(holdR, opts.maxHearingM);

  for (const id of ids) {
    const entry = Object.prototype.hasOwnProperty.call(speakers, id) ? speakers[id] : undefined;
    if (entry === undefined) {
      // Absent from the subscription snapshot: grace one poll, then silence.
      const n = (streak ? streak.get(id) || 0 : 0) + 1;
      if (streak) streak.set(id, n);
      out.set(id, n >= 2 ? 0 : 1);
      continue;
    }
    if (streak) streak.set(id, 0);
    const d = entry && entry.distance_m;
    if (!fin(d)) {
      out.set(id, 1); // subscribed + in room but position missing this frame
    } else {
      out.set(id, volumeForDistance(Number(d), cut, {
        nearRadiusM: audibleR, exponent: opts.exponent, fullFrac: opts.fullFrac,
      }));
    }
  }
  if (streak) {
    for (const key of Array.from(streak.keys())) if (!out.has(key)) streak.delete(key);
  }
  return out;
}

/**
 * The poll loop. Everything it touches is injected so the whole lane — not just
 * the curve — is testable without a browser, a room or a network.
 *
 * deps: {
 *   getToken()          -> current LiveKit JWT (the bridge authenticates /positions with it)
 *   remintToken()       -> Promise<string|null>, at most once per TOKEN_REMINT_MIN_MS
 *   getIdentities()     -> iterable of identities we currently hold remote audio for
 *   applyVolume(id, f)  -> apply the distance CURVE FACTOR for that speaker (the
 *                          caller composes master/per-speaker/mute on top)
 *   getCurveConfig()    -> optional {exponent, fullFrac, maxHearingM} from user settings
 *   reportDistances(m, holdRadiusM) -> optional; the per-speaker distance map this
 *                          poll saw, so the UI can recompute the curve instantly
 *                          on a slider change without waiting for the next poll
 *   fetchImpl(url,init) -> fetch
 *   setTimer/clearTimer/now, onLog(msg, extra)
 * }
 */
export class VoiceFalloff {
  constructor(deps) {
    this.deps = deps;
    this.timer = null;
    this.running = false;
    this.radius = DEFAULT_AUDIBLE_RADIUS_M;
    // Pacing stamps start FAR in the past, never at 0: with a 0 stamp the very
    // first re-mint / first poke falls inside its own window and is swallowed.
    this.lastRemintAt = -1e9;
    this.lastPokeAt = -1e9;
    this.inFlight = false;
    this.degraded = false; // true while we are failing safe at full volume
    this._absentStreak = new Map();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.degraded = false;
    this._schedule(0);
  }

  /**
   * A voice just came into range — attenuate it now instead of leaving it at
   * full volume until the next scheduled poll. Bounded to one extra poll per
   * MIN_POLL_MS so a burst of joins cannot turn into a burst of requests.
   */
  poke() {
    if (!this.running) { this.start(); return; }
    if (this.inFlight) return;
    const now = this.deps.now();
    if (now - this.lastPokeAt < MIN_POLL_MS) return;
    this.lastPokeAt = now;
    this._schedule(0);
  }

  stop() {
    this.running = false;
    if (this.timer != null) {
      try { this.deps.clearTimer(this.timer); } catch (e) { /* already fired */ }
    }
    this.timer = null;
  }

  _schedule(ms) {
    if (!this.running) return;
    if (this.timer != null) {
      try { this.deps.clearTimer(this.timer); } catch (e) { /* already fired */ }
    }
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      this.tick();
    }, ms);
  }

  _allFullVolume(reason) {
    let touched = 0;
    for (const id of this.deps.getIdentities() || []) {
      try { this.deps.applyVolume(String(id), 1); touched += 1; } catch (e) { /* element gone */ }
    }
    this._absentStreak.clear();
    if (!this.degraded && touched > 0) {
      this.degraded = true;
      if (this.deps.onLog) this.deps.onLog("falloff unavailable - voices at full volume", reason);
    }
    return touched;
  }

  /** One poll. Never throws, never leaves the loop unscheduled while running. */
  async tick() {
    if (!this.running || this.inFlight) return;
    const ids = Array.from(this.deps.getIdentities() || []);
    if (ids.length === 0) {
      // Nobody in earshot: nothing to attenuate and nothing worth polling for.
      this._absentStreak.clear();
      this._schedule(clampPollMs(null));
      return;
    }
    this.inFlight = true;
    let nextMs = clampPollMs(null);
    try {
      const token = this.deps.getToken();
      if (!token) {
        this._allFullVolume("no_token");
      } else {
        const res = await this.deps.fetchImpl("/positions", {
          method: "GET",
          headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
          cache: "no-store",
          credentials: "same-origin",
        });
        const status = res && res.status;
        if (status === 200) {
          const payload = await res.json();
          const authoritative = !!(payload && payload.authoritative);
          const audibleR = Number(payload && payload.audible_radius_m);
          const holdR = Number(payload && payload.hold_radius_m);
          if (audibleR > 0) this.radius = audibleR;
          const cfg = this.deps.getCurveConfig ? (this.deps.getCurveConfig() || {}) : {};
          const volumes = volumesFromPositions(payload, ids, {
            radiusFallback: this.radius,
            absentStreak: this._absentStreak,
            exponent: cfg.exponent, fullFrac: cfg.fullFrac, maxHearingM: cfg.maxHearingM,
          });
          let applied = 0;
          for (const [id, v] of volumes) {
            try { this.deps.applyVolume(id, v); applied += 1; } catch (e) { /* element gone */ }
          }
          // Hand the raw distances to the UI so a settings change re-fades at once.
          if (this.deps.reportDistances) {
            const dm = new Map();
            const sp = payload && payload.speakers;
            if (authoritative && sp) {
              for (const id of ids) {
                const e = Object.prototype.hasOwnProperty.call(sp, id) ? sp[id] : undefined;
                dm.set(String(id), e && Number.isFinite(Number(e.distance_m)) ? Number(e.distance_m) : null);
              }
            }
            // (distances, hold radius = the hard cut, audible radius = near-zone size)
            try { this.deps.reportDistances(dm, holdR > 0 ? holdR : this.radius, this.radius); } catch (e) { /* ui gone */ }
          }
          if (authoritative) {
            if (this.degraded && applied > 0) {
              this.degraded = false;
              if (this.deps.onLog) this.deps.onLog("falloff active", { radius_m: this.radius });
            }
          } else if (!this.degraded && applied > 0) {
            // A degraded (non-authoritative) 200: everyone at full volume by design.
            this.degraded = true;
            if (this.deps.onLog) this.deps.onLog("falloff unavailable - bridge degraded, voices at full volume");
          }
          nextMs = clampPollMs(payload && payload.poll_ms);
        } else if (status === 401 || status === 403) {
          // Token aged out mid-session. Re-mint at most once per window, then
          // fail safe until it lands.
          this._allFullVolume("token_rejected");
          const now = this.deps.now();
          if (now - this.lastRemintAt >= TOKEN_REMINT_MIN_MS && this.deps.remintToken) {
            this.lastRemintAt = now;
            try { await this.deps.remintToken(); } catch (e) { /* next tick retries */ }
          }
          nextMs = ERROR_BACKOFF_MS;
        } else {
          // 404 not-in-game, 429, 5xx, bridge down: full volume, slow down.
          this._allFullVolume(`status_${status}`);
          nextMs = ERROR_BACKOFF_MS;
        }
      }
    } catch (e) {
      this._allFullVolume("poll_failed");
      nextMs = ERROR_BACKOFF_MS;
    } finally {
      this.inFlight = false;
      this._schedule(nextMs);
    }
  }
}
