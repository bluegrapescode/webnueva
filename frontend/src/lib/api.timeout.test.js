/**
 * @jest-environment node
 *
 * Client abort ordering law: client abort > server wait > measured latency.
 *
 * This drives the REAL axios instance exported by lib/api against a REAL socket
 * that accepts the connection and then never answers — no adapter stubs, no
 * fake timers. The node environment is deliberate: it gives axios its http
 * adapter and a real TCP connection, and skips jsdom's CORS handling, which
 * would otherwise decide the outcome before the timeout ever mattered. The
 * `timeout` config under test is adapter-independent (xhr and http both honour
 * it), so what is proven here is the config the browser gets.
 *
 * NEGATIVE CONTROL: drop `timeout` from the axios.create() call in lib/api.js
 * and "aborts a request the server never answers" hangs until jest kills it —
 * which is precisely the production failure it guards, a spinner that never
 * stops. The final assertion (rejection reason is a timeout, not some other
 * error) is what stops a wrong-reason rejection scoring as a pass.
 */
const http = require("http");

// lib/api touches two browser globals at import time (window.__deployLane, and
// localStorage inside the auth request interceptor). Supply them, then load the
// real module — everything else about it is exercised as shipped.
global.window = global.window || {};
global.localStorage = { getItem: () => null, setItem: () => {} };

let server;
let baseUrl;
let client;
let api;
let REQUEST_TIMEOUT_MS;
let SWAP_REQUEST_TIMEOUT_MS;

// Sockets parked open by the hanging route — closed in afterAll so the node
// process can exit even though nothing was ever answered.
const parked = [];

beforeAll(async () => {
  server = http.createServer((req, res) => {
    if (req.url.startsWith("/api/hang")) {
      parked.push(res);
      return; // never respond: the client is the only thing that can end this
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;

  process.env.REACT_APP_BACKEND_URL = baseUrl;
  const mod = require("./api");
  client = mod.default;
  api = mod.api;
  REQUEST_TIMEOUT_MS = mod.REQUEST_TIMEOUT_MS;
  SWAP_REQUEST_TIMEOUT_MS = mod.SWAP_REQUEST_TIMEOUT_MS;
});

afterAll(async () => {
  parked.forEach((res) => { try { res.destroy(); } catch (e) { /* already gone */ } });
  await new Promise((resolve) => server.close(resolve));
});

test("the shared client carries a finite abort, ahead of every server deadline", () => {
  expect(client.defaults.baseURL).toBe(`${baseUrl}/api`);
  expect(REQUEST_TIMEOUT_MS).toBe(30000);
  expect(client.defaults.timeout).toBe(REQUEST_TIMEOUT_MS);
  // The longest ack a request actually waits on is the body drop's 25 s window.
  expect(REQUEST_TIMEOUT_MS).toBeGreaterThan(25000);
});

test("aborts a request the server never answers", async () => {
  const started = Date.now();
  let err = null;
  try {
    await client.get("/hang");
  } catch (e) {
    err = e;
  }
  const elapsed = Date.now() - started;

  expect(err).not.toBeNull();
  // must fail BECAUSE of the timeout — a connection refused / interceptor throw
  // would otherwise pass this test for the wrong reason
  expect(["ECONNABORTED", "ETIMEDOUT"]).toContain(err.code);
  expect(err.response).toBeUndefined();
  expect(elapsed).toBeGreaterThanOrEqual(REQUEST_TIMEOUT_MS - 1500);
  expect(elapsed).toBeLessThan(REQUEST_TIMEOUT_MS + 10000);
}, 60000);

test("/population/respawn overrides the default — it legitimately blocks past 30 s", async () => {
  const seen = [];
  const id = client.interceptors.request.use((config) => { seen.push(config); return config; });
  try {
    await api.populationRespawn("LIVE", "rex");
    await api.slayDino(); // a normal call, for contrast
  } finally {
    client.interceptors.request.eject(id);
  }
  const respawn = seen.find((c) => c.url === "/population/respawn");
  const slay = seen.find((c) => c.url === "/active-dino/slay");

  expect(SWAP_REQUEST_TIMEOUT_MS).toBeGreaterThan(REQUEST_TIMEOUT_MS);
  // the mod's swap ack window is LIN_SWAP_ACK_TIMEOUT_SECS, 30 s by default
  expect(SWAP_REQUEST_TIMEOUT_MS).toBeGreaterThan(30000);
  expect(respawn.timeout).toBe(SWAP_REQUEST_TIMEOUT_MS);
  expect(slay.timeout).toBe(REQUEST_TIMEOUT_MS);
});
