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

## 2026-06 — Fix telarañas de esquina [iteration_17: 100% FE]
- Bug: había 4 telarañas en z-0; las de arriba quedaban ocultas tras la tarjeta hero y las de abajo solo asomaban en huecos = se veían "bugueadas".
- Fix: `CornerWeb` reconstruida como telaraña poligonal limpia (radios + anillos rectos). Ahora solo 2, en esquina superior IZQUIERDA y DERECHA, a z-30 opacity-45 (visibles sobre el hero), pointer-events-none. Responden al Modo Halloween.

## 2026-06 — Cementerio: sin telarañas + arañita colgante + sonido + FX resurrección [iteration_20: 100% FE]
- Telarañas de esquina ELIMINADAS (CornerWeb sigue exportado pero sin uso).
- `HangingSpider.jsx`: arañita que cuelga de un hilo en la esquina superior derecha y sube/baja despacio (hilo animado 120<->195px). Gated por Modo Halloween (fx).
- `CryptAmbience.jsx`: ambiente procedural (viento + drone grave) con Web Audio API (sin asset), reanuda en el primer gesto. Botón `ambience-toggle` en header ("Sonido: ON/OFF"), persiste en localStorage `cem_sound` (default ON), independiente del Modo Halloween.
- `ResurrectionFX.jsx`: overlay full-screen (z-200) al resucitar — el fósil se disuelve, el dino se materializa con 26 partículas verdes + onda expansiva + texto "Resucitado" + especie; se autocierra ~3s. Disparado en doResurrect success.

## 2026-06 — Rediseño del sonido ambiental de cementerio (Halloween) [smoke-tested FE]
- Problema: el usuario reportó que el ambiente sonaba como "viento de ventilador" (ruido constante band-limited), no a Halloween.
- Fix (`CryptAmbience.jsx`): reescrito el generador Web Audio para un ambiente de cripta/camposanto:
  - Drone grave y tenebroso: sines a 55/55.35/82.4/41.2 Hz (batido lento + quinta hueca + suboctava), con LFO 0.05Hz moviendo un lowpass (shimmer).
  - Pad de tensión disonante (2ª menor 233/246.9 Hz) muy tenue.
  - Ráfagas de viento INTERMITENTES (ruido por bandpass con LFO de gust 0.07Hz + barrido 0.04Hz) — ya no es constante.
  - Campana lejana de cementerio: parciales inarmónicos con ataque rápido/decay 5.5s, cada 16-42s aleatorio.
  - Master bajo con fade-in 4s; cleanup limpia timers y osciladores.
- Verificado con smoke test: monta/alterna/limpia sin errores (solo warning estándar de autoplay hasta el primer gesto). La calidad "suena a Halloween" queda a validación auditiva del usuario.

## 2026-06 — Sonido ambiental ELIMINADO del cementerio [smoke-tested FE]
- A petición del usuario se quitó por completo el ambiente sonoro y su botón.
- Cambios en `Cementerio.jsx`: eliminado import de CryptAmbience, estado soundOn/toggleSound, el <CryptAmbience>, el botón `ambience-toggle` y los iconos Volume2/VolumeX.
- Archivo `components/cemetery/CryptAmbience.jsx` borrado.
- Header ahora solo tiene el botón "Modo Halloween". Verificado: compila sin errores y el botón de sonido ya no está.

## 2026-06 — Tienda de Skins Únicas (estilo Fortnite, Stripe) [iteration_21: BE 100%, FE ~95%; rediseño legendario aplicado]
- Objetivo: tienda rotativa estilo Fortnite. El owner/admin crea skins únicas por tiempo limitado/temporadas; se compran con DINERO REAL vía Stripe; son coleccionables y equipables a los dinos. WebSockets para tiempo real.
- Backend `/app/backend/skin_shop.py` (módulo self-contained, `build_router(...)` montado en server.py ~línea 18824, prefix /api; `ensure_indexes()` en startup):
  - Colecciones: shop_skins, owned_shop_skins, shop_payments. Campo user: equipped_shop_skin.
  - Público (auth): GET /api/shop/skins (agrupa destacados/diario/temporada, flags owned/live/equipped), /shop/skins/mine, POST /shop/checkout, GET /payments/status/{sid}, POST /shop/equip, /shop/unequip.
  - Admin: GET/POST/PATCH/DELETE /api/admin/shop/skins (+ stats). Cada skin crea Stripe Product+Price (tax_code digital) al crearse; cambiar precio genera nuevo Price.
  - WS /api/shop/ws: shop_hello, shop_update (CRUD), purchase_success (push al comprador), inventory, equipped.
  - Stripe Flow A (claimable sandbox, US) con managed_payments (SMP, tax_mode "full") + fallback automatic_tax. Grant idempotente (webhook /api/stripe/webhook + polling en /payments/status). Llaves en backend/.env (STRIPE_SECRET_KEY etc.).
