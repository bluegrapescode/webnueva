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
