// Baneos de la página web — the pure half of the Admin "Baneos" tab (2026-08-17).
//
// Everything here is a plain function over the API's shapes, so it is testable
// with no DOM: the request body the tab sends, the sentence the confirm card
// says, the facts a list row shows, and how a refusal is read out of an axios
// error. BansTab.jsx renders; nothing here decides anything the server does not
// also decide (self-ban, owner-ban, folding, the arm/confirm handshake all live
// in web/backend/webban.py and are shown here verbatim).
//
// Spanish copy is the whole point of this file: the site is LATAM Spanish and the
// owner asked for "max friendly, non tech".

export const BAN_COPY = {
  title: "Baneos",
  lede: "Banea a alguien de esta página web, o déjale volver.",
  findLabel: "¿A quién quieres banear?",
  findPlaceholder: "Escribe su nombre — o pega su Steam ID",
  noneFound: "No encontramos a nadie con ese nombre. Revisa cómo se escribe, o pega su Steam ID.",
  notAnId: "Eso no parece un nombre ni un Steam ID. Un Steam ID tiene 17 dígitos y empieza por 7656.",
  unknownAccount: "No hemos visto esta cuenta por aquí. Aun así puedes banearla.",
  bannedChip: "ya baneado",
  alsoCalled: "también conocido como {names}",
  lastSeen: "última vez aquí {date}",
  howLong: "¿Por cuánto tiempo?",
  forever: "para siempre",
  days: "días",
  reasonLabel: "¿Por qué? (opcional — lo verán)",
  reasonPlaceholder: "Lo verán si intentan entrar.",
  banButton: "Banearle de esta página web",
  cancel: "Cancelar",
  confirmTitle: "¿Seguro?",
  confirmBody: "Esto baneará a {name} de esta página web {when}. Se le cerrará la sesión de inmediato y no podrá volver a entrar.",
  confirmFold: "Ya tiene un baneo más largo. Se mantendrá ese, y no se acortará nada.",
  confirmReplace: "Ya tiene un baneo registrado. Este lo sustituye.",
  confirmYes: "Sí, banearle",
  doneBan: "Listo. {name} ya no puede usar esta página web.",
  activeTitle: "Baneados ahora mismo",
  activeEmpty: "Nadie está baneado de esta página.",
  unbanButton: "Dejarle volver",
  unbanConfirm: "¿Dejar volver a {name}?",
  doneUnban: "Listo. {name} ya puede volver a entrar.",
  historyToggle: "Ver baneos anteriores ({count})",
  historyTitle: "Baneos anteriores",
  liftedWord: "desbaneado",
  endedWord: "terminó",
  untilWord: "hasta el {date}",
  byWord: "por {name}",
  accountTail: "Cuenta de Steam terminada en {tail}",
  genericFail: "Eso no funcionó, y no se cambió nada.",
  listFail: "No se pudo leer la lista de baneos.",
  unavailable: "La lista de baneos no está disponible ahora mismo.",
  healthWarning: "Ojo: la comprobación de baneos ha tenido problemas leyendo su lista, así que puede que ahora mismo no esté dejando fuera a todo el mundo. Si esto sigue apareciendo, avisa a soporte.",
};

export function fill(template, vars) {
  return String(template || "").replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] != null ? String(vars[k]) : ""));
}

// A fresh operation id per PRESS. The server pairs the preview and the confirm
// on it (arm-then-confirm), so it is minted when the form opens and never reused.
let opCounter = 0;
export function opId(randomBytes) {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  let tail = "";
  try {
    const bytes = randomBytes || (typeof crypto !== "undefined" && crypto.getRandomValues
      ? crypto.getRandomValues(new Uint8Array(12)) : null);
    if (!bytes) throw new Error("no crypto");
    for (let i = 0; i < bytes.length; i += 1) tail += alphabet[bytes[i] % 36];
  } catch (e) {
    // No WebCrypto (old browser, test env): time + random + a counter, still
    // unique per press and still inside the server's ^[A-Za-z0-9_-]{8,64}$.
    opCounter = (opCounter + 1) % 1296;
    tail = Date.now().toString(36) + Math.random().toString(36).slice(2, 10) + opCounter.toString(36);
  }
  return "ban-" + tail;
}

