import axios from "axios";

// Deploys ship automatically from this repository (see docs/AUTODEPLOY.md).
// The marker below identifies which deploy pipeline produced the running bundle.
window.__deployLane = "github";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
// Asset routes (GLB/webp) live OUTSIDE the /api namespace — same convention as the
// donor skin sites' /dino-assets/<species>/<file> static route.
export const ASSET_BASE = BACKEND_URL;

// Hard client-side abort on every request. Nothing on this API legitimately runs
// longer: the body-drop ack window is 25 s, growth-pause 7 s, every outbound
// httpx call is <= 15 s, and park/redeem hand back a job_id immediately and are
// polled. /chat/poll is a plain 3 s-interval read, not a long poll. So in normal
// operation this never fires — it exists so a wedged socket surfaces as an error
// the caller already knows how to show, instead of a spinner that never stops.
export const REQUEST_TIMEOUT_MS = 30000;
// The one endpoint that legitimately outlives the default: /population/respawn
// holds the request open until the mod's terminal swap ack
// (LIN_SWAP_ACK_TIMEOUT_SECS, 30 s by default and tunable UP), so a 30 s client
// abort would race it and report a failure for a swap that actually landed.
export const SWAP_REQUEST_TIMEOUT_MS = 60000;

const client = axios.create({ baseURL: API, timeout: REQUEST_TIMEOUT_MS });

// Navigate the TOP-LEVEL window for external OAuth (Steam/Patreon/Discord block being framed).
// Inside an iframe (e.g. the preview), a normal location change shows a blank page because the
// provider sends X-Frame-Options: DENY. Break out to the top window, or fall back to a new tab.
export function externalRedirect(url) {
  try {
    if (window.self !== window.top) {
      window.top.location.href = url;
      return;
    }
  } catch (e) {
    // Cross-origin parent: cannot navigate it -> open in a new tab instead.
    window.open(url, "_blank", "noopener");
    return;
  }
  window.location.href = url;
}

export function startSteamLogin() {
  externalRedirect(`${API}/auth/steam/login`);
}

