# La Isla Nublar — Radio de Proximidad + Trade en Vivo (paquete)

Este paquete contiene el código de DOS sistemas listos para integrar en tu app
(React + FastAPI + MongoDB):

1. **Trade en Vivo P2P** (estilo BG3, 4 columnas, WebSocket, swap atómico, historial, anti-estafa, apilado ×N).
2. **Radio de Proximidad** (consola de comunicaciones: PTT/mic abierto, tecla configurable, volumen general ±, silenciar a todos, rango/nitidez, favoritos, bloquear, historial, dispositivos, prueba de mic, supresión de ruido, indicador VAD).

> Nota: ambos usan archivos COMPARTIDOS de la app (api.js, media.js, sounds.js, App.js, server.py).
> Aquí incluyo los archivos propios de cada feature + este README con los fragmentos exactos
> que debes pegar en los archivos compartidos.

---

## 📁 Archivos incluidos

### Backend (FastAPI)
- `backend/live_trade.py` — router del Trade en Vivo (REST + WebSocket). Se monta en server.py.
- `backend/_seed_trade_test.py` — crea 2 usuarios de prueba con inventario + tokens JWT.
- `backend/_reset_trade_test.py` — limpia sesiones y resetea cooldowns/límites diarios.

### Frontend (React)
- `frontend/src/components/trade/LiveTradeHub.jsx` — lobby + WS + invitaciones + toggle En vivo/Historial.
- `frontend/src/components/trade/TradeRoom.jsx` — sala 4 columnas, apilado ×N, control de Amberium, anti-estafa.
- `frontend/src/components/trade/TradeHistory.jsx` — pestaña de historial.
- `frontend/src/pages/ProximityVoice.jsx` — página/consola de la Radio de Proximidad.
- `frontend/src/lib/proximitySim.js` — simulación de proximidad + hook de micrófono (VU, dispositivos, prueba de mic).
- `frontend/src/context/VoiceContext.jsx` — voz REAL con LiveKit (para el servidor de juego).
- `frontend/src/lib/voiceFalloff.js`, `voiceRoster.js`, `voiceSettings.js` — lógica de la voz real.

> Este paquete NO incluye ninguna sala/endpoint "demo" — fue retirado del código a petición.

---

## 🔧 Integración

### 1) Backend — montar el router de Trade (en `server.py`)
Después de crear `app` y `db`, y de definir `get_current_user`, `add_log`, `JWT_SECRET`, `JWT_ALGO`:

```python
import live_trade
app.include_router(
    live_trade.build_router(db, JWT_SECRET, get_current_user, add_log, JWT_ALGO),
    prefix="/api")
```

La Radio de Proximidad REAL usa `POST /api/voice/token` (LiveKit) — ver `voice_token.py`
en tu backend actual. Si solo quieres la simulación (preview), NO necesitas backend de voz.

### 2) Frontend — métodos de API (pega en `src/lib/api.js`)

WebSocket del trade (helper exportado):
```js
export function tradeWsUrl() {
  const base = process.env.REACT_APP_BACKEND_URL;
  const token = localStorage.getItem("primal_token"); // tu clave de token
  return `${base}/api/trade/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}
```

Métodos del cliente `api` (Trade en Vivo):
```js
tradeOnline:        () => client.get("/trade/online"),
tradeInventory:     () => client.get("/trade/inventory"),
tradeActive:        () => client.get("/trade/active"),
tradeInvite:        (to_user_id) => client.post("/trade/invite", { to_user_id }),
tradeRespond:       (session_id, accept) => client.post("/trade/respond", { session_id, accept }),
tradeSetOffer:      (session_id, items, amber) => client.post("/trade/offer", { session_id, items, amber }),
tradeLock:          (session_id, locked) => client.post("/trade/lock", { session_id, locked }),
tradeConfirm:       (session_id) => client.post("/trade/confirm", { session_id }),
tradeCancel:        (session_id) => client.post("/trade/cancel", { session_id }),
tradeHistory:       () => client.get("/trade/history"),
tradePeerInventory: (session_id) => client.get(`/trade/peer/${session_id}`),
```

Voz real (LiveKit), si usas `VoiceContext.jsx`:
```js
voiceToken: () => client.post("/voice/token", {}),
```

### 3) Frontend — assets e íconos compartidos

`src/lib/media.js` debe exponer la imagen de Amberium usada por el Trade:
```js
export const MEDIA = {
  coinNormal: `/coins/meat.png`,
  coinVip:    `/coins/amber.png`, // <- Amberium (usado en TradeRoom/TradeHistory)
};
```
Copia también los PNG a `frontend/public/coins/` (meat.png, amber.png).

`src/lib/sounds.js` debe incluir el sonido `coinSack` (tintineo suave de monedas) que usa el Trade:
```js
coinSack: () => {
  const parts = [2100, 2550, 3050, 1850];
  parts.forEach((f, i) => {
    bell({ freq: f + (Math.random() * 130 - 65), dur: 0.08 + Math.random() * 0.05, gain: 0.016, delay: i * 0.03, ratio: 3.2, index: 42 });
  });
  noise({ dur: 0.045, gain: 0.011, filterType: "bandpass", filterFreq: 2800, filterQ: 1.2, delay: 0.01 });
},
```
(Requiere los helpers `voice`, `bell`, `noise` que ya trae tu `sounds.js`, además del `SoundProvider`/`useSound`.)

### 4) Frontend — rutas (en `src/App.js`)

```js
const ProximityVoice = React.lazy(() => import("@/pages/ProximityVoice"));
// ...dentro de <Routes>:
<Route path="/proximity-voice" element={<ProximityVoice />} />
```
El Trade en Vivo se monta dentro del Mercado con el filtro "Trade en Vivo" que renderiza `<LiveTradeHub/>`.

### 5) Dependencias
- Frontend: `framer-motion`, `lucide-react`, `sonner`, Tailwind, shadcn/ui, y `livekit-client` (solo para la voz REAL).
- Backend: FastAPI, `motor` (MongoDB async), `pyjwt`.

---

## 🧪 Probar el Trade (2 usuarios reales)
```bash
python3 backend/_seed_trade_test.py      # crea userA/userB + imprime tokens
python3 backend/_reset_trade_test.py     # limpia sesiones/cooldowns
```
En el navegador: `localStorage.setItem('primal_token', '<TOKEN>')` y entra al Mercado → Trade en Vivo.
Ambos jugadores conectados se ven en el lobby y pueden invitarse.

## 📌 Reglas del Trade (en live_trade.py)
- Tradeable: Amberium (máx 1000 enviado/día), Skins, Huevos, Cofres. PrimeMeat NO. Dinosaurios excluidos.
- Cooldown 3 h por trade salvo que sea SOLO Amberium.
- Editar la oferta reinicia ambos bloqueos (dispara la alerta anti-estafa en el cliente).

## 📌 Radio de Proximidad
- En preview funciona con SIMULACIÓN local (`proximitySim.js`), sin servidor de juego.
- En producción, `VoiceContext.jsx` (LiveKit) maneja la voz real; el rango lo gestiona el bridge del servidor.
- Favoritos/bloqueados persisten en `localStorage` (`prox_favs`, `prox_blocked`).

— Generado para descarga. La Isla Nublar LATAM.