- Frontend:
  - Ruta /tienda-skins (`pages/TiendaSkins.jsx`) + enlace navbar en grupo "Tienda" ("Skins").
  - Componentes `components/shop/`: SkinCard, SkinDetailModal, PurchaseCelebration, Countdown, shopRarity.js.
  - Página /payment/success (`pages/PaymentSuccess.jsx`) hace polling y muestra celebración; /payment/cancel -> /tienda-skins.
  - Admin: pestaña "Tienda Skins" (tab key skins_shop) -> `components/admin/AdminSkinShop.jsx` (form con imagen URL, rareza, sección, precio USD, dino, fechas con Calendar+Popover, activa; vista previa en vivo; lista con activar/editar/eliminar; stats).
  - api.js: métodos shop* + shopWsUrl().
- Rediseño "legendario" (a petición del usuario): index.css con keyframes/utilidades (clip-notch, conic frame giratorio, holo foil, sheen, shop-grid-bg, price-tag). Hero "SKIN VAULT" con degradado, encabezados numerados 01/02/03, layout bento (hero grande + banner ancho + grid), banners cinematográficos en Temporada, leyenda de rareza.
- NOTA: aplicar la skin dentro del juego real necesita el servidor live (RCON); en preview equipar solo marca equipped_shop_skin (web). El campo skin_data queda guardado para el enganche in-game futuro.
- Stripe tax mode = "full" (Stripe gestiona todo incl. impuestos, +3.5%/tx). Sandbox sin reclamar; onboarding pendiente para pasar a live.

## 2026-06 — Trade en Vivo P2P (BG3-style) [iteration_22: BE 83%->fix aplicado y verificado E2E; FE 100%]
- Sesión de intercambio en vivo cara a cara dentro de la pestaña Intercambios del Mercado (filtro "Trade en Vivo" -> market-filter-live -> <LiveTradeHub/>). NO reemplaza el sistema asíncrono de dinos.
- Backend `/app/backend/live_trade.py` (build_router montado en server.py ~18829, prefix /api; ensure_indexes en startup):
  - WS /api/trade/ws: presencia (quién está en línea) + push por usuario. Colecciones: trade_sessions, trade_log. Campos user: trade_amber_day, trade_amber_sent, last_item_trade_at.
  - REST: /trade/online, /trade/inventory, /trade/active, /trade/invite, /trade/respond, /trade/offer, /trade/lock, /trade/confirm, /trade/cancel.
  - Reglas: única moneda tradeable = Amberium (vip_coins), máx 1000 ENVIADOS/día por usuario. Tradeable = todo db.inventory EXCEPTO category "Dinosaurs". Cooldown 3h por trade con cualquier item no-amberium; solo-amberium sin cooldown. Editar oferta reinicia ambos locks/confirmaciones. Swap con validación de propiedad, caps y rollback; ejecución idempotente bajo lock por sesión.
  - FIX aplicado (bug crítico iteration_22): el snapshot de oferta ahora guarda item_id -> los items entregados conservan su item_id (0 filas rotas). Verificado E2E por API: A<->B intercambiaron huevos + amber correctamente, cooldown y tope diario aplicados.
