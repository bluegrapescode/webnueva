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

## 2026-06 — Cementerio: ajustes (precio 8000, redención 2h, privacidad, enredaderas) [iteration_9: 100%]
- Precio del Fósil = **8000 Amberiums** (`CEM_DEFAULT_FOSSIL_PRICE=8000`; se actualizó el doc `settings._id=cemetery` a 8000).
- **Cooldown de redención de 2h** anti revenge-kill: al resucitar se guarda `redeem_cooldown_until` en el record y `redeemable_at` en `resurrected_dinos`; `config` expone `redeem_cooldown_hours=2`. La UI lo muestra en el perfil ("No se puede redimir por …").
- **Cementerio PRIVADO**: `feed`, `record/{id}` y `hall-of-fame` requieren auth y se filtran al dueño (`_cem_owner_clause`). WS ahora empuja muertes/resurrecciones/updates SOLO al dueño (`_cem_resolve_owner_uid` + `push_to_user`); `cemetery_config` sigue en broadcast. Nuevo `GET /cemetery/admin/records` (admin ve TODO) y el panel admin lo usa. La página muestra `SignInPrompt` si no hay sesión.
- **Enredaderas** SVG (`components/cemetery/Vines.jsx`: `VineStrip` sobre el grid + `VineCorner` en las tarjetas; keyframe `vineSway` en index.css).
- Navbar: carrito (código muerto) reemplazado por pill de **Fósil** (`/fossil.png`, `data-testid=balance-fossil`) junto a las monedas.

## 2026-06 — Fix enredadera "estilo panteón" [iteration_10: 100% FE]
- Bug: la enredadera estaba en una tira recortada (`h-16 overflow-hidden`) y se veía cortada.
- Fix: `VineStrip` ahora es un DOSEL a lo ancho de toda la pantalla (w-screen, absolute top-0 z-20, pointer-events-none, alturas variadas ~280px) + `VineSide` en los bordes izq/der (desktop). Se eliminó la tira recortada. Contenido en `relative z-10`. Tarjetas siguen clicables. Verificado por testing_agent.

## 2026-06 — Fix enredaderas amontonadas a la izquierda [iteration_11: 100% FE]
- Causa raíz: la animación CSS `vineSway` (`transform: rotate`) SOBRESCRIBÍA el atributo SVG `transform="translate(x 0)"` de cada liana (en SVG el transform de CSS pisa el atributo), colapsando todas las lianas a x=0 (izquierda) al iniciar la animación.
- Fix: la oscilación ahora usa SMIL `<animateTransform type="rotate" additive="sum">` dentro del `<g transform="translate(x 0)">`, así la rotación se COMPONE con el translate en vez de reemplazarlo. Se quitó la animación CSS de las lianas. Verificado: 34 lianas repartidas en todo el ancho (izq/centro/der), sin colapso tras la animación.

## 2026-06 — Halloween: enredaderas siniestras + enjambre de aranas global [iter 12-14: 100% FE]
- Enredaderas rediseñadas siniestras: tallos secos retorcidos (dos tonos), espinas, hojas marchitas (verde apagado + café muerto), bayas tóxicas/sangre con leve brillo, telarañas + araña diminuta en esquinas de tarjetas, y neblina tóxica detrás del dosel. Mantiene fix SMIL (sin amontonarse).
- `SpiderRunner.jsx`: araña que cruza TODA la pantalla en dirección aleatoria (8 rutas: horizontal/vertical/diagonales), nunca repite la dirección anterior; primera aparición a los 8s y luego cada 6 min. `position:fixed z-[60] pointer-events-none`, patas animadas (spiderScuttleA/B en index.css), rota para "mirar" hacia donde corre. Montada en `Cementerio.jsx`.
- Araña ahora es un ENJAMBRE GLOBAL (montado en App.js, aparece en toda la web): oleada de 5–8 arañas cada 2 min (primera a los 6s), cada una en dirección distinta (rutas barajadas), frenéticas (dur 1.6–3.6s), tamaños variados, `pointer-events-none`, z-[60], sin scrollbar. `SpiderRunner.jsx` = SpiderSwarm.

## 2026-06 — Arañas: solo en cementerio + menos cantidad [iteration_15: 100% FE]
- Se quitó el montaje global (App.js). `SpiderRunner` vuelve a estar SOLO en `Cementerio.jsx` (exclusivo de esa sección).
- Cantidad reducida: MIN_SPIDERS=2, MAX_SPIDERS=3 (antes 5-8). Sigue cada 2 min, primera oleada a los ~6s. 0 arañas en home/tienda; se desmonta al salir del cementerio.

## 2026-06 — Halloween cementerio: telarañas + bichos + interruptor [iteration_16: 100% FE]
- Telarañas fijas en las 4 esquinas del cementerio (`CornerWeb` en Vines.jsx, SVG radiales + anillos, pointer-events-none).
- Murciélagos/polillas ocasionales (`FlyingCritters.jsx`): 1 cada 40-95s (primero ~14s), vuelo ONDULADO (distinto a la araña), alas aleteando (keyframes batFlap/mothFlap en index.css). data-testid=cemetery-critter, z-[59], solo cementerio.
- Interruptor "Modo Halloween" (`halloween-toggle`) en el header del cementerio: enciende/apaga TODO (arañas, dosel + enredaderas laterales + de tarjetas, telarañas, neblina, bichos). Persiste en localStorage `cem_halloween` (default ON). Tarjetas siguen clicables en ambos estados.
