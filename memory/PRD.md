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

## Actualización 6 (Jun 2026) — Layout 3 columnas (Tablón central)
- Petición: Tablón de recompensas es la atracción principal -> debe ir arriba y al centro; Historial a la izquierda, Objetivos a la derecha.
- Bounty.jsx: grid lg:grid-cols-5 items-start -> Historial (lg:col-span-1) | Tablón (lg:col-span-3, tarjetas grid grid-cols-1 md:grid-cols-2) | Objetivos+Mis bounties (lg:col-span-1). Historial y TargetList con max-h-[560px] overflow-y-auto. Filas de Historial/Mis bounties compactadas para las columnas estrechas. Verificado por screenshot.

## Actualización 7 (Jun 2026) — Diseño sólido 3 columnas + fixes de overflow
- grid lg:grid-cols-12: Historial (col-span-3) | Tablón + Mis bounties (col-span-6) | Objetivos (col-span-3). min-w-0 en cada columna y overflow-x-hidden en contenedores con scroll para evitar scroll horizontal.
- Mis bounties movido al centro, DEBAJO del Tablón (grid sm:grid-cols-2 cuando hay varios).
- TargetList.jsx compactado: se eliminó el bloque de recompensa de ancho fijo (min-w-[74px]); la recompensa ahora va en línea bajo el nombre; botón "Cazar"/"Subir" (antes "Subir bote"); tags con shrink-0. Esto elimina el desborde lateral en columnas estrechas.

## Actualización 8 (Jun 2026) — Fix botón "Cazar" oculto
- Bug: en la columna estrecha de Objetivos (col-span-3 con overflow-x-hidden) el botón "Cazar" (al final de una fila horizontal, shrink-0) se recortaba/ocultaba.
- Fix TargetList.jsx: la fila ahora es flex-col -> arriba avatar+info (nombre/especie/recompensa en línea), y abajo el botón "Cazar"/"Subir bote" a w-full (ancho completo). Garantiza que el botón siempre sea visible sin importar el ancho de la columna.
- NO verificado visualmente logueado en preview (auth demo no propaga al frontend en headless; login real es Steam). Verificado por compilación (webpack sin errores) y por lógica del patrón w-full.

## Actualización 9 (Jun 2026) — Auditoría anti-exploit + hardening + packaging
- Auditoría del sistema de bounties: testing_agent 16/16 backend PASS (reporte /app/test_reports/iteration_26.json). Verificado: cobro atómico ($gte, sin negativo ni doble gasto), saldo insuficiente 400, mínimo 400, no auto-target 400, amber inyectado por sistema (ignora amber del request), límite 3 contratos, objetivo offline 400, cancelar reembolsa, simulate-kill atómico e IDEMPOTENTE (sin doble pago), auto-bounty único, WS sync (bounty:state/contract_new/board), history, admin protegido.
- Hardening en bounty.py: (1) _bid() ahora usa uuid.uuid4().hex[:10] (evita colisiones del índice único que romperían el insert tras cobrar); (2) place_contract reembolsa y aborta 500 si el insert falla tras el cobro; (3) fallback de admin simulate-kill usa "SIMKILL-"+uuid (antes str(int(sid)+1) crasheaba con sids no numéricos).
- Sonidos: bountyAlert/bountyLock/bountyComplete/bountyDisconnect en /app/frontend/src/lib/sounds.js, cableados vía SoundContext en Bounty.jsx, BountyContext.jsx y BountyWidget.jsx. Animaciones: framer-motion en tarjetas/listas/widget.
- Packaging/descarga: NO existe botón ZIP; la vía oficial es "Save" -> "Save to GitHub" (requiere plan Standard+) y luego git clone; o botón "Code" (VS Code) para copiar manualmente. .env y datos de DB no se exportan.

## Actualización 10 (Jun 2026) — Prontuario / "porqué" del bounty en Objetivos
- Backend bounty.py: nuevas helpers _diet_of() (herbívoro/carnívoro por slug/especie) y _target_profile() -> {diet, kills, herbOnHerb, reasons:[{code,label,tone}], threat}. Motivos: "Asesino en serie · N cazas" (kills>=8, danger), "Agresivo · N cazas" (>=4, warn), "N cazas recientes" (>=1, muted), "Traidor: atacó a un herbívoro" (herbívoro que mató herbívoro, danger), "Depredador ápice" (carnívoro kills>=10, danger), "Sin cargos — caza libre" si nada. En preview los datos son DETERMINISTAS por sid (random.Random("bounty:kills:"+sid)); en prod usa p['kills']/p['herb_on_herb'] si el roster los provee. GET /bounty/targets ahora incluye 'profile' y ordena por (bounty, kills, nombre). Verificado por curl (10 sim targets con perfiles).
- Frontend TargetList.jsx: cada fila muestra dieta (Leaf/Drumstick), y chips de motivos con tono (danger rojo / warn ámbar / muted gris) bajo la especie. data-testid bounty-reasons-{sid}. Compila OK. NO verificado visualmente logueado (auth demo no propaga al frontend headless; login real Steam).