- Frontend: `components/trade/LiveTradeHub.jsx` (presencia + popup invitación aceptar/rechazar + espera) y `components/trade/TradeRoom.jsx` (dos inventarios estilo BG3, slots animados con muelle sincronizado, sonido click/hover al seleccionar, lock + confirm con glow pulsante). api.js: métodos trade* + tradeWsUrl(). FIX: dedupe por inv_id en AnimatedSlots (warning de key duplicada).
- Test users: A=demo (POST /api/auth/demo). B=demo_0000000002 (token 7d en /app/memory/test_credentials.md). Reseed: python3 /app/backend/_seed_trade_test.py. Reset sesiones/cooldowns: python3 /app/backend/_reset_trade_test.py.

## 2026-06 — Verificación E2E del Trade en Vivo BG3 4 columnas [iteration_23: FE 100%]
- Se validó todo el flujo con DOS contextos de navegador (A/B) autenticados vía localStorage primal_token:
  - Lobby (market-filter-live) renderiza; invitación->aceptar por WebSocket; ambos entran a trade-room.
  - Layout 4 columnas OK: Tu inventario | Tu oferta | Su oferta | Inventario del peer (solo lectura con items reales).
  - Add/remove de objetos (click en inv-item -> my-offered y de vuelta); cap de Amberium (99999 -> 500); sync en vivo de "Su oferta" en ambas direcciones.
  - ANTI-ESTAFA: A bloquea, B edita -> A ve trade-scam-alert y su lock se resetea de "Desbloquear" a "Bloquear". OK.
  - Swap completo (ambos lock + confirm) -> toast "¡Intercambio completado!", vuelven al lobby, Historial poblado en ambos lados (Diste/Recibiste).
- Notas menores no bloqueantes (backlog): avatar propio "Tú" pasa src=undefined (cosmético); 503 esporádico en consola del 2º contexto durante carga (recurso de fondo, no bloquea).

## 2026-06 — Trade UI: nombres de items visibles + botón "Confirmar" [smoke-tested FE]
- A petición del usuario: en `TradeRoom.jsx` el componente Tile ahora muestra el NOMBRE del objeto (barra inferior con degradado, text-[8px], data-testid `<tile>-name`) + tooltip nativo (title) con nombre · rareza. El contador se movió a la esquina superior derecha como "×N".
- Botón central renombrado de "Barter" (jerga BG3 en inglés, confusa) a "Confirmar".
- Verificado por captura: nombres renderizan en las 4 columnas (Tu inventario / Tu oferta / Su oferta / Inventario del peer).
- Script auxiliar para demo de diseño: `/app/backend/_demo_trade_session.py` (inserta una sesión activa A<->B con ofertas y A bloqueado, para capturar el diseño sin necesitar un 2º jugador).

## 2026-06 — Trade: apilado, sonidos, control Amberium, sala DEMO, invitación [smoke-tested FE]
- APILADO: items idénticos (item_id+cat+rareza+tier) se agrupan en UNA casilla con ×N en las 4 columnas (TradeRoom `groupInv`/`groupOffer`). Add/remove reparte entre filas subyacentes (por inv_id) → swap sigue seguro. Chip ×N en esquina con borde de rareza.
- ICONO AMBERIUM: se reemplazó el icono Gem por la imagen real `/coins/amber.png` (MEDIA.coinVip) en TradeRoom y TradeHistory.
- NOMBRES DE ITEMS: barra inferior con el nombre + tooltip nativo (nombre·rareza) en cada Tile.
- CONTROL AMBERIUM: panel visible en "Tu oferta" con etiqueta "Amberium a enviar", botones +/- (stepAmber ±10) e input central (data-testid amber-control/amber-plus/amber-minus/my-amber-input).
- SONIDO: item click usa `coinSack` (tintineo suave de monedas en saco, sintetizado en lib/sounds.js). Se probaron y descartaron: click mecánico, bloop, thunk Skyrim, coin.mp3 real (muy fuerte), coinClick Mario.
- BOTÓN "Barter" → "Confirmar".
- SALA DEMO: `POST /api/trade/demo` (live_trade.py) crea sesión contra bot "Demo Trader" para la cuenta actual (sin 2º jugador). Asegura items demo si el user no tiene, y da 500 Amberium demo si su saldo es 0. Botón "Ver demo" (Sparkles) en el lobby de LiveTradeHub (api.tradeDemo). Reset sesiones: `/app/backend/_reset_trade_test.py` o borrar trade_sessions.
- INVITACIÓN: popup central `trade-invite-popup` (avatar+nombre, Aceptar/Rechazar) vía WS `trade_invite` + sonido "open".

