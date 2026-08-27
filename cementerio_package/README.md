# Sistema de Cementerio & Fósiles — The Isle Evrima (La Isla Nublar LATAM)

Paquete con TODO el código del Cementerio (backend + frontend) para descargar.

## Contenido

```
cementerio_package/
├── README.md
├── backend/
│   └── cementerio_backend.py        # Módulo backend completo (extraído de server.py)
└── frontend/
    ├── pages/
    │   └── Cementerio.jsx           # Página principal del cementerio
    ├── components/cemetery/
    │   ├── Vines.jsx                # Enredaderas / dosel + telaraña de esquina
    │   ├── SpiderRunner.jsx         # Enjambre de arañas
    │   ├── HangingSpider.jsx        # Arañita colgante que sube/baja
    │   ├── FlyingCritters.jsx       # Murciélagos / polillas
    │   └── ResurrectionFX.jsx       # Overlay de partículas al resucitar
    └── cemetery.css                 # Keyframes a copiar dentro de index.css
```

## Backend (FastAPI + MongoDB)
`backend/cementerio_backend.py` es una EXTRACCIÓN del módulo que vive dentro de
`/app/backend/server.py`. No corre solo: depende de objetos globales de server.py
(`db`, `api_router`, `app`, `get_current_user`, `get_admin_user`, `add_log`,
`new_id`, `now_iso`, `_nonnegative_int`, `vault`, `JWT_SECRET`, etc.).

Wiring en el startup de server.py:
```python
@app.on_event("startup")
async def ...():
    ...
    try:
        await _cem_ensure_indexes()
        await _cem_seed_demo()
    except Exception:
        logger.warning("[cemetery] startup init skipped", exc_info=True)
```

### Endpoints (prefijo /api)
- GET  /api/cemetery/config
- GET  /api/cemetery/feed            (privado: solo tus dinos)
- GET  /api/cemetery/record/{id}
- GET  /api/cemetery/hall-of-fame
- GET  /api/cemetery/fossils
- POST /api/cemetery/fossils/buy
- POST /api/cemetery/fossils/claim-free
- GET  /api/cemetery/transactions
- GET  /api/cemetery/my-resurrections
- POST /api/cemetery/resurrect
- POST /api/cemetery/admin/record
- PUT  /api/cemetery/admin/record/{id}
- DELETE /api/cemetery/admin/record/{id}
- POST /api/cemetery/admin/fossils
- PUT  /api/cemetery/admin/config
- GET  /api/cemetery/admin/transactions
- GET  /api/cemetery/admin/records
- WS   /api/cemetery/ws

### Colecciones Mongo
`cemetery_records`, `fossil_transactions`, `resurrected_dinos`,
`settings` ({_id:"cemetery"}), y campos en `users`:
`fossils`, `vip_coins` (Amberiums), `last_free_fossil_month`, `last_resurrection_at`.

### Economía
- 1 Fósil = 8.000 Amberiums (vip_coins).
- 1 Fósil gratis por mes calendario.
- Cooldown de 24h tras resucitar; el dino resucitado no se puede redimir por 2h (anti revenge-kill).
- Ahogamiento en combate = NO REVIVIBLE (excepto Deinosuchus).

## Frontend (React)
- Copia `frontend/pages/Cementerio.jsx` a `src/pages/`.
- Copia la carpeta `frontend/components/cemetery/` a `src/components/`.
- Copia los keyframes de `frontend/cemetery.css` al final de `src/index.css`.
- Requiere: react-router, lucide-react, tailwind, y los componentes de shadcn/ui ya presentes en el proyecto.
- El WebSocket usa `REACT_APP_BACKEND_URL` (ws://.../api/cemetery/ws?token=<jwt>).

> Este paquete es para lectura/descarga. Para descargar TODO el proyecto usa el botón "Save to GitHub".