## Actualización 11 (Jun 2026) — Objetivos más grande/legible + demo de motivos
- Bounty.jsx: contenedor max-w-6xl -> max-w-7xl; grid re-balanceado Historial (col-span-3) | Tablón (col-span-6->5) | Objetivos (col-span-3->4, ~400px) para que la info de motivos no se recorte. Objetivos scroll max-h-[620px].
- TargetList.jsx: filas agrandadas (avatar w-11->w-12, glifo text-2xl->3xl, nombre text-sm->text-[15px], especie text-[11px]->text-xs, dieta/contador ->text-[11px], chips motivos text-[9px]->text-[10px], botón py-2->py-2.5 text-[13px] con hover:brightness-110). Eliminado bloque de recompensa duplicado.
- bounty.py _sim_roster: ahora asigna kills (0-14) y herb_on_herb=True a herbívoros en preview para demostrar TODOS los motivos (incluye "Traidor: atacó a un herbívoro" en YonduSkywalker/Triceratops). Producción sigue usando telemetría real. Corregida gramática "1 caza reciente".
- Verificado por curl (espectro completo de motivos). Render visual bloqueado en headless (WS/flakiness + auth Steam), pero app compila (webpack 0 errores) y endpoints 200.

## Actualización 12 (Jun 2026) — Interfaz de Bounty a pantalla grande
- Petición: usar la mayor parte de la pantalla, interfaz más grande (sin chocar con chat/amigos), que quepa más animación.
- Bounty.jsx: contenedor max-w-7xl -> max-w-[1760px]; padding px-4 sm:px-8 lg:px-12 py-10 pb-28 (pb-28 libra las burbujas fijas de chat/amigos); gap-6 -> gap-8; secciones p-4 sm:p-5 -> p-5 sm:p-6; h2 text-sm -> text-base; header más grande (Skull w-8/9, h1 hasta text-6xl, p text-base); scroll interno max-h-[76vh]; board grid md:grid-cols-2 -> xl:grid-cols-2 gap-4 (tarjetas más grandes lado a lado en pantallas anchas).
- BountyCard.jsx (variante full) escalada: avatar w-12->w-16 glifo text-2xl->4xl, nombre text-base->text-xl, StatChip px-2/py-1->px-2.5/py-1.5 valor text-[13px]->sm etiqueta text-[8px]->9px grid gap-1.5->2.5, iconos w-4->w-5, barra supervivencia h-1.5->h-2, caja recompensa rounded-lg px-3 py-2->rounded-xl px-4 py-3 valor text-base->text-xl.
- Verificado: webpack 0 errores, /bounty 200, Babel OK. Render visual no capturable en headless (flakiness del gate de carga de la ruta; app corre, ticker en vivo actualiza).

## Actualización 13 (Jun 2026) — Pulso de recompensa suave (fix lag)
- Problema: la animación de "pulso" (glow) de las tarjetas se veía lagueada.
- Causa: se animaba box-shadow en bucle (animate={boxShadow:[...]}), que fuerza repaint por frame y no usa GPU.
- Fix BountyCard.jsx: se envolvió la tarjeta en un div relativo con una capa <motion.div> de glow detrás (absolute inset-0, boxShadow fijo del acento) que anima SOLO opacity [0.4,0.92,0.4] (3.2s, easeInOut) -> compositada por GPU, suave. La tarjeta ahora tiene box-shadow estático y willChange:transform; se quitó la animación de boxShadow. Verificado por Babel/compilación (render/suavidad no capturable en screenshot estático).

## Actualización 14 (Jun 2026) — Glow entrecortado: causa raíz y fix definitivo
- Causa raíz: la página se re-renderiza cada 1s (setInterval tickNow para contadores). El glow usaba framer animate={{opacity:[...]}} con array literal nuevo en cada render -> framer REINICIABA la animación cada segundo => se veía entrecortado. Además el prop `layout` en cada tarjeta forzaba recálculo de layout por render (thrash).
- Fix: (1) glow migrado a animación CSS pura .bounty-glow (@keyframes bountyGlowPulse opacity 0.4->0.92->0.4, 3.2s) en index.css -> corre en compositor, inmune a re-renders de React. (2) Removido `layout` del motion.div de cada tarjeta en Bounty.jsx. CountUp ya depende solo de [value] (no reinicia por render).
- Verificado: Babel/webpack OK. Suavidad no capturable en screenshot estático ni render headless (gate de carga de ruta).

## Actualización 15 (Jun 2026) — 5 features: Salón, Alertas, Feed, #1 destacado, Motivo en Tablón
- (a) Salón de Cazadores: GET /bounty/leaderboard?period=week|month|all agrega bounties completed/dead por killer (kills, primeMeat, amberium) + badge por tier (_hunter_badge). Componente HunterHall en Bounty.jsx (toggle de periodo, top 20, medallas). Verificado curl (6 hunters).
- (b) Alertas globales: BountyContext ahora usa useAuth (mySid), dispara toasts en cualquier página: te pusieron precio, cobraste recompensa, te mataron, y anuncio global de cacerías >=100k. Broadcast bounty:completed ahora incluye killerSid/targetId.
- (c) Feed en vivo: BountyContext mantiene buffer feed (últimos 14 eventos contract_new/completed); componente LiveFeed (ticker marquee) bajo el header.
- (d) #1 Más Buscado destacado: BountyCard isTop (rank 0 no-self) usa .bounty-glow-top (glow dorado más rápido/intenso) + .bounty-border-top (borde animado) + borde dorado. Verificado por screenshot.
- (e) Motivo en el Tablón: _build_board añade topReason/threat/diet por objetivo usando el MISMO roster que /targets (roster_map) para consistencia. BountyCard muestra b.topReason. Verificado: NubladoMX = "Asesino en serie · 12 cazas" idéntico en lista y tablón.
- Estado pruebas: backend por curl OK; d y e verificados visualmente; a por datos+montaje; b y c son WS/logueado (no reproducibles en headless con login Steam).