## 2026-06 — Optimización producción (code-splitting) [build verificado]
- Deployment readiness check: PASS (sin secretos/URLs hardcodeados, env-only, CORS ok, compila).
- `App.js`: rutas convertidas a `React.lazy` + `Suspense` (fallback spinner `page-loading`); Landing y AuthCallback quedan eager.
- Resultado build: main.js **1.04 MB → 342 kB gzip** (~67% menos en carga inicial). 31 chunks; el chunk pesado de 3D (three.js/R3F ~204 kB gzip) solo carga al abrir el editor de skins. Smoke test OK (Landing + Marketplace lazy sin pantalla en blanco).

## 2026-06 — Radio de Proximidad: rediseño pro + controles avanzados [smoke-tested FE]
- Rediseño completo de `ProximityVoice.jsx` a consola de comunicaciones táctica (grid 12 col: consola izq 5 / roster der 7). Sin radar (eliminado a petición). Se mantuvo toda la lógica de `useProximitySim` y `useMicLevel`.
- Controles base: encender/apagar, LCD con telemetría (alcance/en canal/en rango/hablando), VU LED 16 seg, modo PTT/abierto, tecla PTT configurable (Espacio/V/T/C), botón keycap transmitir, silenciar mi mic, volumen general (slider + ±5% + silenciar a todos), diales Nitidez y Alcance, roster in/out range con señal, marcador hablando, volumen y mute por jugador.
- Nuevas features (todas en la sim, persistencia localStorage donde aplica):
  - Presets rápidos: Manada (alcance 60), Explorar (alcance máx), Sigilo (volumen 30%). testids voice-preset-{id}.
  - Buscar/filtrar roster (voice-search) + ordenar Cercanía/Nombre (voice-sort-dist/name).
  - Favoritos (voice-fav-{id}): fija arriba + sube volumen a 100%; persiste en localStorage 'prox_favs'.
  - Bloquear (voice-block-{id}): silencia permanente; persiste en 'prox_blocked'; badge "bloqueado".
  - Historial "Últimos en hablar" (voice-history): últimos 8 que transmitieron en rango.
  - Dispositivos (voice-devices): selects de micrófono/altavoz (enumerateDevices + setSinkId en la prueba).
  - Supresión de ruido toggle (voice-noise-suppression) → re-adquiere el mic.
  - Probar micrófono (voice-test-mic): graba 3s con MediaRecorder y lo reproduce.
  - Indicador VAD (voice-vad): el panel LCD brilla en verde cuando el mic real supera el umbral al transmitir.
- Lógica añadida en `proximitySim.js`: setAllMuted, favorites/blocked persistentes, history; y en `useMicLevel`: devices/listDevices, changeInput/Output, noiseSuppression, testMic, testing.
- Pendiente opcional: cablear estos controles nuevos (tecla PTT configurable, ±volumen, silenciar a todos, dispositivos, NS) a la voz REAL LiveKit en `VoiceContext.jsx` para el servidor de juego.

## 2026-06 — Tienda de Skins → Catálogo/Galería (sin carrito) [smoke-tested FE]
- La Tienda de Skins (`TiendaSkins.jsx`) se reescribió como GALERÍA tipo catálogo: filtros (dino, tipo, orden), buscador, toggle grid/lista. Tarjetas SIN botón de carrito; clic → `SkinDetailModal` (que ya tiene checkout Stripe + equipar).
- Nuevo `components/shop/GalleryCard.jsx` (grid y lista), entrada escalonada (delay por índice), glow de rareza en hover, sonidos hover/click/open.
- `SkinDetailModal`: la foto de preview ahora usa `object-contain` (dino completo, sin recorte) + entrada con zoom y flotación.
- Backend `skin_shop.py`: nuevo `GET /shop/catalog` (lista plana de skins live + owned/equipped + facets dinos/types). Campo nuevo `skin_type` en modelo/_public/admin_create/admin_update.
- Admin (`AdminSkinShop.jsx`): añadido campo "Tipo de skin" (para el filtro del catálogo). El admin gestiona: nombre, descripción, imagen, rareza, sección, dino, tipo, precio (sincroniza Stripe), fechas y activar/ocultar.
- Seed de ejemplo: `backend/_seed_skins_catalog.py` creó 8 skins (Rex/Austroraptor/Spinosaurus/Ceratosaurus) con imágenes generadas (renders oscuros) y PRODUCTOS/PRECIOS Stripe reales. Idempotente por nombre+dino.
- api.js: `shopCatalog`. Verificado: catálogo 200 con 15 skins; grid/list, filtros, buscador, detalle y checkout Stripe operativos; sin overflow en móvil (390) ni desktop (1440).

