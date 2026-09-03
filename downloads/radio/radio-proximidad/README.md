# Radio de Proximidad — paquete

Consola de comunicaciones de voz por proximidad para tu app (React).
Incluye: encender/apagar, PTT / micrófono abierto, tecla PTT configurable
(Espacio/V/T/C), volumen general (± y silenciar a todos), diales de Alcance y
Nitidez, roster de jugadores en/fuera de rango con marcador de "hablando",
volumen y mute por jugador, favoritos, bloquear (persistente), historial de
últimos en hablar, selector de dispositivos (mic/altavoz), prueba de micrófono,
supresión de ruido e indicador VAD.

## 📁 Archivos
- `frontend/src/pages/ProximityVoice.jsx` — la página/consola (UI completa).
- `frontend/src/lib/proximitySim.js` — SIMULACIÓN local + hook de micrófono
  (`useProximitySim`, `useMicLevel`): VU real, dispositivos, prueba de mic, favoritos/bloqueados.
- `frontend/src/context/VoiceContext.jsx` — voz REAL con LiveKit (para el servidor de juego).
- `frontend/src/lib/voiceFalloff.js`, `voiceRoster.js`, `voiceSettings.js` — lógica de la voz real.

## 🔧 Integración

### 1) Ruta (en `src/App.js`)
```js
const ProximityVoice = React.lazy(() => import("@/pages/ProximityVoice"));
// dentro de <Routes>:
<Route path="/proximity-voice" element={<ProximityVoice />} />
```

### 2) Dependencias
- `framer-motion`, `lucide-react`, Tailwind (y shadcn/ui opcional).
- Solo para la voz REAL: `livekit-client`.
- La página usa `useSound()` de tu `SoundContext` (reproduce "click"/"open"/"close").
  Si no lo tienes, cambia `const { play } = useSound();` por `const play = () => {};`.

### 3) Modo de funcionamiento
- **Preview / sin servidor:** `ProximityVoice.jsx` usa `proximitySim.js` (jugadores simulados
  que se mueven; el micrófono real alimenta el VU meter y la prueba de mic). Funciona tal cual.
- **Producción con servidor de juego:** usa `VoiceContext.jsx` (LiveKit). Necesita en tu backend
  el endpoint `POST /api/voice/token` que emite un token de LiveKit, y el bridge del servidor
  que publica las posiciones para calcular el rango.

### 4) Persistencia
- Favoritos y bloqueados se guardan en `localStorage`: claves `prox_favs` y `prox_blocked`.

— La Isla Nublar LATAM.
