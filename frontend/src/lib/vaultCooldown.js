// Vault action cooldowns, read straight off the /me/vault summary.
//
// The backend names every one of these "<action>_cooldown_s" and reports WHOLE
// SECONDS remaining (slay_cooldown_s, redeem_cooldown_s — see vault.summary()).
// Body Drop's limiter is the mod's 10-minute per-SteamID feeder lease, surfaced
// on that same convention as bodydrop_cooldown_s. Knowing it here stops the
// futile press: without it the player pays a full web -> game -> web round trip
// (up to the 25 s ack window) just to be told to wait.
//
// Everything below degrades OPEN. A field that is missing, null, non-numeric or
// implausible reads as "no cooldown" — which is exactly the behaviour before
// this existed: the button stays pressable and the game gets the last word. A
// stuck or corrupt value must never lock a player's button for the session.

export const BODYDROP_COOLDOWN_FIELD = "bodydrop_cooldown_s";
export const PARK_COOLDOWN_FIELD = "park_cooldown_s";

// The mod's lease is 10 minutes. Anything past an hour is not a cooldown, it is
// a bad clock or a bad write — ignore it rather than disable the button on it.
export const COOLDOWN_SANITY_MAX_S = 3600;

// Bounded so a value that churns every 8 s poll can never flood the console.
const WARN_CAP = 8;
const warned = new Set();

function warnOnce(key, message) {
  if (warned.has(key) || warned.size >= WARN_CAP) return;
  warned.add(key);
  console.warn(`[vault] ${message}`);
}

// Seconds remaining on `field`, or 0 for "no cooldown" / anything unusable.
export function cooldownSeconds(vault, field) {
  const raw = vault == null ? undefined : vault[field];
  if (raw == null) return 0;
  if (typeof raw !== "number" && typeof raw !== "string") return 0;
  const n = typeof raw === "number" ? raw : Number(raw.trim());
  if (!Number.isFinite(n) || n <= 0) return 0;
  if (n > COOLDOWN_SANITY_MAX_S) {
    warnOnce(`${field}:${raw}`, `${field}=${raw} is out of range — ignoring the cooldown`);
    return 0;
  }
  return Math.round(n);
}

// The park wait (owner rule 2026-07-31, default 2 min). Same degrade-open rule
// as everything else here: an absent or unusable field leaves the button live
// and the backend gets the last word. Seconds under a minute, so a 2-minute
// wait does not read "1 min" for its last 59 seconds — the backend's refusal
// copy says the same thing.
export function parkButtonState(vault, busy) {
  const seconds = cooldownSeconds(vault, PARK_COOLDOWN_FIELD);
  const inFlight = busy === "park";
  const waitText = seconds > 0
    ? (seconds < 60 ? `${seconds} s` : `${Math.ceil(seconds / 60)} min`)
    : "";
  return {
    seconds,
    disabled: inFlight || seconds > 0,
    label: !inFlight && seconds > 0 ? `Espera ${waitText}` : "Aparcar mi dinosaurio",
    title: seconds > 0
      ? `Guardaste un dino hace poco. Puedes guardar otro en ${waitText}.`
      : "Guarda tu dinosaurio actual en La Bóveda.",
  };
}

// Everything the Body Drop button renders, as data — the button itself decides
// nothing. `disabled`/`title` keep the pre-existing offline and carnivore-only
// gates untouched and add the cooldown on top; minutes round UP, the same way
// the backend's own refusal copy does ((remaining + 59) // 60).
export function bodyDropButtonState(vault, busy) {
  const seconds = cooldownSeconds(vault, BODYDROP_COOLDOWN_FIELD);
  const minutes = seconds > 0 ? Math.ceil(seconds / 60) : 0;
  const inFlight = busy === "bodydrop";
  const online = !!(vault && vault.online);
  // absent bodydrop_max = the backend never spoke on species -> do not gate on it
  const speciesOk = vault && vault.bodydrop_max ? !!vault.bodydrop_max.species_ok : true;
  return {
    seconds,
    minutes,
    disabled: inFlight || !online || !speciesOk || minutes > 0,
    label: !inFlight && minutes > 0 ? `Espera ${minutes} min` : "Body Drop",
    title: !online
      ? "Debes estar en partida para pedir un Body Drop."
      : !speciesOk
        ? "Body Drop alimenta solo a carnívoros."
        : minutes > 0
          ? `Ya pediste un Body Drop hace poco. Puedes pedir otro en ${minutes} min.`
          : "El servidor deja caer un cuerpo fresco junto a ti para que puedas comer.",
  };
}