## 2026-06 — Sistema Global de Bounties (☠️) [iteration_24: BE 100% (9/9) + FE 100%]
Objetivo global aleatorio elegido server-side; el primero que lo mate (kill PVP validado) gana la recompensa. Server-side, seguro, atómico/idempotente, en tiempo real por WebSocket, con anuncio a Discord.
- Backend `/app/backend/bounty.py` (self-contained, patrón configure(...) + build_router(get_current_user, get_admin_user); montado en server.py ~18832 prefix /api; ensure_indexes()+start_loops() en startup):
  - Colecciones: `bounties`, `bounty_state` (singleton), `bounty_dodge_log`. Config tuneable en `settings/_id=bounty` (prime_meat 60000, experience 2500, amberium 500, next_bounty_delay 1200s, minimum_online_time 900s, recent_target_protection 3, disconnect_grace 300s).
  - Elegibilidad (solo backend): online + vivo + SteamID válido (>=17 díg) + >=minimum_online_time conectado (reloj propio `_seen_since`) + no el anterior ni en últimos N + no admin (ADMIN_STEAM_IDS). Selección aleatoria.
  - Validación de muerte: hook `on_kill(killer_sid, victim_sid)` desde `_drain_kill_credits` (solo kills PVP del log del juego). Compleción por update atómico `{id, status:active, target_sid, reward_processed:False} -> {completed, reward_processed:True}` => idempotente (nunca doble cobro; suicidio/natural/admin/desconexión/duplicados no llegan/no pagan).
  - Recompensa (callbacks server.py): PrimeMeat->coins, Amberium->vip_coins, EXP->battle_pass._add_xp; intento in-game best-effort vía game_ipc.write_game_command (no-op en preview). Killer sin cuenta web: bounty se completa igual, reward_delivered=False.
  - Desconexión: si el target sale, status suspended `disconnect_grace` (5min) -> si vuelve, active; si no, cancelado (dodge log) y nuevo bounty. Cooldown next_bounty_delay tras completar.
  - WS público `/api/bounty/ws`: eventos bounty:state/new/active/target_disconnected/target_returned/completed/cancelled/waiting/paused/config (sin polling; timestamps del server, el front cuenta con Date.now()).
  - Admin: POST /bounty/admin/force-new, /pause, /resume, /cancel, /config, /simulate-kill (para probar sin juego real). Público: GET /bounty/current, /config, /history.
  - MODO SIMULACIÓN (preview): `_bounty_online_players` devuelve None cuando no hay RCON/mod -> roster falso estable + `_sim_autokill_loop` completa el bounty a los ~90-150s. Se auto-desactiva cuando el juego real está conectado.
  - Discord: embeds "NUEVO BOUNTY" y "BOUNTY COMPLETADO" (rojo oscuro, timestamp) vía `DISCORD_BOUNTY_WEBHOOK_URL` (server-side, en backend/.env; inactivo hasta configurarlo; nunca en frontend).
