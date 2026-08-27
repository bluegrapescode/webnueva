# La Isla Nublar LATAM — PRD / Working Notes

## Origin
User's own repo ("webnueva" / "la-isla-nublar"). Uploaded as `backend.7z` + `frontend.7z`.
It is a React (CRACO) + FastAPI + MongoDB community website for a The Isle: Evrima
Spanish/LATAM dinosaur game server (dinos, skins, battle pass, marketplace, trades,
mini-games/casino, quests, leaderboard, proximity voice, creator program, admin).

## Environment setup done (infra only — no backend business logic changed)
- Reorganized flat repo into `/app/backend` (37 .py + requirements) and `/app/frontend` (src, public, config).
- Created `/app/backend/.env` (MONGO_URL, DB_NAME=laislanublar, JWT_SECRET, CORS, ALLOW_DEMO_LOGIN=1) and `/app/frontend/.env` (REACT_APP_BACKEND_URL).
- `yarn install --ignore-engines` (camera-controls needs node22; we run node20). Backend + frontend run under supervisor.
- Preview limitations: LiveKit voice, game RCON, on-disk vault DB, real Steam login are NOT available (need the original Windows game box). API runs in demo mode.

## Work done in this session (all FRONTEND unless noted)
1. **Navbar redesign** (`components/layout/Navbar.jsx`): grouped dropdowns — Tienda (Tienda/Mercado/Intercambios), Mini Juegos (Ruleta/Blackjack/Roll/Cajas/Pase de Batalla), Dino en Vivo (Estadísticas/Equipo/Mapa/GEN-Ø), Comunidad (Radio Proximidad/Creators/Patreon). Squared/uppercase "boxy" styling, gold accents. Dropdowns open **on click only** (not hover); close on outside-click/Escape.
2. **Sounds** (`lib/sounds.js`): added `menu` / `menuClose` dropdown sounds.
3. **Live simulation** (whole site): new `context/LiveSimContext.jsx` + `components/live/LiveTicker.jsx` (floating "● EN VIVO" HUD w/ animated player count + activity feed + toasts). Wired in `App.js`; Landing hero count reads live values.
4. **Proximity radio** (`pages/ProximityVoice.jsx` full rewrite + new `lib/proximitySim.js`): removed radar per user; shows who is in range with a working **range dial** (real detection) + real-mic VU meter + speaking indicator + per-player volume/mute.
5. **Inventory stacking** (`components/inventory/InventoryPanel.jsx`): identical items collapse into one card with `xN` badge. Dinos & Skins stay unique.
6. **Dashboard Events/News redesign** (`pages/Dashboard.jsx`): fixed cut images (aspect-video + object-contain), richer cards w/ type identity. Added **DetailModal** popup for news ("Leer más") and clickable event cards, showing full info + photo.
7. **Event photos** (backend): added `image: Optional[str]` to `EventInput` in `server.py` (only backend change). Admin Eventos form (`pages/Admin.jsx`) got an image-URL input.

## Testing
- iteration_1.json: Events/News redesign (images no longer cut) — passed.
- iteration_2.json: News modal + event photo support — **100% backend & frontend**, no issues.

## Backlog / next ideas
- P1: Event category filter + "add to calendar" on the event modal.
- P1: News modal — related links / share.
- P2: Real object-storage image upload for events/news (currently URL paste).
- P2: Surface backend error detail in Admin EventsTab (currently generic toast).
- Deferred (needs live game infra): LiveKit voice, RCON, vault, Steam login.

## 2026-06 — Skin systems: dual previews + Glitch Lab color selector
- Extracted reusable `frontend/src/components/skin3d/SkinPreview3D.jsx` (the proven designer R3F canvas + Capturer).
- Skin Designer uses it (unchanged behavior); Glitch Lab now has its OWN 3D preview (`data-testid=glitch-3d-viewer`) fed clamped-to-gamut colors.
- Glitch Lab gained a per-slot color selector (`data-testid=glitch-colorpicker-<slot>`) that writes sRGB 0-1 values into the R/G/B raw inputs; verified by testing agent.
- NOTE: 3D canvas only renders where `/dino-assets/*` is served (DINO_ASSETS_ROOT points to the Windows game server `C:\LaIslaNublar\web\assets\dinos`). In this Linux preview box assets 404, so BOTH previews (designer + glitch) show the "Vista 3D no disponible" boundary fallback — pre-existing/environmental, not a code bug.

## 2026-06 — PrimeMeat payout bars smooth+synced
- Added `frontend/src/hooks/usePayoutTimer.js` (rAF countdown); wired BalanceHUD + PayoutPanel so bars and counters are smooth and in sync.

