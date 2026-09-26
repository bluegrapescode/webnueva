# Paquete: Sistema de Tickets + Sistema de Airdrop Global
La Isla Nublar LATAM — export de módulos

## Contenido
```
backend/
  tickets.py            # Sistema de Soporte/Tickets (WS, Discord, escalado/refuerzo, notas internas)
  airdrop.py            # Motor del Airdrop Global (state machine, claim atómico, WS, loot, chat global)
frontend/
  src/pages/Support.jsx                     # UI del sistema de Tickets (usuario + panel de staff)
  src/components/airdrop/AirdropArena.jsx   # Escena del Airdrop (caja, estallido, pool, recompensas)
  src/context/AirdropContext.jsx            # Provider global + avisos (toast/sonido) en toda la web
  src/hooks/useAirdropSocket.js             # WebSocket del Airdrop (reconexión + offset de reloj)
  public/airdrop/crate_common|rare|epic|legendary.png  # Imágenes de la caja por rareza
```

## IMPORTANTE — estos módulos dependen de cambios en archivos COMPARTIDOS
No se incluyen enteros (son del proyecto), pero necesitas estas líneas:

### backend/server.py
- Registrar el router del airdrop y arrancar el motor:
  ```python
  import airdrop
  airdrop.configure(db, add_transaction=add_transaction, ...)
  app.include_router(airdrop.router, prefix="/api")
  # en startup: await airdrop.start_engine()
  ```
- Configurar tickets (rangos que atienden: owner/admin/mod):
  ```python
  import tickets
  tickets.configure(db, admin_ids=ADMIN_STEAM_IDS, add_log=add_log,
      jwt_secret=JWT_SECRET, jwt_algo=JWT_ALGO,
      is_staff_fn=lambda u: (u.get("role")=="admin")
          or (u.get("staff_rank") in {"owner","admin","mod"})
          or (u.get("steam_id") in ADMIN_STEAM_IDS))
  app.include_router(tickets.router, prefix="/api")
  ```

### frontend/src/lib/api.js — añadir helpers
```js
export function airdropWsUrl() { /* ws://.../api/airdrop/ws?token= */ }
// en el objeto api:
airdropWsUrl, airdropState, airdropClaim, airdropHistory, airdropPool,
airdropSettings, airdropSaveSettings, airdropLaunch,
ticketTake, ticketEscalate, /* + resto de endpoints ticket* y ticketStaff */
```

### frontend/src/lib/sounds.js — añadir cues del airdrop
`airdropIncoming, airdropFalling, airdropLanded, airdropAvailable, airdropClaimed, airdropLegendary`

### frontend/src/App.js — montar el provider (dentro de BrowserRouter)
```jsx
import { AirdropProvider } from "@/context/AirdropContext";
<AirdropProvider> ... </AirdropProvider>
```

### frontend — pestaña Airdrop en Mini Juegos (Casino.jsx)
```jsx
import AirdropArena from "@/components/airdrop/AirdropArena";
{ k: "airdrop", label: "Airdrop", icon: Plane, C: () => <AirdropArena /> }
```

## Variables de entorno usadas
- backend: MONGO_URL, DB_NAME, JWT_SECRET, DISCORD_BOT_TOKEN, TICKETS_CHANNEL_ID, PUBLIC_URL
- frontend: REACT_APP_BACKEND_URL

## Endpoints principales
- Airdrop: GET /api/airdrop/state, /api/airdrop/state/public, /api/airdrop/pool,
  POST /api/airdrop/claim, /api/airdrop/launch (admin), WS /api/airdrop/ws
- Tickets: /api/tickets (CRUD), /api/tickets/staff, /api/tickets/{id}/take,
  /api/tickets/{id}/escalate, WS del soporte
