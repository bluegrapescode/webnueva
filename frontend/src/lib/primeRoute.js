/**
 * Prime — the ten requirements read as a ROUTE, not a checklist.
 *
 * The mod publishes prime state in two different shapes and this module is the
 * single place that reconciles them:
 *   - `meState.prime_progress.conditions` — a PARTIAL map of condition id ->
 *     either a boolean flag or a `{n|count, cap}` counter. Today only a subset
 *     (e.g. {5,6,7,8,10}) actually arrives; the rest land later. Never assume
 *     all ten are present.
 *   - `dino.l_mig` / `dino.l_pat` (+ `dino.prime_progress.{mig,pat}`) — the two
 *     zone counters, which the panel has always shown even when `conditions`
 *     is missing entirely.
 *
 * Everything here is pure and total: any input shape (null, array, string,
 * NaN caps, negative counts) yields a valid route rather than a throw, because
 * the caller renders this on a 3 s poll and a throw would blank the page.
 * Cost is O(n) over at most ten ids with no work outside the returned arrays.
 */

// Condition ids 1-10. These are the SAME words the game says in its Prime
// banners (mod `PRIME_CONDITION_LABELS_LOC`, reworded 2026-07-28 with the
// Estación InGen voice) — if the two ever drift, a player is told a
// requirement has one name in game and another on the site.
export const PRIME_CONDITION_LABELS = {
  1: "De cría, pisa un Santuario",
  2: "Nace en un nido con un progenitor",
  3: "Come de todo: 1% de cada nutriente",
  4: "Entra en la Migración Masiva",
  5: "Recorre 2 rutas de Migración",
  6: "Marca 4 territorios de Patrulla",
  7: "Llega fértil hasta el final",
  8: "Sin espasmos en toda la vida",
  9: "Saca adelante a tus crías",
  10: "Especie con ventaja: Hypsi, Troodon, Beipi, Dryo o Deino",
};

// Short forms for the station markers on the route, where the label sits under
// a 22 px dot and a long string would collide with its neighbour.
export const PRIME_CONDITION_SHORT = {
  1: "Santuario de cría",
  2: "Nido con progenitor",
  3: "1% de cada nutriente",
  4: "Migración Masiva",
  5: "2 rutas de Migración",
  6: "4 territorios de Patrulla",
  7: "Siempre fértil",
  8: "Sin espasmos",
  9: "Crías a Subadulto",
  10: "Especie con ventaja",
};

// The two counter conditions. They are always drawn, even with no `conditions`
// payload at all, because their counts have their own top-level source.
export const PRIME_COUNTER_IDS = [5, 6];
export const PRIME_DEFAULT_CAPS = { 5: 2, 6: 4 };