- Frontend: página `/bounty` (`pages/Bounty.jsx`, nav bajo Comunidad -> "Bounty Global"), overlay OBS `/bounty/overlay` (fondo transparente, `?bg=1` sólido), widget flotante global `components/bounty/BountyWidget.jsx` (bottom-left, oculto en /bounty). `components/bounty/BountyCard.jsx` (tarjeta WANTED cinemática: intro TARGET ACQUIRED->mira->☠->nombre->ACTIVE, glow rojo pulsante, anillo de mira, count-up de recompensas al completar, sello "ELIMINADO", estados active/suspended/completed/waiting/paused). `hooks/useBountySocket.js` (WS público con reconexión), `lib/bountyMeta.js`. api.js: bountyWsUrl + api.bounty*.
- Sonidos (lib/sounds.js): bountyAlert (swell+campana+shimmer), bountyLock (tick intro), bountyComplete (campanas ascendentes+sub), bountyDisconnect (2 tonos ámbar). REFINADOS a versión limpia/elegante y menor volumen tras feedback del usuario ("no me gustan los sonidos").
- Verificado: testing_agent 100% (config, current, auth guard, force-new, simulate-kill, idempotencia doble-kill, config update+revert, pause/resume, cancel, WS state+ping/pong; FE flujos + widget + overlay). Verificación visual del agente: tarjeta activa (glow), completada (ELIMINADO+count-up+next timer), widget en /dashboard, transición en vivo por WS, sin errores de consola.
- Credenciales: demo login (POST /api/auth/demo) = admin. Reward web solo si el killer SteamID mapea a un usuario web (los killers simulados no -> reward_delivered=False, reward_processed=True, esperado).