// Creator Program — same-origin WebSocket URL for /api/creator/ws. Reuses the
// real auth token key (primal_token, same one the request interceptor below
// attaches as a Bearer header) and the same BACKEND_URL fallback the REST
// client uses, so it resolves correctly whether REACT_APP_BACKEND_URL is a
// real cross-origin host (dev) or empty (prod, same-origin behind the proxy).
export function creatorWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/creator/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Tienda de Skins — same-origin WebSocket URL for /api/shop/ws (live drops,
// countdowns, sold-out and purchase_success pushes to the buyer).
export function shopWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/shop/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Trade en Vivo — WebSocket URL for /api/trade/ws (presence + live session sync).
export function tradeWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/trade/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Sistema de Cacería — WebSocket para /api/bounty/ws. Manda el token (si existe)
// para registrar la presencia del usuario web (invitaciones de auto-bounty).
export function bountyWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/bounty/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Sistema de Crafteo — WebSocket para /api/crafting/ws (materiales, jobs, claim).
export function craftingWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/crafting/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Sistema de Clanes — WebSocket para /api/clans/ws (chat + estado en vivo).
export function clansWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/clans/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// Turf Wars — WebSocket para /api/turf/ws (estado de zonas en vivo, capturas).
export function turfWsUrl() {
  const base = (BACKEND_URL || window.location.origin).replace(/^http/, "ws");
  const token = localStorage.getItem("primal_token");
  return `${base}/api/turf/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

// A "subscriber" (sub) = active Patreon patron, Discord Patreon tier role
// (Apex / Elder / Adult / Sub Adult / Juvie), Discord VIP role, or an admin.
export function isSubscriber(user) {
  if (!user) return false;
  if (user.role === "admin") return true;
  const p = user.patreon || {};
  const d = user.discord || {};
  return p.patron_status === "active_patron" || p.linked === true || d.vip_role === true || !!d.tier_role || d.streamer === true;
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("primal_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Balance auto-refresh: any successful mutating call may have changed the user's
// balances (spends, awards, refunds) — AuthContext registers a debounced refresh
// here so the HUD updates without a manual page reload. The 20s passive-tick POST
// from BalanceHUD rides this too, doubling as a background re-sync for balance
// changes that happen outside the site (in-game, Discord bot).
let mutationListener = null;
export function registerMutationListener(fn) { mutationListener = fn; }
const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);
// High-frequency endpoints that never move a balance.
const MUTATION_IGNORE = [/\/chat\/send$/, /\/voice\/token$/];
client.interceptors.response.use((res) => {
  const method = (res.config?.method || "").toLowerCase();
  const url = res.config?.url || "";
  if (mutationListener && MUTATING_METHODS.has(method) && !MUTATION_IGNORE.some((re) => re.test(url))) {
    mutationListener();
  }
  return res;
});

export const api = {
  root: () => client.get("/"),
  // auth
  steamLoginUrl: () => `${API}/auth/steam/login`,
  demoLogin: () => client.post("/auth/demo"),
  me: () => client.get("/auth/me"),
  claimDaily: () => client.post("/auth/daily"),
  passiveTick: () => client.post("/economy/passive-tick"),
  payoutStatus: () => client.get("/payout/status"),
  giftStatus: () => client.get("/gift/status"),
  giftClaim: () => client.post("/gift/claim"),
  // cosmetics (chat decorations)
  cosmeticsCatalog: () => client.get("/cosmetics/catalog"),
  cosmeticsEquip: (category, id) => client.post("/cosmetics/equip", { category, id }),
  eggsInfo: () => client.get("/cosmetics/eggs"),
  chatEmotes: () => client.get("/cosmetics/emotes"),
  eggOpen: (tier) => client.post("/cosmetics/egg/open", { tier }),
  eggPool: (tier) => client.get(`/cosmetics/egg/${tier}/pool`),
  // dinosaurs
  dinosaurs: (params) => client.get("/dinosaurs", { params }),
  dinosaur: (slug) => client.get(`/dinosaurs/${slug}`),
  // store
  storeCategories: () => client.get("/store/categories"),
  storeItems: (params) => client.get("/store/items", { params }),
  purchase: (item_id) => client.post("/store/purchase", { item_id }),
  purchaseDino: (body) => client.post("/store/purchase-dino", body),
  checkout: (items) => client.post("/store/checkout", { items }),
  // leaderboards
  leaderboards: () => client.get("/leaderboards"),
  leaderboardsMe: () => client.get("/leaderboards/me"),
  // GEN-Ø virus contamination (Dino en Vivo tab). The facilities endpoint was
  // removed 2026-08-21 on the owner's order — the zones are found in-world.
  gen0Contamination: () => client.get("/gen0/contamination"),
  // economy
  economySummary: () => client.get("/economy/summary"),
  transactions: (params) => client.get("/economy/transactions", { params }),
  economyChart: () => client.get("/economy/chart"),
  // inventory & profile
  inventory: () => client.get("/inventory"),
  inventoryReorder: (ids) => client.post("/inventory/reorder", { ids }),
  releaseDino: (inv_id) => client.delete(`/inventory/${inv_id}`),
  editDinoMutations: (inv_id, mutations) => client.post(`/inventory/dino/${inv_id}/mutations`, { mutations }),
  editDinoMutationGroups: (inv_id, groups) => client.post(`/inventory/dino/${inv_id}/mutation-groups`, { groups }),
  entombDino: (inv_id) => client.post(`/inventory/dino/${inv_id}/entomb`),
  renameDino: (inv_id, name) => client.post(`/inventory/dino/${inv_id}/rename`, { name }),
  purchaseHistory: () => client.get("/profile/purchases"),
  redemptions: () => client.get("/profile/redemptions"),
  dinoRecords: () => client.get("/profile/dino-records"),

  // friends & teleport
  friends: () => client.get("/friends"),
  friendsSearch: (q) => client.get("/friends/search", { params: { q } }),
  steamFriends: () => client.get("/friends/steam"),
  steamAddByLink: (query) => client.post("/friends/steam-add", { query }),
  friendsRequest: (user_id) => client.post("/friends/request", { user_id }),
  friendsRespond: (user_id, accept) => client.post("/friends/respond", { user_id, accept }),
  friendsRemove: (friend_id) => client.delete(`/friends/${friend_id}`),
  friendsTeleportRequest: (user_id) => client.post("/friends/teleport-request", { user_id }),
  friendsTeleportRespond: (request_id, accept) => client.post("/friends/teleport-respond", { request_id, accept }),
  // codes
  redeemCode: (code) => client.post("/codes/redeem", { code }),
  // cases
  cases: () => client.get("/cases"),
  openCase: (id) => client.post(`/cases/${id}/open`),
  openCaseBulk: (id, count) => client.post(`/cases/${id}/open-bulk`, { count }),
  openCrate: (inv_id) => client.post("/inventory/open-crate", { inv_id }),
  unboxings: () => client.get("/profile/unboxings"),
  // reward skins (glitch skins won from crates)
  rewardSkins: () => client.get("/me/rewards/skins"),
  applyRewardSkin: (glitch_id, pattern) => client.post("/me/rewards/skins/apply",
    pattern == null ? { glitch_id } : { glitch_id, pattern }),
  // provably fair
  fairnessCurrent: () => client.get("/fairness/current"),
  fairnessSetClientSeed: (client_seed) => client.post("/fairness/client-seed", { client_seed }),
  fairnessRotate: (client_seed) => client.post("/fairness/rotate", client_seed ? { client_seed } : {}),
  fairnessVerify: (body) => client.post("/fairness/verify", body),
  // active dino + mutations
  mutations: (dinoSlug) => client.get("/mutations", dinoSlug ? { params: { dino_slug: dinoSlug } } : undefined),
  skins: () => client.get("/skins"),
  activeDino: () => client.get("/active-dino"),
  deployDino: (inv_id) => client.post("/active-dino/deploy", { inv_id }),
  parkDino: () => client.post("/active-dino/park"),
  slayDino: () => client.post("/active-dino/slay"),
  dropBody: () => client.post("/active-dino/drop-body"),
  toggleGrowth: () => client.post("/active-dino/toggle-growth"),
  setPrime: () => client.post("/active-dino/set-prime"),
  equipSkin: (inv_id) => client.post("/active-dino/skin", { inv_id }),
  applyCustomSkin: (name, color, config, image) => client.post("/active-dino/custom-skin", { name, color, config, image }),
  unequipSkin: () => client.post("/active-dino/skin/remove"),
  // 3D skin studio
  skins3dList: () => client.get("/skins3d"),
  skins3dSave: (body) => client.post("/skins3d", body),
  skins3dUpdate: (id, body) => client.put(`/skins3d/${id}`, body),
  skins3dDelete: (id) => client.delete(`/skins3d/${id}`),
  // casino
  bjCurrent: () => client.get("/casino/blackjack"),
  bjDeal: (bet) => client.post("/casino/blackjack/deal", { bet }),
  bjHit: () => client.post("/casino/blackjack/hit"),
  bjStand: () => client.post("/casino/blackjack/stand"),
  bjDouble: () => client.post("/casino/blackjack/double"),
  minesCurrent: () => client.get("/casino/mines"),
  minesStart: (bet, mines) => client.post("/casino/mines/start", { bet, mines }),
  minesReveal: (index) => client.post("/casino/mines/reveal", { index }),
  minesCashout: () => client.post("/casino/mines/cashout"),
  diceRoll: (bet, target, direction) => client.post("/casino/dice/roll", { bet, target, direction }),
  rollState: () => client.get("/casino/roll/state"),
  rollBet: (color, amount) => client.post("/casino/roll/bet", { color, amount }),
  casinoHistory: () => client.get("/casino/history"),
  casinoStats: () => client.get("/casino/stats"),
  casinoLeaderboard: () => client.get("/casino/leaderboard"),
  // Nublar Spin (daily wheel). `cmd_id` = one id per ATTEMPT (the marketplace
  // client_request_id rule): a retry of the same attempt answers with the
  // recorded spin instead of spinning twice.
  wheelConfig: () => client.get("/wheel/config"),
  wheelStatus: () => client.get("/wheel/status"),
  wheelSpin: (cmd_id) => client.post("/wheel/spin", { cmd_id }),
  wheelHistory: () => client.get("/wheel/history"),
  wheelUseVial: (inv_id) => client.post("/wheel/vial/use", { inv_id }),
  wheelAdminConfig: () => client.get("/wheel/admin/config"),
  wheelAdminSave: (body) => client.post("/wheel/admin/config", body),
  wheelAdminReset: () => client.post("/wheel/admin/reset-defaults"),
  wheelAdminGrantSpins: (user_id, amount, reason) => client.post("/wheel/admin/grant-spins", { user_id, amount, reason }),
  wheelAdminRecent: () => client.get("/wheel/admin/recent"),
  // chat
  chatPoll: (channel, after) => client.get("/chat/poll", { params: { channel, ...(after ? { after } : {}) } }),
  chatSend: (text, channel) => client.post("/chat/send", { text, channel }),
  chatDelete: (id) => client.delete(`/chat/messages/${id}`),
  staffRanks: () => client.get("/staff-ranks"),
  adminSetStaffRank: (user_id, rank) => client.post("/admin/staff-rank", { user_id, rank }),
  // marketplace
  //
  // Every money call carries a `client_request_id`: one id per ATTEMPT, so a
  // replay of the same attempt returns the stored outcome instead of charging
  // twice, and a genuinely new attempt is still allowed. Buy and bid also carry
  // `expected_price` — the button sends the number it SHOWED, so a price that
  // moved under a stale page earns an exact refusal rather than a silent
  // overcharge. Callers build both through @/lib/marketPricing.
  market: () => client.get("/market"),
  marketCreate: (body) => client.post("/market/list", body),
  marketBuy: (id, body) => client.post(`/market/${id}/buy`, body || {}),
  marketBid: (id, amount, extra) => client.post(`/market/${id}/bid`, { amount, ...(extra || {}) }),
  marketHistory: () => client.get("/market/history"),
  // The dino's IDENTITY, not a mutation count: the server counts the mutations
  // itself off the row, because a client-sent count is a client-sent price with
  // extra steps. Pass {dino_id} for a vault animal, {inv_id} for an inventory
  // one; slug/species are the species-only fallback the route still answers.
  marketSuggestedPrice: (params) => client.get("/market/suggested-price", {
    params: Object.fromEntries(
      Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ),
  }),
  marketMine: () => client.get("/market/mine"),
  marketWithdraw: (id, body) => client.post(`/market/${id}/withdraw`, body || {}),
  mySales: () => client.get("/profile/sales"),
  // ── Intercambios (direct player-to-player trades) ──
  //
  // NO COINS ON EITHER SIDE. There is no coins field on any of these bodies and
  // no place to put one: a coin leg turns a trade into an untaxed sale and
  // re-opens the fee the market charges. The server's TradeOfferInput has no
  // such field either, so a caller that invented one would simply be ignored.
  //
  // tradeConfig is the ONLY source of the cooldown, the offer TTL, the symmetry
  // band, the per-side cap and the open-offer cap. Nothing that consumes these
  // may pin its own copy — see @/lib/tradeRules.
  //
  // The three writes carry a `client_request_id` for exactly the reason the
  // market's do: one id per ATTEMPT, so a replay of a dropped attempt returns
  // the stored outcome instead of escrowing a second time, while a genuinely new
  // attempt is still allowed. Build them with marketPricing's newRequestId /
  // attemptSettled — the trade lane shares the market's attempt ledger.
  //
  // THE BOARD is how an offer gets addressed now. `tradeOffer` carries a
  // `showcase_id` and the server resolves BOTH the other player and the animal
  // being asked for off that card — no route on this backend hands out another
  // player's row number, and this is why one never has to.
  tradeBoard: () => client.get("/trade/board"),
  tradeBoardCreate: (body) => client.post("/trade/board", body),
  tradeBoardClose: (id, body) => client.post(`/trade/board/${id}/close`, body || {}),
  tradeConfig: () => client.get("/trade/config"),
  tradeLookup: (q) => client.get("/trade/lookup", { params: { q } }),
  tradeMine: () => client.get("/trade/mine"),
  tradeOffer: (body) => client.post("/trade/offer", body),
  tradeAccept: (id, body) => client.post(`/trade/${id}/accept`, body || {}),
  tradeDecline: (id, body) => client.post(`/trade/${id}/decline`, body || {}),
  tradeCancel: (id, body) => client.post(`/trade/${id}/cancel`, body || {}),
  // integrations
  integrationsStatus: () => client.get("/integrations/status"),
  integrationsStart: () => client.post("/integrations/start"),
  patreonSync: () => client.post("/patreon/sync"),
  patreonStatus: () => client.get("/patreon/status"),
  patreonUnlink: () => client.post("/patreon/unlink"),
  discordUnlink: () => client.post("/discord/unlink"),
  // streamer pack (free, application-only; benefits driven by the Discord Streamer role)
  streamerStatus: () => client.get("/streamer/status"),
  streamerApply: (body) => client.post("/streamer/apply", body),
  // admin
  adminStats: () => client.get("/admin/stats"),
  adminUsers: (params) => client.get("/admin/users", { params }),
  adminGrant: (body) => client.post("/admin/grant", body),
  adminSetRole: (body) => client.post("/admin/role", body),
  adminCodes: () => client.get("/admin/codes"),
  adminCreateCode: (body) => client.post("/admin/codes", body),
  adminUpdateCode: (id, body) => client.patch(`/admin/codes/${id}`, body),
  adminDeleteCode: (id) => client.delete(`/admin/codes/${id}`),
  adminLogs: () => client.get("/admin/logs"),
  adminCreateNews: (body) => client.post("/admin/news", body),
  adminDeleteNews: (id) => client.delete(`/admin/news/${id}`),
  adminCreateEvent: (body) => client.post("/admin/events", body),
  adminDeleteEvent: (id) => client.delete(`/admin/events/${id}`),
  adminCreateStore: (body) => client.post("/admin/store", body),
  adminUpdateStore: (id, body) => client.patch(`/admin/store/${id}`, body),
  adminDeleteStore: (id) => client.delete(`/admin/store/${id}`),
  adminCreateDino: (body) => client.post("/admin/dinosaurs", body),
  adminDeleteDino: (slug) => client.delete(`/admin/dinosaurs/${slug}`),
  adminGetSettings: () => client.get("/admin/settings"),
  adminUpdateSettings: (body) => client.patch("/admin/settings", body),
  adminGetRollConfig: () => client.get("/admin/roll-config"),
  adminUpdateRollConfig: (body) => client.patch("/admin/roll-config", body),
  adminRconStatus: () => client.get("/admin/rcon/status"),
  adminRconPlayers: () => client.get("/admin/rcon/players"),
  adminRconAnnounce: (message) => client.post("/admin/rcon/announce", { message }),
  adminRconSave: () => client.post("/admin/rcon/save"),
  adminGetGift: () => client.get("/admin/gift-schedule"),
  adminSaveGift: (schedule) => client.put("/admin/gift-schedule", { schedule }),
  // ---- Battle Pass ----
  bpStatus: () => client.get("/battle-pass/status"),
  bpClaim: (body) => client.post("/battle-pass/claim", body),
  bpClaimAll: () => client.post("/battle-pass/claim-all"),
  bpCheckout: (tier) => client.post("/battle-pass/checkout", { tier }),
  bpPayment: (sid) => client.get(`/battle-pass/payment/${sid}`),
  bpTokens: () => client.get("/battle-pass/tokens"),
  bpTokenRedeem: (body) => client.post("/battle-pass/token/redeem", body),
  bpVaultTargets: () => client.get("/battle-pass/vault-targets"),
  bpAdminOverview: () => client.get("/battle-pass/admin/overview"),
  bpAdminGift: (body) => client.post("/battle-pass/admin/gift", body),
  bpAdminGrantXp: (body) => client.post("/battle-pass/admin/grant-xp", body),
  bpAdminSettle: (body) => client.post("/battle-pass/admin/settle", body),
  bpAdminSeasonName: (body) => client.post("/battle-pass/admin/season-name", body),
  // quests + multiplier events
  listQuests: () => client.get("/quests"),
  claimQuest: (id) => client.post(`/quests/${id}/claim`),
  adminListMultiplierEvents: () => client.get("/admin/multiplier-events"),
  adminCreateMultiplierEvent: (body) => client.post("/admin/multiplier-events", body),
  adminEndMultiplierEvent: (id) => client.patch(`/admin/multiplier-events/${id}/end`),
  adminDeleteMultiplierEvent: (id) => client.delete(`/admin/multiplier-events/${id}`),
  adminRecoverDino: (body) => client.post("/admin/recover-dino", body),
  adminRecoverable: (q) => client.get("/admin/recoverable", { params: { q } }),
  // account standing / strikes
  profileStanding: () => client.get("/profile/standing"),
  adminModeration: () => client.get("/admin/moderation"),
  adminUserStanding: (user_id) => client.get(`/admin/users/${user_id}/standing`),
  adminAddStrike: (user_id, body) => client.post(`/admin/users/${user_id}/strike`, body),
  adminRemoveStrike: (strike_id) => client.delete(`/admin/strikes/${strike_id}`),
  adminUnban: (user_id) => client.post(`/admin/users/${user_id}/unban`),
  // Baneos de la página web (owners only): the drop-down, the arm/confirm
  // press, the lift. See lib/webBans.js for the shapes and the copy.
  adminBansOverview: () => client.get("/admin/bans/overview"),
  adminBansSuggest: (q) => client.get("/admin/bans/suggest", { params: { q } }),
  adminBansPlace: (body) => client.post("/admin/bans/place", body),
  adminBansLift: (steam_id) => client.post("/admin/bans/lift", { steam_id }),
  adminWipeInventory: (user_id) => client.post(`/admin/users/${user_id}/inventory-wipe`),
  // server / content
  serverStatus: () => client.get("/server/status"),
  population: (server) => client.get("/population", { params: { server } }),
  populationUnlock: (server, slug) => client.post("/population/unlock", { server, slug }),
  // blocks server-side until the mod acks the swap — see SWAP_REQUEST_TIMEOUT_MS
  populationRespawn: (server, slug) => client.post("/population/respawn", { server, slug }, { timeout: SWAP_REQUEST_TIMEOUT_MS }),
  populationLeave: () => client.post("/population/leave"),
  news: () => client.get("/news"),
  events: () => client.get("/events"),

  // ════════════════════════════════════════════════════════════════
  // Fleet contract — La Isla Nublar web wave. Backend built in parallel:
  // every consumer of these must degrade gracefully (loading/offline/error
  // states), never assume a response.
  // ════════════════════════════════════════════════════════════════
  meState: () => client.get("/me/state"),
  aiPositions: () => client.get("/ai_positions"),
  meVault: () => client.get("/me/vault"),
  meVaultPark: () => client.post("/me/vault/park"),
  // backend's _DinoIdIn model requires the field name "dino_id" (was sending "id",
  // which 422'd every redeem attempt before it ever reached vault.start_redeem).
  meVaultRedeem: (id) => client.post("/me/vault/redeem", { dino_id: id }),
  meVaultDelete: (id) => client.delete(`/me/vault/${id}`),
  meVaultRename: (id, name) => client.post(`/me/vault/${id}/rename`, { name }),
  meVaultJob: (job_id) => client.get(`/me/vault/job/${job_id}`),
  meVaultMutations: (id) => client.get(`/me/vault/${id}/mutations`),
  meVaultMutationSet: (id, slot, mutation) => client.post(`/me/vault/${id}/mutations`, { slot, mutation }),
  meSlay: () => client.post("/me/slay"),
  meBodyDrop: () => client.post("/me/bodydrop"),
  meGrowthPause: (pause) => client.post("/me/growth-pause", { pause }),
  species: () => client.get("/species"),
  skinMapGet: () => client.get("/skin-map"),
  skinMapPut: (body) => client.put("/skin-map", body),
  materialScalars: () => client.get("/material-scalars"),
  presetsList: () => client.get("/presets"),
  presetsSave: (body) => client.post("/presets", body),
  presetsDelete: (id) => client.delete(`/presets/${id}`),
  applySkinLive: (body) => client.post("/apply", body),
  // Skin contract v2 (studio). The state probe is tiny and ALWAYS 200 when the route
  // is mounted; skinContract() is the immutable ~761 KB capability table, so it is
  // fetched only after the probe says v2 is on, and cached for the session.
  skinContractState: () => client.get("/studio/skin-contract-state"),
  skinContract: () => client.get("/studio/skin-contract"),
  applySkinV2: (body) => client.post("/studio/apply-v2", body),
  applyPresetExact: (presetId) => client.post("/apply-preset", { preset_id: presetId }),
  glitchAccess: () => client.get("/glitch-access"),
  glitchApply: (raw) => client.post("/glitch/apply", { raw }),
  skinSnapshot: () => client.get("/snapshot"),
  patreonAccess: (refresh) => client.get("/patreon-access", { params: { refresh: refresh ? 1 : 0 } }),
  adminPopState: () => client.get("/admin/pop/state"),
  adminPopApply: (body) => client.post("/admin/pop/apply", body),
  adminPopAudit: () => client.get("/admin/pop/audit"),
  voiceToken: () => client.post("/voice/token", {}),

  // ---- Creator Program ----
  cpApplyCode:      (code) => client.post("/creator/apply-code", { code }),
  cpMyReferral:     () => client.get("/creator/my-referral"),
  cpDashboard:      () => client.get("/creator/dashboard"),
  cpReferrals:      () => client.get("/creator/referrals"),
  cpNotifications:  () => client.get("/creator/notifications"),
  cpMarkRead:       () => client.post("/creator/notifications/mark-read"),
  cpLeaderboard:    (scope = "all") => client.get(`/creator/leaderboard?scope=${scope}`),
  cpPublic:         (code) => client.get(`/creator/public/${code}`),
  cpAdminCreate:    (payload) => client.post("/creator/admin/create", payload),
  cpAdminUpdate:    (payload) => client.post("/creator/admin/update", payload),
  cpAdminList:      () => client.get("/creator/admin/list"),
  cpAdminSettings:  () => client.get("/creator/admin/settings"),
  cpAdminSetSettings: (payload) => client.post("/creator/admin/settings", payload),
  cpTimeseries:     (days = 30) => client.get(`/creator/timeseries?days=${days}`),
  cpProgramStats:   () => client.get("/creator/program-stats"),
  cpTrackVisit:     (code) => client.post("/creator/track-visit", { code }),
  cpHallOfFame:     (limit = 12) => client.get(`/creator/hall-of-fame?limit=${limit}`),
  cpAdminAlerts:    () => client.get("/creator/admin/alerts"),
  cpAdminAlertAction: (alert_id, action) => client.post("/creator/admin/alerts/action", { alert_id, action }),
  // The payouts CSV route requires an admin Bearer token (get_admin_user), which a
  // plain <a href> download link can never carry — routed through the authenticated
  // client as a blob instead, same technique Economy.jsx's client-built CSV uses to
  // trigger the save (Blob + object URL + a synthetic <a>.click()).
  cpAdminPayoutsCsv: () => client.get("/creator/admin/payouts.csv", { responseType: "blob" }),
  // ── Cementerio & Fósiles ──
  cemConfig:        () => client.get("/cemetery/config"),
  cemFeed:          (params) => client.get("/cemetery/feed", { params }),
  cemRecord:        (id) => client.get(`/cemetery/record/${id}`),
  cemHallOfFame:    () => client.get("/cemetery/hall-of-fame"),
  cemFossils:       () => client.get("/cemetery/fossils"),
  cemBuyFossils:    (quantity) => client.post("/cemetery/fossils/buy", { quantity }),
  cemClaimFree:     () => client.post("/cemetery/fossils/claim-free"),
  cemTransactions:  () => client.get("/cemetery/transactions"),
  cemMyResurrections: () => client.get("/cemetery/my-resurrections"),
  cemResurrect:     (record_id) => client.post("/cemetery/resurrect", { record_id }),
  cemAdminAddRecord: (body) => client.post("/cemetery/admin/record", body),
  cemAdminUpdateRecord: (id, body) => client.put(`/cemetery/admin/record/${id}`, body),
  cemAdminDeleteRecord: (id) => client.delete(`/cemetery/admin/record/${id}`),
  cemAdminFossils:  (body) => client.post("/cemetery/admin/fossils", body),
  cemAdminConfig:   (fossil_price) => client.put("/cemetery/admin/config", { fossil_price }),
  cemAdminTransactions: () => client.get("/cemetery/admin/transactions"),
  cemAdminRecords:  (params) => client.get("/cemetery/admin/records", { params }),

  // ── Tienda de Skins Únicas (Stripe) ──
  shopSkins:        () => client.get("/shop/skins"),
  shopCatalog:      () => client.get("/shop/catalog"),
  shopMine:         () => client.get("/shop/skins/mine"),
  shopCheckout:     (skin_id) => client.post("/shop/checkout", { skin_id, origin_url: window.location.origin }),
  shopPaymentStatus: (session_id) => client.get(`/payments/status/${session_id}`),
  shopEquip:        (skin_id) => client.post("/shop/equip", { skin_id }),
  shopUnequip:      () => client.post("/shop/unequip"),
  shopAdminList:    () => client.get("/admin/shop/skins"),
  shopAdminCreate:  (body) => client.post("/admin/shop/skins", body),
  shopAdminUpdate:  (id, body) => client.patch(`/admin/shop/skins/${id}`, body),
  shopAdminDelete:  (id) => client.delete(`/admin/shop/skins/${id}`),

  // ── Trade en Vivo P2P ──
  tradeOnline:      () => client.get("/trade/online"),
  tradeInventory:   () => client.get("/trade/inventory"),
  tradeActive:      () => client.get("/trade/active"),
  tradeInvite:      (to_user_id) => client.post("/trade/invite", { to_user_id }),
  tradeRespond:     (session_id, accept) => client.post("/trade/respond", { session_id, accept }),
  tradeSetOffer:    (session_id, items, amber) => client.post("/trade/offer", { session_id, items, amber }),
  tradeLock:        (session_id, locked) => client.post("/trade/lock", { session_id, locked }),
  tradeConfirm:     (session_id) => client.post("/trade/confirm", { session_id }),
  tradeCancel:      (session_id) => client.post("/trade/cancel", { session_id }),
  tradeHistory:     () => client.get("/trade/history"),
  tradePeerInventory: (session_id) => client.get(`/trade/peer/${session_id}`),
  // Sistema de Cacería / Bounties puestos por jugadores
  bountyWsUrl,
  bountyConfig:     () => client.get("/bounty/config"),
  bountyBoard:      () => client.get("/bounty/board"),
  bountyTargets:    () => client.get("/bounty/targets"),
  bountyMine:       () => client.get("/bounty/mine"),
  bountyHistory:    (limit = 20) => client.get(`/bounty/history?limit=${limit}`),
  bountyLeaderboard: (period = "all") => client.get(`/bounty/leaderboard?period=${period}`),
  bountyPlaceContract: (target_sid, prime, amber = 0) => client.post("/bounty/contract", { target_sid, prime, amber }),
  bountyCancelContract: (bounty_id) => client.post("/bounty/contract/cancel", { bounty_id }),
  bountySelfStart:  () => client.post("/bounty/self/start"),
  bountySelfAcceptInvite: () => client.post("/bounty/self/accept-invite"),
  bountySetConfig:  (cfg) => client.post("/bounty/admin/config", cfg),
  bountySimulateKill: (target_sid) => client.post("/bounty/admin/simulate-kill", { target_sid }),
  bountyPause:      () => client.post("/bounty/admin/pause"),
  bountyResume:     () => client.post("/bounty/admin/resume"),

  // ── Sistema de Crafteo de Skins (🔨) ──
  craftingWsUrl,
  craftingState:    () => client.get("/crafting/state"),
  craftingCraft:    (recipe_id, idempotency_key) => client.post("/crafting/craft", { recipe_id, idempotency_key }),
  craftingClaim:    (job_id, idempotency_key) => client.post("/crafting/claim", { job_id, idempotency_key }),
  craftingCancel:   (job_id) => client.post("/crafting/cancel", { job_id }),
  craftAdminOverview: () => client.get("/crafting/admin/overview"),
  craftAdminSaveMaterial: (body) => client.post("/crafting/admin/materials", body),
  craftAdminDeleteMaterial: (id) => client.delete(`/crafting/admin/materials/${id}`),
  craftAdminSaveRecipe: (body) => client.post("/crafting/admin/recipes", body),
  craftAdminDeleteRecipe: (id) => client.delete(`/crafting/admin/recipes/${id}`),
  craftAdminGetSettings: () => client.get("/crafting/admin/settings"),
  craftAdminSaveSettings: (body) => client.put("/crafting/admin/settings", body),
  craftAdminGrant:  (body) => client.post("/crafting/admin/grant", body),
  craftAdminLogs:   (kind, limit = 100) => client.get(`/crafting/admin/logs${kind ? `?kind=${kind}&limit=${limit}` : `?limit=${limit}`}`),

  // ── Sistema de Clanes (🛡️) ──
  clansWsUrl,
  clanMe:           () => client.get("/clans/me"),
  clanConfig:       () => client.get("/clans/config"),
  clanDirectory:    () => client.get("/clans/directory"),
  clanFound:        (body) => client.post("/clans/found", body),
  clanEdit:         (body) => client.post("/clans/edit", body),
  clanSaveRank:     (body) => client.post("/clans/ranks", body),
  clanDeleteRank:   (id) => client.delete(`/clans/ranks/${id}`),
  clanAssign:       (user_id, rank_id) => client.post("/clans/assign", { user_id, rank_id }),
  clanInvite:       (body) => client.post("/clans/invite", body),
  clanPlayerSearch: (q) => client.get(`/clans/players/search?q=${encodeURIComponent(q || "")}`),
  clanCancelInvite: (user_id) => client.post("/clans/invite/cancel", { user_id }),
  clanRequestJoin:  (clan_id) => client.post("/clans/request", { clan_id }),
  clanCancelRequest:(clan_id) => client.post("/clans/request/cancel", { clan_id }),
  clanRequestAccept:(user_id) => client.post("/clans/request/accept", { user_id }),
  clanRequestDecline:(user_id) => client.post("/clans/request/decline", { user_id }),
  clanInviteAccept: (clan_id) => client.post("/clans/invite/accept", { clan_id }),
  clanInviteDecline:(clan_id) => client.post("/clans/invite/decline", { clan_id }),
  clanKick:         (user_id) => client.post("/clans/kick", { user_id }),
  clanTransfer:     (user_id) => client.post("/clans/transfer", { user_id }),
  clanLeave:        () => client.post("/clans/leave"),
  clanDisband:      () => client.post("/clans/disband"),
  clanChatHistory:  (limit = 50, channel = "clan") => client.get(`/clans/chat?limit=${limit}&channel=${channel}`),
  clanChatSend:     (text, channel = "clan") => client.post("/clans/chat", { text, channel }),
  clanAnnouncement: (text) => client.post("/clans/announcement", { text }),
  clanReact:        (message_id, emoji) => client.post("/clans/react", { message_id, emoji }),
  clanInsights:     () => client.get("/clans/insights"),
  clanTurfHistory:  () => client.get("/clans/turf-history"),
  clanAdminGetSettings: () => client.get("/clans/admin/settings"),
  clanAdminSaveSettings: (body) => client.put("/clans/admin/settings", body),
  clanAdminList:    () => client.get("/clans/admin/list"),
  clanAdminDelete:  (clan_id) => client.post("/clans/admin/delete", { clan_id }),

  // ── Turf Wars (⚔️) ──
  turfWsUrl,
  turfState:        () => client.get("/turf/state"),
  turfConfig:       () => client.get("/turf/config"),
  turfRally:        (zone_id) => client.post("/turf/rally", { zone_id }),
  turfAdminGetSettings: () => client.get("/turf/admin/settings"),
  turfAdminSaveSettings: (body) => client.put("/turf/admin/settings", body),
  turfAdminCapture: (zone_id, clan_id) => client.post("/turf/admin/capture", { zone_id, clan_id }),
  turfAdminReset:   () => client.post("/turf/admin/reset"),
};

// GLB/webp dino asset files live OUTSIDE /api (same convention as the donor skin sites).
// sv= is a fleet-wide cache epoch for these files. Browsers hold /dino-assets/*
// responses long-term, so replacing a species file on the box under the SAME name
// is invisible to anyone who already loaded the old bytes — bump the epoch when
// species assets are swapped in place and every browser fetches fresh copies.
export const DINO_ASSET_EPOCH = 2;
export const dinoAssetUrl = (species, file) =>
  `${ASSET_BASE}/dino-assets/${encodeURIComponent(species)}/${file}${file.includes("?") ? "&" : "?"}sv=${DINO_ASSET_EPOCH}`;

export default client;