// The name a row is shown under, never blank: the stored name, the current
// persona, or "Cuenta de Steam terminada en 1234".
export function displayName(person) {
  const name = String((person && (person.player_name || person.name || person.current_name)) || "").trim();
  if (name) return name;
  const sid = String((person && person.steam_id) || "");
  return fill(BAN_COPY.accountTail, { tail: sid.slice(-4) || "????" });
}

export function fmtDate(iso, locale = "es-MX") {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString(locale, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "";
  }
}

// "para siempre" or "hasta el 21 ago 2026, 14:05" — the sentence's when-part.
export function whenText(expiresAt, locale) {
  if (!expiresAt) return BAN_COPY.forever;
  const text = fmtDate(expiresAt, locale);
  return text ? fill(BAN_COPY.untilWord, { date: text }) : BAN_COPY.forever;
}

export function confirmSentence(person, preview, locale) {
  return fill(BAN_COPY.confirmBody, { name: displayName(person), when: whenText(preview && preview.expires_at, locale) });
}

// The second sentence the confirm card must not hide: the server's own preview
// said the ban folds into a longer one, or replaces an existing one.
export function confirmNote(preview) {
  if (!preview) return "";
  if (preview.outcome === "folded_kept_longer") return BAN_COPY.confirmFold;
  if (preview.outcome && preview.outcome !== "placed" && preview.existing) return BAN_COPY.confirmReplace;
  return "";
}

// days -> hours, whole and at least one. null = para siempre.
export function hoursFromDays(mode, days) {
  if (mode !== "days") return null;
  const n = Math.floor(Number(days) || 0);
  return Math.max(1, n) * 24;
}

export function buildPlaceBody(person, { mode, days, reason, opId: op }) {
  return {
    steam_id: person ? String(person.steam_id || "") : "",
    player_name: person ? String(person.name || person.player_name || "").slice(0, 64) : "",
    avatar: person ? String(person.avatar || "").slice(0, 512) : "",
    reason: String(reason || "").trim().slice(0, 100),
    hours: hoursFromDays(mode, days),
    op_id: op,
  };
}

// The facts under a name in the lists: reason · when · by whom.
export function rowFacts(row, locale) {
  const parts = [];
  if (!row) return parts;
  if (row.reason) parts.push(row.reason);
  if (row.state === "lifted") parts.push(BAN_COPY.liftedWord);
  else if (row.state === "expired") parts.push(BAN_COPY.endedWord);
  else if (row.permanent) parts.push(BAN_COPY.forever);
  else {
    const until = fmtDate(row.expires_at, locale);
    if (until) parts.push(fill(BAN_COPY.untilWord, { date: until }));
  }
  if (row.by_name) parts.push(fill(BAN_COPY.byWord, { name: row.by_name }));
  return parts;
}

// The facts under a drop-down candidate.
export function candidateFacts(person, locale) {
  const facts = [];
  if (!person) return facts;
  if (person.known === false) facts.push(BAN_COPY.unknownAccount);
  if (Array.isArray(person.alt_names) && person.alt_names.length) {
    facts.push(fill(BAN_COPY.alsoCalled, { names: person.alt_names.join(", ") }));
  }
  if (person.last_seen) {
    const seen = fmtDate(new Date(Number(person.last_seen) * 1000).toISOString(), locale);
    if (seen) facts.push(fill(BAN_COPY.lastSeen, { date: seen }));
  }
  return facts;
}

export function suggestHint(kind, count) {
  if (count > 0) return "";
  if (kind === "not_an_id") return BAN_COPY.notAnId;
  if (kind === "empty") return "";
  return BAN_COPY.noneFound;
}

// The server's own sentence out of an axios error, else the fallback.
export function refusalText(err, fallback) {
  const detail = err && err.response && err.response.data && err.response.data.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback || BAN_COPY.genericFail;
}

// Only rows that are NOT active are history to a reader; the active ones are
// already above.
export function splitHistory(history) {
  return (Array.isArray(history) ? history : []).filter((r) => r && r.state !== "active");
}

// Is this axios error the website-ban refusal (X-Web-Ban rides the 401)?
export function isBanRefusal(err) {
  const res = err && err.response;
  if (!res) return false;
  const headers = res.headers || {};
  const flag = typeof headers.get === "function" ? headers.get("x-web-ban") : (headers["x-web-ban"] || headers["X-Web-Ban"]);
  return String(flag || "") === "1";
}