## 2026-06 — Rediseño: Sistema de Cacería (bounties puestos por jugadores) [iteration_25: BE 100% 12/12 + FE 100%]
Reemplaza el bounty aleatorio automático anterior. Ahora los bounties los ponen los jugadores.
- CONTRATO: eliges a quién cazar de la lista de online y PAGAS SOLO CON PRIMEMEAT (mín 20.000). La recompensa al cazador = ese PrimeMeat + un mínimo de Amberium que APORTA EL SISTEMA (config reward_amber_bonus, def 100). Varios contratos sobre el mismo objetivo se ACUMULAN. Límite 1 contrato activo por persona. No puedes cazarte a ti mismo (ni a tu grupo, hook _same_group listo para cuando el mod exponga tribu). Reembolso SOLO del PrimeMeat pagado al cancelar/expirar (paid_prime).
- AUTO-BOUNTY: pones precio a tu propia cabeza; ganas self_prime_per_min (5.000) PrimeMeat/min mientras vivas (máx self_max_seconds 900s), acreditado por minuto por el loop. Si te matan: killer recibe self_killer_amber (300) y tú conservas lo acumulado. Gratis con cooldown self_cooldown (600s). 1 activo por persona.
- INVITACIÓN ALEATORIA: cada invite_interval (300s) el server empuja bounty:self_invite por WS a un usuario web online aleatorio, con invite_recent_protection (25) para que sea muy raro repetir; excluye a quienes ya tienen auto-bounty o están en cooldown.
- Validación de muerte (on_kill desde _drain_kill_credits, kills PVP): completa TODOS los contratos del objetivo (atómico e idempotente, reward_processed) sumando la recompensa al cazador; si el que puso el contrato es el killer -> reembolso, sin pago. Resuelve también el auto-bounty (killer gana Amberium). WS bounty:completed + Discord.
- Presencia web: WS /api/bounty/ws?token= autentica al usuario (sub del JWT) para saber quién está online (invitaciones). BountyContext monta UN solo WS compartido para toda la web.
- Endpoints: GET /bounty/config|board|targets(auth)|mine(auth)|history; POST /bounty/contract|contract/cancel|self/start|self/accept-invite; admin: /bounty/admin/simulate-kill{target_sid}|config|pause|resume. Modo simulación de roster en preview (auto-off con juego real).
- Frontend: /app/frontend/src/pages/Bounty.jsx (hub "LA CACERÍA": panel auto-bounty, lista de objetivos animada TargetList.jsx, tablón WANTED rico BountyCard.jsx con rango de amenaza/#1 más buscado/contratistas/temporizador/doble moneda/emisor/ubicación, ContractModal.jsx solo-PrimeMeat, mis bounties, historial, admin). BountyWidget.jsx (destacado global), BountySelfInvite.jsx (invitación global), BountyOverlay.jsx (OBS). context/BountyContext.jsx, hooks/useBountySocket.js, lib/bountyMeta.js (featuredBounty), lib/api.js (api.bounty*).
- Diseño: guiado por design_agent -> /app/design_guidelines.json (Cinematic Carbon & Blood Amber). PrimeMeat en verde #22C55E, Amberium en dorado #F0B429, rojo peligro #E11D2A. Sonidos bountyAlert/bountyComplete/bountyLock/bountyDisconnect (versión limpia).
- Economía confirmada por el usuario: recompensa = PrimeMeat + mínimo de Amberium (bonus del sistema); poner bounty se paga SOLO con PrimeMeat. Verificado por curl (cobro -40k coins, vip intacto; reembolso solo prime) + UI.
- Discord: DISCORD_BOUNTY_WEBHOOK_URL en backend/.env (inactivo hasta configurarlo). Recompensa a billetera web solo si el killer mapea a un usuario web por steam_id.

## Actualización (Jun 2026) — Layout del Tablón de recompensas
- El usuario pidió restaurar las tarjetas WANTED ricas (BountyCard) y colocarlas en 2 columnas (izquierda-derecha, luego siguiente fila). Se descartó la variante de filas compactas (BoardRow).
- Bounty.jsx reorganizado: fila superior [Objetivos en línea | Mis bounties] en 2 col; "Tablón de recompensas" ahora es sección de ancho completo con tarjetas en `grid grid-cols-1 md:grid-cols-2`; Historial de ancho completo (md:grid-cols-2). Verificado por screenshot (desktop + móvil), sin overflow.

## Actualización 2 (Jun 2026) — Tablón a la derecha
- Ajuste solicitado: Objetivos (lista) a la IZQUIERDA y Tablón de recompensas a la DERECHA, a la par (grid lg:grid-cols-2). Tarjetas WANTED (BountyCard) una debajo de la otra en la columna derecha. Mis bounties + Historial abajo en otra fila de 2 columnas. Verificado por screenshot.

## Actualización 3 (Jun 2026) — Historial a la izquierda + reposición del widget
- Layout: columna IZQUIERDA apila Objetivos en línea + Mis bounties + Historial (llena el espacio junto al Tablón alto); columna DERECHA = Tablón de recompensas. Un solo grid lg:grid-cols-2 items-start con div.space-y-6 a la izquierda.
- BountyWidget.jsx reposicionado de `bottom-28 left-5 z-[70]` a `bottom-24 right-5 z-[80]` (entrada desde la derecha x:30) para no chocar con la burbuja de chat (ChatDock bottom-6 left-6). Verificado geométricamente sin solapes con FriendsDock (bottom-6 right-6).

## Actualización 4 (Jun 2026) — Tarjetas WANTED compactas
- Queja: el tablón se extendía mucho hacia abajo (mucho scroll). Se compactó BountyCard.jsx (variante full) manteniendo el diseño: avatar w-16->w-12, texto nombre text-lg->text-base, threat chip movido en línea con dino/Adulto, StatChip px-2.5/py-1.5->px-2/py-1 y gap-2->gap-1.5, se eliminaron el banner "WANTED — Dead or Alive", la línea de telemetría (Radio) y el pie "Bounty ID"; caja de recompensa condensada (rounded-lg px-3 py-2). Import Radio removido.
- Bounty.jsx: board gap-4->gap-3; page py-10->py-8, encabezado mb-8->mb-6, self panel mb-8->mb-6. Verificado por screenshot (tarjetas SURVIVOR_5964 self + BLUECITO/CAZADORNOCTURNO contratos, notablemente más cortas).

## Actualización 5 (Jun 2026) — Layout final anti-scroll
- Petición: tarjetas del Tablón en 2 columnas (1 izq, 2 der, 3 abajo-izq, 4 abajo-der) e Historial a la izquierda de Objetivos en línea.
- Bounty.jsx: fila superior grid lg:grid-cols-2 -> [Historial (izq) | Objetivos en línea + Mis bounties (der)]. Tablón de recompensas ahora ancho completo abajo con tarjetas en grid grid-cols-1 md:grid-cols-2 gap-3. Historial y TargetList con max-h-[420px] overflow-y-auto para no alargar la página. Verificado por screenshot.