## 2026-06 — Skin editors verified working (fix: dev overlay)
- Testing agent (iteration_6) confirmed BOTH editors functional end-to-end: designer + glitch lab controls, color pickers, presets, apply, tab/species switching — no crashes.
- FIX: missing /dino-assets textures in the Linux preview box were popping a CRA full-screen runtime-error overlay (React18 dev forwards boundary errors to window.reportError). Disabled the dev-server RUNTIME error overlay in craco.config.js (client.overlay.runtimeErrors=false; compile-error overlay kept). Also added useRequiredTexture in FleetDinoModel so the loader promise resolves (no unhandled rejection); Skin3DBoundary still shows "Vista 3D no disponible".
- Reminder: 3D canvas only renders where /dino-assets is served (owner's Windows game server). In preview both viewers show the fallback placeholder by design; controls + color-apply logic work regardless.


## 2026-06 — Sistema de Cementerio & Resurrección (FÓSIL)  [iteration_8: 100% BE 16/16 + FE flows]
Epic completo: registro de dinos muertos + moneda FÓSIL (comprada con Amberiums = `vip_coins`) + fósil gratis mensual + cooldown de resurrección de 24h + regla de ahogamiento en combate (excepción Deinosuchus) + WebSocket en tiempo real.

### Backend (todo en `server.py`, sección "CEMENTERIO & RESURRECCIÓN")
- Colecciones nuevas: `cemetery_records`, `fossil_transactions`, `resurrected_dinos`. Campos nuevos en `users`: `fossils`, `last_free_fossil_month` (YYYY-MM), `last_resurrection_at`. Config de precio en `settings` `_id="cemetery"` (`fossil_price`, default 1500).
- Rutas (api_router `/api`): `GET /cemetery/config`, `GET /cemetery/feed` (filtros: search/species/status/rarity/cause/sort/limit/skip + stats), `GET /cemetery/record/{id}`, `GET /cemetery/hall-of-fame`, `GET /cemetery/fossils` (auth), `POST /cemetery/fossils/buy` (auth), `POST /cemetery/fossils/claim-free` (auth, idempotente por mes calendario), `POST /cemetery/resurrect` (auth, solo dueño), `GET /cemetery/transactions`, `GET /cemetery/my-resurrections`. Admin: `POST/PUT/DELETE /cemetery/admin/record`, `POST /cemetery/admin/fossils`, `PUT /cemetery/admin/config`, `GET /cemetery/admin/transactions`.
- WebSocket `@app.websocket("/api/cemetery/ws")` (hub `cemetery_hub`): difunde `cemetery_death`/`cemetery_resurrection`/`cemetery_update`/`cemetery_delete`/`cemetery_config` y empuja `fossil_balance` al dueño.
- Elegibilidad `_cem_eligibility`: Ahogamiento + en combate = NO_REVIVIBLE, salvo especie que empiece por "deino" (Deinosuchus, tolerante a variantes del mod).
- Resurrección: cobra 1 fósil (atómico), fija cooldown 24h, marca record RESUCITADO, intenta escribir a la bóveda SQLite real (falla con gracia en preview → vault_written=false) y SIEMPRE guarda el dino restaurado en `resurrected_dinos` (inventario web) con todos los stats/mutaciones/prime/skin.
- Semilla demo `_cem_seed_demo` (12 registros, dueño = demo). `public_user` ahora incluye `fossils`.

### Frontend
- Página `pages/Cementerio.jsx` (ruta `/cementerio`, en nav bajo "Dino en Vivo"): hero con stats + **fósil levitando con pulso de fondo** (framer-motion), filtros (buscador/especie/orden/tabs de estado), grid de tarjetas, `ProfileModal` (perfil completo), `ConfirmResurrect`, `BuyModal`, `TxModal`, `HallOfFame`. Real-time vía `hooks/useCemeterySocket.js`. Meta puro en `lib/cemeteryMeta.js`.
- `Admin.jsx`: pestaña "Cementerio" (`CementerioTab`): cambiar precio, editar saldos de fósiles, alta manual de muerte (con aviso NO REVIVIBLE), lista de registros con cambio de estado/eliminar, log de transacciones.
- **Navbar**: se quitó el carrito (era código muerto — nada lo poblaba salvo el propio botón) y en su lugar se muestra un pill de **Fósil** (`/fossil.png`, junto a las monedas en `BalanceHUD`, enlaza a `/cementerio`). Asset `public/fossil.png` (transparente, ~225KB).

### Notas
- Amberiums = `vip_coins`. 1 Fósil = 1500 Amberiums (configurable). Solo el dueño resucita. Fósil gratis: 1 por mes calendario.
- La escritura a la bóveda del juego real solo funciona con el servidor Windows online; en preview el dino restaurado vive en `resurrected_dinos` (correcto).
- Backlog sugerido por QA: endpoint admin para resetear cooldown (solo QA); modularizar `server.py`.
