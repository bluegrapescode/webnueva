import {
  BAN_COPY, fill, opId, displayName, whenText, confirmSentence, confirmNote, hoursFromDays,
  buildPlaceBody, rowFacts, candidateFacts, suggestHint, refusalText, splitHistory, isBanRefusal,
} from "./webBans";

const REXY = { steam_id: "76561198000000001", name: "Rexy", avatar: "https://a/r.jpg", known: true, alt_names: ["Rexy en Discord"], last_seen: 1755424800 };

describe("webBans", () => {
  test("the owner's words are the copy, verbatim", () => {
    expect(BAN_COPY.findLabel).toBe("¿A quién quieres banear?");
    expect(BAN_COPY.findPlaceholder).toBe("Escribe su nombre — o pega su Steam ID");
    expect(BAN_COPY.howLong).toBe("¿Por cuánto tiempo?");
    expect(BAN_COPY.reasonLabel).toBe("¿Por qué? (opcional — lo verán)");
    expect(BAN_COPY.activeTitle).toBe("Baneados ahora mismo");
    expect(BAN_COPY.activeEmpty).toBe("Nadie está baneado de esta página.");
    expect(BAN_COPY.unbanButton).toBe("Dejarle volver");
    expect(fill(BAN_COPY.unbanConfirm, { name: "Rexy" })).toBe("¿Dejar volver a Rexy?");
  });

  test("confirm sentence: forever by default, the exact promised words", () => {
    expect(confirmSentence(REXY, { expires_at: null })).toBe(
      "Esto baneará a Rexy de esta página web para siempre. Se le cerrará la sesión de inmediato y no podrá volver a entrar.");
    const timed = confirmSentence(REXY, { expires_at: "2026-08-24T14:05:00Z" }, "es-MX");
    expect(timed.startsWith("Esto baneará a Rexy de esta página web hasta el ")).toBe(true);
    expect(timed.endsWith("Se le cerrará la sesión de inmediato y no podrá volver a entrar.")).toBe(true);
    expect(timed).toMatch(/2026/);
  });

  test("confirm note says the server's fold / replace out loud, and nothing otherwise", () => {
    expect(confirmNote({ outcome: "placed" })).toBe("");
    expect(confirmNote({ outcome: "folded_kept_longer", existing: { id: "x" } })).toBe(BAN_COPY.confirmFold);
    expect(confirmNote({ outcome: "escalated", existing: { id: "x" } })).toBe(BAN_COPY.confirmReplace);
    expect(confirmNote(null)).toBe("");
  });

  test("days -> hours (whole, at least one day); forever is null", () => {
    expect(hoursFromDays("forever", 7)).toBeNull();
    expect(hoursFromDays("days", 7)).toBe(168);
    expect(hoursFromDays("days", 0)).toBe(24);
    expect(hoursFromDays("days", "3.9")).toBe(72);
    expect(hoursFromDays("days", "abc")).toBe(24);
  });

  test("the request body carries the pick, the window and the op id; empty reason stays empty", () => {
    const body = buildPlaceBody(REXY, { mode: "days", days: 2, reason: "  Spam  ", opId: "ban-abc123456789" });
    expect(body).toEqual({ steam_id: "76561198000000001", player_name: "Rexy", avatar: "https://a/r.jpg", reason: "Spam", hours: 48, op_id: "ban-abc123456789" });
    const forever = buildPlaceBody(REXY, { mode: "forever", days: 7, reason: "", opId: "ban-abc123456789" });
    expect(forever.hours).toBeNull();
    expect(forever.reason).toBe("");
    expect(buildPlaceBody(null, { mode: "forever", opId: "x" }).steam_id).toBe("");
  });

  test("op ids are fresh, well-shaped and server-acceptable (^[A-Za-z0-9_-]{8,64}$)", () => {
    const a = opId();
    const b = opId();
    expect(a).not.toBe(b);
    // WebCrypto path is 12 chars; the no-crypto fallback (this test env) is
    // longer - both stay inside the server's shape.
    expect(a).toMatch(/^ban-[a-z0-9]{12,40}$/);
    expect(a).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    const many = new Set(Array.from({ length: 200 }, () => opId()));
    expect(many.size).toBe(200);
    // deterministic bytes -> deterministic id (36 wraps to 'a', 37 to 'b')
    expect(opId(new Uint8Array([0, 1, 2, 35, 36, 37, 0, 0, 0, 0, 0, 0]))).toBe("ban-abc9abaaaaaa");
  });

  test("a row is never nameless", () => {
    expect(displayName({ player_name: "Rexy" })).toBe("Rexy");
    expect(displayName({ name: "", current_name: "Rexy2" })).toBe("Rexy2");
    expect(displayName({ steam_id: "76561198000000001" })).toBe("Cuenta de Steam terminada en 0001");
    expect(displayName(null)).toBe("Cuenta de Steam terminada en ????");
  });

  test("row facts: reason · when · by whom, per state", () => {
    expect(rowFacts({ reason: "Spam", permanent: true, state: "active", by_name: "crysis" })).toEqual(["Spam", "para siempre", "por crysis"]);
    expect(rowFacts({ reason: "", state: "lifted" })).toEqual(["desbaneado"]);
    expect(rowFacts({ reason: "", state: "expired" })).toEqual(["terminó"]);
    const timed = rowFacts({ reason: "", state: "active", permanent: false, expires_at: "2026-08-24T14:05:00Z" }, "es-MX");
    expect(timed).toHaveLength(1);
    expect(timed[0].startsWith("hasta el ")).toBe(true);
    expect(rowFacts(null)).toEqual([]);
  });

  test("candidate facts: unknown said honestly, alt names, last seen", () => {
    const facts = candidateFacts(REXY, "es-MX");
    expect(facts[0]).toBe("también conocido como Rexy en Discord");
    expect(facts[1].startsWith("última vez aquí ")).toBe(true);
    expect(candidateFacts({ steam_id: "76561198999999999", known: false })).toEqual([BAN_COPY.unknownAccount]);
  });

  test("hints: nobody / not an id / nothing when people are shown", () => {
    expect(suggestHint("name", 0)).toBe(BAN_COPY.noneFound);
    expect(suggestHint("not_an_id", 0)).toBe(BAN_COPY.notAnId);
    expect(suggestHint("name", 3)).toBe("");
    expect(suggestHint("empty", 0)).toBe("");
  });

  test("the server's sentence wins over the fallback; junk falls back", () => {
    expect(refusalText({ response: { data: { detail: "No puedes banearte a ti mismo." } } }, "x")).toBe("No puedes banearte a ti mismo.");
    expect(refusalText({ response: { data: { detail: { a: 1 } } } }, "fallback")).toBe("fallback");
    expect(refusalText(new Error("net"))).toBe(BAN_COPY.genericFail);
  });

  test("history is only what is not active", () => {
    expect(splitHistory([{ state: "active" }, { state: "lifted" }, null, { state: "expired" }])).toEqual([{ state: "lifted" }, { state: "expired" }]);
    expect(splitHistory("bad")).toEqual([]);
  });

  test("the ban refusal is told apart from an expired token by X-Web-Ban", () => {
    expect(isBanRefusal({ response: { status: 401, headers: { "x-web-ban": "1" } } })).toBe(true);
    expect(isBanRefusal({ response: { status: 401, headers: { get: (k) => (k === "x-web-ban" ? "1" : null) } } })).toBe(true);
    expect(isBanRefusal({ response: { status: 401, headers: {} } })).toBe(false);
    expect(isBanRefusal(new Error("net"))).toBe(false);
  });

  test("whenText: forever, or the date", () => {
    expect(whenText(null)).toBe("para siempre");
    expect(whenText("garbage")).toBe("para siempre");
    expect(whenText("2026-08-24T14:05:00Z", "es-MX").startsWith("hasta el ")).toBe(true);
  });
});
