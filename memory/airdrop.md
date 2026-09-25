# Sistema de Airdrop Global — La Isla Nublar

## Fase 1 — Motor backend (COMPLETA, verificada 2026-06)
Archivo: `/app/backend/airdrop.py` (registrado en server.py junto a tickets).
- Evento global cada 60 min controlado por servidor. Estado autoritativo en `db.airdrops` (_id="current").
- Máquina de estados: waiting → incoming(60s) → falling(10s) → available(180s) → claimed/expired → cooldown(5min) → siguiente. Motor = asyncio loop 1s (`start_engine()` en startup).
- Contador global sincronizado: front calcula desde `drop_at`/`server_time`. Sync al entrar tarde vía `/api/airdrop/state` y WS `airdrop:sync`.
- **Claim atómico** `POST /api/airdrop/claim`: `find_one_and_update({state:available, winner_uid:None})` + asyncio lock → 1 solo ganador garantizado; idempotente por usuario. Requiere `steam_id`.
- Loot table configurable por rareza (common/rare/epic/legendary) en `db.airdrop_settings`. Recompensas generadas en servidor al caer, OCULTAS hasta reclamar (`contents: classified`; solo el ganador ve `my_rewards`).
- Entrega real reutilizando sistemas: PrimeMeat=users.coins, Amberium=users.vip_coins (+add_transaction), materiales=crafting._grant_materials (bones/metal/leather/polymer), tokens growth/diet/resurrection=db.inventory categoría "Tokens". Mínimos: Amberium 50, PrimeMeat 10000.
- Chat global automático (db.chat_messages, kind=airdrop): cayendo / aterrizó / ganador.
- Historial `db.airdrop_history`. Admin: GET/PUT `/api/airdrop/settings`, GET `/api/airdrop/history`, POST `/api/airdrop/launch {rarity}` (manual, drop en ~8s).
- WS `/api/airdrop/ws?token=`: eventos airdrop:sync|incoming|falling|available|claimed|rewards|expired|next.
- Verificado: launch epic → secuencia → 6 claims concurrentes (mismo user) idempotente → claimed, rewards entregadas, history 1, chat 3 mensajes.

## Fase 2 — Frontend premium (COMPLETA, verificada 2026-09-25)
- Componentes nuevos: `/app/frontend/src/components/airdrop/AirdropArena.jsx` (escena),
  `/app/frontend/src/context/AirdropContext.jsx` (provider global montado en App dentro de BrowserRouter),
  `/app/frontend/src/hooks/useAirdropSocket.js` (WS con reconexión + offset de reloj).
- API: `api.airdropWsUrl/airdropState/airdropClaim/airdropHistory/airdropSettings/airdropSaveSettings/airdropLaunch` en `lib/api.js`.
- Fases visuales sincronizadas 100% al servidor (offset server_time): waiting (contador HH:MM:SS) → incoming (alerta roja + reflectores) → falling (paracaídas SVG con caja, balanceo, posición por progreso drop→land) → available (caja aterrizada latiendo + botón RECLAMAR pulsante + cuenta atrás de cierre) → claimed (banner ganador o "X se lo llevó" + próximo airdrop) → expired → disabled.
- Revelado de recompensas CARTA POR CARTA (flip 3D al clic) + botón "Revelar todo". Icono por material (frontend). Sonido especial legendary/resurrection.
- 6 sonidos sintetizados en `lib/sounds.js`: airdropIncoming, airdropFalling, airdropLanded, airdropAvailable, airdropClaimed, airdropLegendary. Respetan el toggle 🔊 (SoundContext).
- Aviso GLOBAL (toast + sonido) en cualquier página del sitio cuando cae/aterriza/es reclamado (AirdropProvider). Se omite si ya estás en /mini-juegos. Acción "Ver/Reclamar" navega a la pestaña.
- Verificado E2E: launch legendary → available con botón → claim → 8 recompensas entregadas (saldos PrimeMeat/Amberium subieron) → history registrado. Layout OK en desktop 1920 y móvil 390.
- REDISEÑO 2026-09-25 (pedido usuario "mismo estilo que la ruleta"): AirdropArena reescrita con la estética de Nublar Spin (`Wheel.jsx`): fondo magenta/neón + palmeras (AmbientBackdrop), título italic a dos tonos AIR/DROP, HUDs glossy (EN VIVO, rareza, PrimeMeat, Amberium), puntero triangular + tarima con brillo rosa (StageBar). El protagonista es un COFRE 3D (componente `Chest`, tapa con bisagra rotateX, tintado por rareza) que se abre al ganar con rayos de luz. Botón `GlossyButton` con barrido de brillo. Confeti canvas (fireConfetti) en épico/legendario. Tarjetas de recompensa estilo placa (cinta de rareza + disco radial + gloss, flip 3D). Usan las IMÁGENES REALES de la web: materiales (iconos de la colección crafting_materials vía /crafting/state → matImg), PrimeMeat=/coins/meat.png, Amberium=/coins/amber.png, growth=/tokens/growth.png, diet=/tokens/diet.png; resurrection_token=/fossil.png (asset real de resurrección de la web). IMPORTANTE: los nodos con Motion NO usan `-translate-x-1/2` de Tailwind (Motion pisa `transform`); centrar con wrapper estático + hijo motion. Verificado desktop+móvil.

## Fase 3 — Panel de Admin (PENDIENTE)
Sección en el Admin Dashboard para editar `airdrop_settings` (intervalo, warning, falling, cooldown, pesos de rareza, loot table por rareza) vía GET/PUT `/api/airdrop/settings`, ver `/api/airdrop/history`, y lanzar manualmente vía POST `/api/airdrop/launch {rarity}`.

