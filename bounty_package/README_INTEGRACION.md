# Paquete: Sistema de Bounty Hunting (Global P2P)

Este paquete contiene TODO el código del sistema de cacería/bounties (React + FastAPI).

## Estructura incluida

```
backend/
  bounty.py                     # Motor completo: lógica, anti-exploit, motivos, leaderboard, WS, Discord
frontend/src/
  pages/
    Bounty.jsx                  # Hub principal (layout 3 columnas, feed, leaderboard)
    BountyOverlay.jsx           # Overlay opcional
  components/bounty/
    BountyCard.jsx              # Tarjeta WANTED (glow CSS, motivos, #1 morado)
    TargetList.jsx              # Lista de objetivos online (#1 Más Buscado morado)
    ContractModal.jsx           # Modal para poner precio a un objetivo
    BountyWidget.jsx            # Widget compacto (para otras páginas)
    BountySelfInvite.jsx        # Auto-bounty / invitación
  context/
    BountyContext.jsx           # Estado global, WebSocket, feed, alertas
  lib/
    bountyMeta.js               # Helpers (formato, glyphs de dinos, countdown)
reference/
  server_wiring.py              # Snippet EXACTO de cómo se conecta bounty.py en server.py
```

## Cómo integrarlo en otro proyecto FastAPI + React

### Backend (`server.py`)
1. Copia `bounty.py` junto a tu `server.py`.
2. Añade el bloque de `reference/server_wiring.py` a tu `server.py`. Debes proveer
   estas funciones de tu propio código (billetera, roster online, usuarios):
   - `_bounty_online_players()` -> lista de jugadores online (o `None` para modo simulado)
   - `_bounty_resolve_user_id(sid)` / `_bounty_user_info(uid)`
   - `_bounty_charge_wallet` / `_bounty_refund_wallet` / `_bounty_award_reward` (atómicos con `$gte`)
   - `_bounty_ingame_grant(sid, prime, amber, xp)` (opcional, best-effort)
3. Llama a `bounty.configure(...)` y luego
   `app.include_router(bounty.build_router(get_current_user, get_admin_user), prefix="/api")`.
4. En tu hook de muerte del juego, llama `await bounty.on_kill(killer_sid, victim_sid)`.

Endpoints expuestos (todos bajo `/api`):
- `GET  /bounty/config`, `GET /bounty/board`, `GET /bounty/targets`
- `GET  /bounty/mine`, `GET /bounty/history`, `GET /bounty/leaderboard`
- `POST /bounty/contract`, `POST /bounty/contract/cancel`, `POST /bounty/self/start`
- `WS   /bounty/ws` (actualizaciones en tiempo real)

### Frontend (React)
1. Copia las carpetas `pages/`, `components/bounty/`, `context/`, `lib/` a tu `src`.
2. Envuelve tu app con `<BountyProvider>` (de `context/BountyContext.jsx`).
3. Enruta `pages/Bounty.jsx` (por ejemplo `/bounty`).
4. Asegúrate de tener: `framer-motion`, `sonner`, `lucide-react`, y un cliente `api`
   equivalente a `@/lib/api` con los métodos `bounty*` que usa `Bounty.jsx`.
5. Las animaciones de glow usan CSS keyframes (`.bounty-glow`, `.bounty-glow-top`,
   `.bounty-border-top`, `bounty-scan`, `decoShift`) — cópialas de tu `index.css`.

## Notas importantes
- Anti-exploit: cobros atómicos con `$gte`, idempotencia y validación server-side.
- Rendimiento: NO uses el prop `layout` de Framer en listas que se re-renderizan cada 1s;
  usa las animaciones CSS incluidas.
- Requiere MongoDB (colección `users` con `coins` = PrimeMeat y `vip_coins` = Amberium).
- Discord Webhook: se configura vía el panel admin del bounty (URL del webhook).