function isPlainObject(v) {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

/**
 * Coerce to a finite number WITHOUT the `Number(null) === 0` trap: null, "",
 * booleans and objects are "no value", not zero. A count that silently becomes
 * 0 reads to the player as "you have visited none", which is a lie.
 */
function finiteOrNull(v) {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function labelFor(id) {
  if (PRIME_CONDITION_LABELS[id]) return PRIME_CONDITION_LABELS[id];
  return String(id)
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase()) || String(id);
}

function shortFor(id) {
  return PRIME_CONDITION_SHORT[id] || labelFor(id);
}

/**
 * Read one condition value into {met, count, cap, kind}. A counter value is
 * met at count >= cap; a flag is met when truthy. Missing/garbage -> not met.
 */
export function readCondition(value) {
  if (isPlainObject(value)) {
    const count = finiteOrNull(value.n != null ? value.n : value.count);
    const cap = finiteOrNull(value.cap);
    if (count != null || cap != null) {
      const safeCap = cap != null && cap > 0 ? cap : 1;
      const safeCount = count != null && count > 0 ? count : 0;
      return { met: safeCount >= safeCap, count: safeCount, cap: safeCap, kind: "counter" };
    }
    return { met: false, count: null, cap: null, kind: "flag" };
  }
  // Fail CLOSED on anything that is not an explicit yes. A bare `!!value` reads
  // `[]`, `Infinity` and any stray string as DONE, which would tell a player he
  // has cleared a requirement he has not touched.
  const met = value === true || value === 1 || value === "1" || value === "true";
  return { met, count: null, cap: null, kind: "flag" };
}

/**
 * Build the route. `meState` is the whole /api/me payload; `dino` defaults to
 * `meState.dino` so callers cannot pass a mismatched pair by accident.
 */
export function buildPrimeRoute(meState) {
  const state = isPlainObject(meState) ? meState : {};
  const dino = isPlainObject(state.dino) ? state.dino : {};
  const conditions = isPlainObject(state.prime_progress) && isPlainObject(state.prime_progress.conditions)
    ? state.prime_progress.conditions
    : {};
  const dinoProgress = isPlainObject(dino.prime_progress) ? dino.prime_progress : {};

  // Counter sources, in the same precedence the panel has always used:
  // top-level dino counter first, then the smaller dino.prime_progress shape,
  // then whatever `conditions` carries, then the documented default cap.
  const counterState = {};
  PRIME_COUNTER_IDS.forEach((id) => {
    const key = id === 5 ? "mig" : "pat";
    const nested = isPlainObject(dinoProgress[key]) ? dinoProgress[key] : {};
    const fromConditions = readCondition(conditions[id] != null ? conditions[id] : conditions[String(id)]);
    const count = finiteOrNull(dino[id === 5 ? "l_mig" : "l_pat"]);
    const nestedCount = finiteOrNull(nested.count);
    const cap = finiteOrNull(nested.cap);
    const resolvedCount = count != null ? count
      : nestedCount != null ? nestedCount
        : fromConditions.count != null ? fromConditions.count : 0;
    const resolvedCap = cap != null && cap > 0 ? cap
      : fromConditions.cap != null && fromConditions.cap > 0 ? fromConditions.cap
        : PRIME_DEFAULT_CAPS[id];
    counterState[id] = {
      count: Math.max(0, resolvedCount),
      cap: Math.max(1, resolvedCap),
    };
  });

  // Station ids: the two counters always, plus every id the mod has published.
  const ids = new Set(PRIME_COUNTER_IDS);
  Object.keys(conditions).forEach((k) => {
    const n = finiteOrNull(k);
    if (n != null && n > 0) ids.add(n);
  });

  const stations = Array.from(ids)
    .sort((a, b) => a - b)
    .map((id) => {
      if (PRIME_COUNTER_IDS.indexOf(id) !== -1) {
        const { count, cap } = counterState[id];
        return {
          id,
          label: labelFor(id),
          short: shortFor(id),
          kind: "counter",
          count,
          cap,
          met: count >= cap,
        };
      }
      const read = readCondition(conditions[id] != null ? conditions[id] : conditions[String(id)]);
      return {
        id,
        label: labelFor(id),
        short: shortFor(id),
        kind: read.kind,
        count: read.count,
        cap: read.cap,
        met: read.met,
      };
    });

  const doneCount = stations.reduce((n, s) => n + (s.met ? 1 : 0), 0);
  const total = stations.length;
  const pending = stations.filter((s) => !s.met);

  return {
    stations,
    doneCount,
    total,
    // Percent of the route walked. No stations -> 0, never NaN.
    pct: total > 0 ? Math.round((doneCount / total) * 100) : 0,
    isPrime: !!dino.is_prime,
    current: pending.length > 0 ? pending[0] : null,
    next: pending.length > 1 ? pending[1] : null,
  };
}

/**
 * The one-line hint under the "en curso" card: how far off that station is.
 * Counters say what is left; flags just say they have not started.
 */
export function stationHint(station) {
  if (!isPlainObject(station)) return "";
  if (station.kind === "counter") {
    const count = finiteOrNull(station.count);
    const cap = finiteOrNull(station.cap);
    if (count == null || cap == null) return "Sin datos todavía";
    const left = Math.max(0, cap - count);
    if (left <= 0) return "Ya la tienes";
    return `Llevas ${count} de ${cap} · te ${left === 1 ? "falta una" : `faltan ${left}`}`;
  }
  return station.met ? "Ya la tienes" : "Aún sin empezar";
}