## Actualización 16 (Jun 2026) — Rediseño Tienda de Skins (vitrina de lujo oscuro+dorado)
- Petición: la tienda se veía muy simple; el usuario eligió estilo lujo/coleccionable (oscuro, elegante, dorado), mantener filtros/orden y checkout Stripe, animaciones de rareza más intensas y un Hero destacado con la skin legendaria del momento.
- Blueprint generado por design_agent en /app/design_guidelines.json (v2.0, arquetipo LUXURY & COLLECTIBLE SHOWCASE). NOTA: el token tailwind `gold` es en realidad verde (#7CA842, marca del sitio); para el oro de lujo se usan clases `amber-*` (#F59E0B).
- Cambios frontend:
  - TiendaSkins.jsx: nuevo componente FeaturedHero (selecciona la skin destacada: prioriza section=destacados, luego rareza RARITY_ORDER, luego precio). Encabezado con overline dorado + título degradado (.text-gold-clip). Barra de filtros ahora sticky glass con bordes amber. Se mantienen intactos: WS, filtros (filter-dino/type/sort), búsqueda (skin-search), toggle grid/lista, modal y celebración.
  - GalleryCard.jsx: tarjeta coleccionable obsidiana + marco dorado; holograma continuo (.lux-holo) y marco cónico giratorio (.lux-conic) en hover para legendary/mythic; aura pulsante (.lux-mythic-aura) siempre en mythic; placa inferior con divisor dorado y pill de precio dorado.
  - SkinDetailModal.jsx: marco con ring dorado y botón "Comprar con Stripe" dorado (checkout/equip sin cambios).
  - index.css: keyframes GPU-friendly nuevos: goldGlowPulse, holoSweep, mythicAuraPulse, luxFloat, luxSpin, luxSparkle + utilidades .lux-holo/.lux-gold-glow/.lux-mythic-aura/.lux-float/.lux-conic/.text-gold-clip/.lux-spark.
- Verificación: testing_agent (iteration_27.json) 100% frontend — 15 tarjetas, hero (hero-skin-banner/hero-buy-btn), catalog-count, filtros/búsqueda/toggle y apertura+cierre de modal, en desktop 1920 y móvil 390 sin overflow horizontal. Sin cambios de backend. (El preview headless pierde la sesión Steam al recargar, por eso las capturas manuales logueadas son intermitentes.)

## Actualización 17 (Jun 2026) — Tienda de Skins: NUEVA ESTRUCTURA (Sala de exhibición master-detail)
- Feedback del usuario: la v16 mantenía la MISMA estructura (encabezado + filtros + grid), solo cambiaban colores/efectos -> no era un rediseño real. Se cambió la ESTRUCTURA por completo.
- Nuevo layout en TiendaSkins.jsx = "Sala de exhibición" (master-detail):
  - IZQUIERDA (lg:col-span-7, sticky): VITRINA grande (componente DisplayCase) con la skin SELECCIONADA en grande — render en pedestal con spotlight dorado, sparkles, holograma (legendary/mythic), aura mítica, nombre en degradado dorado, chips de atributos (rareza/especie/tipo/disponibilidad), precio grande y botón Comprar-Stripe / Equipar AHÍ MISMO (sin modal). Cambio de skin animado con AnimatePresence.
  - DERECHA (lg:col-span-5): barra de filtros/búsqueda sticky + LISTA navegable (componente SkinRow) AGRUPADA POR RAREZA (Mítico->Común, encabezado por grupo con punto de color). Fila activa resaltada en oro. Al tocar una fila -> se actualiza la vitrina en vivo (setSelectedId).
  - Móvil: la vitrina se apila arriba y la lista debajo; al seleccionar hace scroll-to-top.
- Se ELIMINÓ el toggle grid/lista y el uso de SkinDetailModal en esta página (la compra/equipar vive en la vitrina). GalleryCard.jsx queda sin uso en esta ruta (no borrado). Se mantienen: WS (shop_update/purchase_success), api.shopCatalog/shopCheckout/shopEquip, PurchaseCelebration, selección por defecto = skin destacada.
- Verificación: testing_agent iteration_28.json 100% frontend — hero-skin-banner con display-skin-name inicial "Obsidian", 15 filas skin-card-{id} agrupadas por rareza, catalog-count "15 skins en la vitrina", interacción master-detail (clic en 'Trike Dorado' actualiza la vitrina sin modal + fila resaltada), filtros/orden/búsqueda OK, desktop 1920 y móvil 390 sin overflow horizontal. Sin cambios de backend.
- NOTA preview: el navegador del screenshot_tool no sostiene la sesión demo (localStorage particionado en el iframe) y queda en el gate de login; la verificación válida es la del testing_agent (que autentica con POST /api/auth/demo -> localStorage primal_token).

## Actualización 18 (Jun 2026) — Tienda Skins: lista compacta 2 columnas + preview object-contain
- Feedback: la lista de rarezas era muy larga hacia abajo, y el preview recortaba la imagen (importante para imágenes subidas por el usuario).
- Fix TiendaSkins.jsx: (1) los tiles de cada grupo de rareza ahora se renderizan en 'grid grid-cols-2 gap-2' (SkinRow rediseñado como tile compacto: thumb 44px object-contain, nombre/especie/precio apilados) -> lista ~50% más corta. (2) La imagen de la vitrina (DisplayCase) pasó de object-cover a 'object-contain p-3 drop-shadow-2xl' -> se ve el contenido COMPLETO sin recorte. Thumbnails de la lista también object-contain.
- Verificado: testing_agent iteration_29.json 100% — 2 columnas (285px desktop / 175px móvil), object-contain aplicado, 15 tiles, sin overflow horizontal en 1920 y 390.

## Actualización 19 (Jun 2026) — SISTEMA DE CRAFTEO DE SKINS (Fase 1) ✅
Server-authoritative, WS-driven (sin polling), atómico + idempotency + recuperación tras reinicios.

### Backend (`/app/backend/crafting.py`, wired en server.py ~L18950 + startup crafting.start_loops)
- Colecciones: crafting_materials, player_materials, crafting_recipes (materiales embebidos), crafting_jobs, crafting_settings(_id="crafting"), crafting_logs. Índices en player_id, recipe_id, status, finish_at, material_id + idempotency_key único sparse.
- Endpoints (/api/crafting): GET /state · POST /craft · POST /claim · POST /cancel · WS /ws · admin: GET /admin/overview, POST/DELETE /admin/materials, POST/DELETE /admin/recipes, GET/PUT /admin/settings, POST /admin/grant, GET /admin/logs.
- CRAFT: transacción compensada (descuento $gte por material + rollback), idempotency_key (doble-click = 1 job/1 descuento), límite de crafteos activos por rol (default/vip/apex desde settings).
- Timers server-side: started_at/finish_at persistidos; sweeper cada 15s + barrido al boot -> CRAFTING vencido pasa a COMPLETED (sobrevive reinicios/crash). CLAIM valida propiedad+COMPLETED, marca CLAIMED atómico (sin doble claim), entrega la skin a LA BÓVEDA (db.inventory categoría Skins, item_id "craft:<recipe>", uses=max(20,receta)).
- Eventos WS: crafting:started/completed/claimed/cancelled, materials:updated, material:collected, recipe:updated, material:updated, settings:updated. El servidor NO envía el temporizador cada segundo (solo started_at/finish_at; el cliente cuenta local).
- Seed: 4 materiales (Huesos/Metal/Cuero/Polímero, iconos NUBLAR RESOURCES) + 4 recetas (T-Rex Volcánico, Spino Abismal, Trike Dorado, Stego Invernal).

### Frontend
- Ruta /crafteo (`pages/SkinCrafting.jsx` + `context/CraftingContext.jsx` WS + `components/crafting/parts.jsx`). Layout 3 columnas estilo okok: Cola de Crafteo (izq) · grid + tabs ALL/CARNÍVOROS/HERBÍVOROS/EN BÓVEDA/FABRICABLES (centro) · Detalles + CRAFT (der). Barra de inventario de materiales arriba. Estados: CRAFTABLE/MISSING/CRAFTING/READY/OWNED. Countdown local + barra de progreso. Notificaciones (sonner). Nav: Tienda > Crafteo de Skins.
- Admin: `components/admin/AdminCrafting.jsx` (tab "Crafteo" en Admin.jsx) con subtabs Materiales/Recetas/Ajustes Globales/Otorgar/Historial (CRUD completo, grant server-authoritative para pruebas, propagación por WS).

### Verificación: testing_agent iteration_30.json — 100% frontend E2E (craft con descuento atómico 390->350, cola, claim con speed x3600, toast, OWNED, admin CRUD, WS live sin reload, responsive 1920 y 390 sin overflow). Backend core curl-verificado (idempotencia, claim-not-ready 400, doble-claim 409, sweeper, entrega uses=20). Fix aplicado post-review: materials:updated ahora re-evalúa checks/CRAFT al instante. crafting_speed_mult reseteado a 1.0.

### PENDIENTE (Fase 2/3): gathering real (collect(nodeId) desde el mod in-game, nodos, respawn, cooldown, posiciones aleatorias, gathering_logs), Discord de crafteos raros (webhook en Settings), historiales admin ampliados, iconos definitivos que enviará el usuario.

## Actualización 20 (Jun 2026) — Crafteo: sonidos + animaciones sincronizadas
- Sonidos sintetizados nuevos en lib/sounds.js: craftStart (forja/yunque), craftMaterial (recolección), craftReady (listo), craftClaim (fanfarria). Disparados DESDE los eventos WS del servidor en CraftingContext (material:collected/crafting:started/completed/claimed) => 100% sincronizados con el estado real; play("error") en fallos. Sin superficie nueva de exploit (todo sigue server-authoritative).
- Animaciones CSS GPU-friendly (index.css): forge-progress (shimmer en barras activas), forge-ember (partículas en cards en CRAFTING), craft-ready-pulse (glow en jobs READY + botón reclamar), craftPopIn. Aplicadas en components/crafting/parts.jsx.
- Verificado: testing_agent iteration_31.json 100% frontend — clases de animación presentes en los estados correctos, craft/claim sin regresión, sin errores de consola, sin overflow 1920/390. crafting_speed_mult reseteado a 1.

## Actualización 21 (Jun 2026) — Crafteo REDISEÑADO: Estación de Forja Inmersiva
- Feedback: "no me gusta tanto, quiero algo mucho más impactante". Elección: estación de forja inmersiva (vitrina central grande) + vibe forja/industrial. Blueprint por design_agent en design_guidelines.json.
- Rediseño SOLO de presentación (lógica intacta: CraftingContext, craft/claim/cancel, WS, sonidos, 0 exploits). 
- Layout nuevo (SkinCrafting.jsx + parts.jsx reescritos): IZQUIERDA = Fragua activa (cola tipo hornos) + Recetas (rail con tabs); CENTRO = ForgeStage (escenario grande: skin en object-contain sobre yunque, heat-glow molten, brasas/embers, nombre molten-text, y barra de acción Forjar/Reclamar/progreso); DERECHA = MaterialsTray (suministros) + RequirementsPanel (requisitos + Recibirás).
- CSS industrial en index.css: heatGlow, emberRise (.ember), .forge-panel (placas de hierro), .forge-rivet (remaches), .hazard-stripes, moltenText, .forge-anvil-base. Barras de progreso = HeatBar con forge-progress shimmer.
- Componentes eliminados de uso: MaterialsBar/RecipeDetail (reemplazados por MaterialsTray/RequirementsPanel/ForgeStage). Todos los data-testid preservados.
- Verificado: testing_agent iteration_32.json 100% — render 3 columnas desktop + stack móvil sin overflow (1920/390), craft (bones 810->690) + claim + tabs, cero errores de consola. crafting_speed_mult sigue en 60 (modo prueba del usuario; pendiente resetear a 1 para producción).

## Actualización 22 (Jun 2026) — SISTEMA DE CLANES (Fase 1: Hub) ✅
Server-authoritative, WS en vivo, 0 exploits. Turf Wars = Fase 2 (irá en el Live Map, requiere mod del juego).
### Backend (`/app/backend/clans.py`, wired en server.py + startup clans.ensure_indexes)
- Colecciones: clans (ranks embebidos), clan_members (único user_id => 1 clan por jugador), clan_invites, clan_messages (chat con historial), clan_settings(_id="clans"). Índices únicos name/tag/user_id.
- Fundar: cobro ATÓMICO con $gte de moneda configurable (default 20.000 Amberium=vip_coins; admin puede cambiar a PrimeMeat=coins y el monto). Refund si falla. Validación name(3-28)/tag(2-5 A-Z0-9) únicos.
- Permisos por rango (edit_clan/manage_ranks/assign_ranks/invite/kick/manage_members); líder = todos. Rangos default: Líder/Oficial/Miembro. CRUD de rangos, asignar, invitar (por nombre/steam/id), aceptar/rechazar, expulsar, transferir liderazgo, salir, disolver.
- Chat privado en tiempo real vía WS hub (por usuario, empuja a los uids del clan) + historial persistido + mensajes de sistema.
- Admin: GET/PUT settings (moneda/costo/min_members/creation_enabled), listar y eliminar clanes.
- Endpoints /api/clans: me, config, directory, found, edit, ranks(POST/DELETE), assign, invite(+accept/decline), kick, transfer, leave, disband, chat(GET/POST), ws, admin/settings, admin/list, admin/delete.
### Frontend
- Ruta /clanes (`pages/Clans.jsx` + `context/ClanContext.jsx` WS): vista SIN clan (formulario fundar con color picker + costo + directorio + invitaciones) y HUB (header con tag/color/notoriedad/miembros, lista de miembros con online/rango/kick/transfer, chat en vivo, paneles Ajustes/Rangos/Invitar). Animaciones framer + sonidos (reutilizados). Nav: Comunidad > Clanes.
- Admin: `components/admin/AdminClans.jsx` (tab "Clanes").
### Verificación: testing_agent iteration_33.json — backend 7/7 pytest PASS; frontend E2E (fundar, hub, chat WS live + persistencia, rangos, disband) OK, responsive 1920/390. Fixes post-review aplicados: _members_view sin global (orden correcto bajo concurrencia), removido param muerto kicked_by.
### Nota UX menor (pre-existente): los flyouts del nav en hover pueden solaparse con los paneles del hub; no bloqueante.
### PENDIENTE Fase 2: Turf Wars (zonas en el Live Map, entrada/combate/timer de captura server-authoritative vía mod, notoriedad, coloreado del mapa por clan, anuncios).

## Actualización 23 (Jun 2026) — TURF WARS (Fase 2 de Clanes) + Rediseño de creación de clan [iteration_34: BE 100% 15/15, FE ~95%]
Guerra de territorios server-authoritative integrada en el MAPA EN VIVO (Dino en Vivo > Mapa). Simulada en preview, lista para conectar al mod real.
### Backend `/app/backend/turfwars.py` (wired en server.py ~L18984 + startup turfwars.start_loops)
- Colecciones: `turf_zones` (10 territorios con owner_clan_id/contest), `turf_settings` (_id="turf": capture_seconds=30, min_presence=1, tick_seconds=5, deploy_window=60, rally_seconds=120, rally_push=10, notoriety_capture=50, notoriety_hold=2, sim_enabled).
- Mecánica (elección del usuario): captura = clan con MÁS miembros presentes en la zona que SOSTIENE `capture_seconds`. Al capturar: cambia dueño, se colorea el badge en el mapa con el color del clan, +notoriedad, y ANUNCIO EN EL CHAT DEL CLAN (al que captura "⚔️ ¡Capturamos X!" y al que pierde "🏴 Perdimos X ante [TAG]"). Renta de notoriedad por zona sostenida (~cada 60s).
- Presencia SIMULADA por ventanas estables (random.Random(clan:window)) usando todos los clanes de db.clans (reales + 3 rivales IA seed: ALBA/OBSD/CNBR). `presence_provider` devuelve None en preview -> sim; gancho para telemetría real futura. RALLY: POST /turf/rally {zone_id} (debe estar en clan; 429 si ya hay rally activo) refuerza presencia (rally_push) para poder capturar; anuncia "📣 ¡Rally a X!" al chat.
- Endpoints /api/turf: GET /state (zonas+leaderboard+my_clan_id+my_rally), GET /config, POST /rally, WS /ws (broadcast turf:state/turf:captured), admin: GET/PUT /admin/settings, POST /admin/capture, POST /admin/reset.
- Anuncios reutilizan clans._sys_msg + clans._push_clan_update (inyectados en configure). Notoriedad incrementa db.clans.notoriety (se refleja en el Hub de clanes).
### Frontend
- `hooks/useTurf.js` (WS público + fetch, rally con set optimista de my_rally), `components/livemap/InteractiveMap.jsx` (capa "Turf Wars" con toggle map-toggle-turf; badges turf-zone-<id> coloreados por dueño, anillo de disputa turf-contest-ring + barra de progreso; clic en badge = rally si estás en clan), `components/livemap/TurfWarsPanel.jsx` (leaderboard "Dominio de territorios" + "Tu frente" con botones de rally por zona), `pages/MyDino.jsx` (pestaña Mapa ahora SIEMPRE renderiza el mapa + panel, aunque no haya dino en vivo — aviso map-offline-note; antes estaba gateado por in_game que en preview siempre es false).
- api.js: turfState/turfConfig/turfRally/turfWsUrl/turfAdmin*.
- Admin: `components/admin/AdminClans.jsx` amplió con sección "Turf Wars" (ajustes + reset de territorios).
### Rediseño creación de clan (petición con capturas de referencia)
- `pages/Clans.jsx`: vista SIN clan ahora es ESTADO VACÍO ("No estás en un clan aún" + botón open-found-modal) + MODAL `FoundModal` (vista previa [TAG]+nombre, nombre con contador x/28, tag, fila de COLORES PREDEFINIDOS swatches found-color-<hex>, costo, botón found-submit). Botón deshabilitado hasta tag EXACTO 4 chars + nombre>=3.
- REGLA NUEVA: el TAG debe tener EXACTAMENTE 4 caracteres (A-Z 0-9) y único en el servidor. Backend clans.py do_found/do_edit: regex `[A-Z0-9]{4}`. (Nombre sigue 3-28, único.)
### Verificación: testing_agent iteration_34.json — Backend pytest 15/15 (state shape, progreso de sim en 35s, rally requiere clan/429/mensaje al chat, admin settings/capture/reset, regla tag 3/4/5 + unicidad 409). Frontend E2E: estado vacío -> modal -> matriz de validación (submit deshabilitado con tag<4, habilitado con tag=4, input clampa a 4), swatches, mapa siempre renderiza con capa Turf + badges coloreados + panel/leaderboard. Único detalle menor (resuelto): banner de rally ahora se muestra al instante (set optimista de my_rally en useTurf).
### Nota preview: la cuenta demo (POST /api/auth/demo) tiene 10.000.000 de Amberium para pruebas y quedó SIN clan (para ver el estado vacío/creación). El mapa en vivo no muestra la posición propia en preview (necesita el mod real); Turf Wars sí funciona simulado.
### PENDIENTE Fase 3: conectar presencia real de miembros por zona desde el mod (presence_provider), coordenadas de zonas ajustables por admin, y (multi-worker) mover _rally/_tick_count a Mongo si se escala a >1 worker.

## Actualización 24 (Jun 2026) — Switch de chat: Chat del Clan ↔ Chat Global (Clanes)
Petición (con mockup): switch en el chat del Hub para alternar entre chat SOLO de tu clan y un CHAT GLOBAL entre todos los clanes.
- Backend clans.py: canal global usando `clan_messages` con clan_id sentinel `GLOBAL_ROOM="__global__"`; los mensajes globales guardan clan_tag/clan_color/sender_clan_id del emisor. `_post_global_message` hace `hub.broadcast_all("clan:global", ...)` a TODOS los conectados. `do_chat(user,text,channel)` y `get_chat_history(user,limit,channel)` con channel "clan"|"global". ChatIn.channel. Endpoints: GET /clans/chat?channel=..., POST /clans/chat {text,channel}. Requiere estar en un clan para leer/escribir en ambos canales.
- Frontend: ClanContext expone `globalMessages` (carga inicial + evento WS clan:global). Clans.jsx ClanChat con SWITCH [data-testid=chat-channel-toggle] (verde=clan, azul=global), listas separadas, placeholder e ícono según canal, y badge [TAG] del clan emisor en mensajes globales. Verificado backend (curl: separación clan/global + tag) + screenshots desktop/móvil (sin overflow).

## Actualización 25 (Jun 2026) — Rediseño COMPLETO del Hub de Clanes (estilo mockup del usuario)
El usuario pidió (con mockup) rediseñar el Hub para verse como un panel de clan tipo juego. Implementado fiel a la imagen.
### Backend clans.py (nuevos datos + solicitudes de ingreso)
- `_pub_clan` ahora incluye: `code` (#NNNN derivado del id), `level`/`xp_into`/`xp_needed` (curva: nivel n cuesta n*1000 XP; XP = notoriedad), `territories` (count turf_zones owner==clan), `language` (def "Español"), `clan_type` (def "PvP / Territorios").
- `build_me` añade `online_count`, y para líder/invite/manage_members: `sent_invites` (invitaciones enviadas pendientes con nombre/nivel) y `join_requests` (solicitudes de ingreso).
- Helpers: `_acct_level(u)` (nivel de cuenta = 1 + coins/50000, máx 99), `_player_status(u)` (En partida/En línea/Ausente por active_dino y last_login).
- SOLICITUDES DE INGRESO (nueva colección `clan_requests`): POST /clans/request (solicitar unirse), /clans/request/cancel, /clans/request/accept (perm invite), /clans/request/decline. BÚSQUEDA: GET /clans/players/search?q= (jugadores con nivel/estado/in_clan/invited). CANCELAR INVITACIÓN: POST /clans/invite/cancel. do_edit acepta language/clan_type. Índice clan_requests en ensure_indexes.
### Frontend Clans.jsx (Hub reconstruido)
- Layout: sidebar izquierdo (Mi Clan/Explorar Clanes/Solicitudes/Invitaciones/Territorios/Turf Wars/Ranking/Configuración + imagen T-Rex) + contenido principal.
- BannerHeader: fondo selva/montaña (grayscale) + gradiente color del clan, [TAG] grande, nombre + corona, lema, meta (Fundado/ID #code/Idioma/Tipo), botón Editar clan, hexágono de NIVEL + barra XP, fila de 4 stats (Miembros/Online/Notoriedad/Territorios).
- ClanTabs: Resumen/Miembros/Chat/Invitaciones/Rangos/Territorios/Turf Wars/Estadísticas/Configuración (badge de pendientes).
- Paneles laterales (RightPanels): Invitar Jugadores (búsqueda en vivo `clanPlayerSearch` + Invitar), Invitaciones Pendientes (cancelar), Solicitudes para Unirse (aceptar/rechazar). Roles con color (RoleBadge). SettingsPanel ampliado con Idioma/Tipo y swatches de color + tag de 4.
- api.js: clanPlayerSearch, clanCancelInvite, clanRequestJoin/Cancel/Accept/Decline. ClanContext maneja evento WS clan:invite_cancelled.
### Verificación: curl E2E (payload con level/xp/code/territories/language/type/online; players/search; flujo de solicitud insertar→payload→accept añade miembro y limpia solicitud) + screenshots desktop 1920 (sin overflow) y móvil 390 (banner apila, tabs con scroll horizontal por diseño). Testing_agent pendiente para flujos UI.
### data-testids clave: clan-hub, clan-header, clan-tabs, tab-<id>, side-<tab>-<label>, invite-players, invite-search, invite-player-<id>, pending-invites, cancel-invite-<id>, join-requests, accept-request-<id>, decline-request-<id>, member-row-<id>, edit-clan-btn, save-settings-btn.

## Actualización 26 (Jun 2026) — Ajuste fiel al mockup del Hub de Clanes
El usuario pidió: quitar la barra de tabs superior (redundante con el sidebar) y que el diseño sea EXACTO al mockup (fondo + tipografías).
- QUITADA la barra de tabs superior (ClanTabs). El SIDEBAR izquierdo (8 ítems del mockup: Mi Clan, Explorar Clanes, Solicitudes, Invitaciones, Territorios, Turf Wars, Ranking, Configuración) es ahora la única navegación; en móvil se muestra como nav horizontal (data-testid=clan-mobile-nav). Estado activo estilo mockup (verde sólido + glow interior). Miembros y Rangos se movieron dentro de Configuración.
- FUENTE tipo brocha/graffiti: agregado import de Google Font "Bangers" + clase `.font-brush` en index.css. Aplicada al nombre del clan (grande) y al badge [TAG] (con glow neón del color del clan).
- FONDO del banner: generado con IA para igualar el mockup (selva verde vibrante a la izquierda → montaña/volcán gris con pterosaurios volando a la derecha). Imagen a color (ya no grayscale) + gradiente oscuro de izquierda para legibilidad. T-Rex del sidebar también regenerado (cabeza realista en selva oscura).
- tabs internos ahora: miclan (banner+chat+paneles Invitar/Invitaciones/Solicitudes), explorar, solicitudes, invitaciones, territorios/turfwars, ranking, config. data-testids: side-<tab>, clan-mobile-nav, config-tab.
- Verificado por screenshots desktop 1920 (sin overflow, idéntico al mockup) y móvil 390 (banner apila, nav horizontal). Funcionalidad de endpoints sin cambios (validada en iteration_35).

## Actualización 27 (Jun 2026) — Fidelidad exacta al mockup (layout + colores verdes)
- Quitado el título de página extra ("HUB DE CLANES / CLANES") — el hub empieza directo con sidebar+banner como el mockup.
- Banner reestructurado a 2 columnas: IZQUIERDA identidad ([TAG]+nombre+lema+meta), DERECHA Editar clan + Nivel/XP + las 4 stats EN FILA (Miembros/Online/Notoriedad/Territorios) con iconos del color del clan (antes iban a lo ancho abajo).
- Color de acento del clan puesto en VERDE (#3BE854) para demo (Escuadron Prueba/TEST) y para el clan real del usuario (Bluecito/BLUE) para igualar el mockup. Lema en verde mayúsculas. tag/nivel/XP/stats usan clan.color.
- Verificado por screenshot desktop: coincide con el mockup (m3).

## Actualización 28 (Jun 2026) — Pulido fiel al mockup (chat, stats, animaciones, sonidos)
- ClanChat rehecho EXACTO al mockup: avatares por mensaje, nombre + RoleBadge de color (Líder dorado/Comandante púrpura/Veterano azul/etc, derivado de me.members), timestamp a la derecha (fmtTime), mensajes de "Sistema · HH:MM" en caja con borde-izq verde + icono engranaje. Barra de envío con Paperclip + input + Smile + botón verde (hover scale). Switch Clan/Global con glow + icono gear.
- Banner: fila de meta con iconitos (Calendar/Hash/Globe/Swords); stat cells con icono a la IZQUIERDA (no centrado) en la columna derecha.
- Panels: enlace "Ver todas ›" en Invitaciones Pendientes y Solicitudes (Panel acepta prop `right`).
- Sonidos (useSound synth): clic al navegar en sidebar/móvil, al enviar mensaje y al alternar canal. Animaciones framer-motion de entrada en banner y mensajes.
- Helpers añadidos: fmtTime, Avatar. Verificado por screenshot desktop: coincide con el mockup (m3) incluyendo chat con roles/horas y mensajes de sistema.

## Actualización 29 (Jun 2026) — Assets propios del usuario + fondo de página
- El usuario envió un sprite sheet (artifact 4BA83F88...webp, 2000x667) con sus assets. Recorté con PIL y guardé en /app/frontend/public/clan/: banner.jpg (montaña+selva+pterosaurios), trex.jpg (T-Rex rugiendo), pagebg.jpg (textura selva oscura).
- Clans.jsx: BANNER_IMG=/clan/banner.jpg, TREX_IMG=/clan/trex.jpg, PAGE_BG=/clan/pagebg.jpg.
- ClansInner ahora tiene FONDO DE PÁGINA a pantalla completa (capa -z-10 sticky con PAGE_BG opacity .28 + overlays oscuros + glow verde). El hub va encima, como el mockup.
- Verificado por screenshot: banner y T-Rex son los assets del usuario; el hub se ve sobre el fondo de selva.
- Assets adicionales disponibles en el sheet para futuro (badges de rango en dorado/verde/púrpura/rojo, marcos hexagonales, texturas de botón con garras, banderas, huevo) si se quiere reemplazar iconos por sprites.


## 2026-06-24 — Clan Hub match 1:1 con mockup BLUECITO (fondo bosque)
- **Fondo de bosque**: nuevo `/app/frontend/public/clan/forestbg.jpg` (imagen del usuario, panorámica selva/volcán). Aplicado como fondo `fixed` a pantalla completa en `ClansInner` (opacity 0.6) con vignette radial + sombras laterales para dejar el follaje visible en los bordes y HUD legible. Reemplaza el antiguo `pagebg.jpg` (tira tenue).
- **Barra de pestañas horizontal** (según mockup) añadida en `Hub` bajo el banner: Resumen, Miembros, Chat, Invitaciones, Rangos, Territorios, Turf Wars, Estadísticas, Configuración. Pestaña por defecto = Chat. `data-testid` `clan-top-tabs` / `toptab-*`. Sidebar izquierdo "Mi Clan" ahora mapea a `chat`.
- **Datos demo del clan TEST (Escuadron Prueba)** poblados vía `/app/backend/_seed_clan_demo.py` (idempotente): ranks de colores (Comandante morado, Veterano azul, Oficial morado, Cazador verde, Miembro), 7 miembros, chat de conversación del mockup, 3 invitaciones pendientes (TTV_Killer/ShadowPR/RaptorQueen), 2 solicitudes (CrosFight/Zylux), pool de invitables con estados (En línea/En partida/Ausente). Nivel 12 (notoriety 74450 → 8450/12000 XP), idioma Español, tipo PvP/Territorios.
- **Turf Wars fix (anti-spam de chat)**: en `turfwars.py::_compute_presence` los clanes de jugadores (con `leader_id`) YA NO participan de la simulación pasiva; solo entran al hacer rally. Las IA (ALBA/OBSD/CNBR) siguen peleando entre sí. Esto evita que el chat del clan del jugador se inunde de "Capturamos/Perdimos".
- Verificado por screenshots: desktop 1536/1920 y móvil 390. Pendiente verificación visual final del usuario.

