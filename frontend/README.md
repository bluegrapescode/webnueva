# La Isla Nublar — Frontend

React single-page app (Create React App + craco + Tailwind), Spanish UI.
Served in production as static files by Caddy; all data comes from the
FastAPI backend under `/api`.

## Develop

```powershell
yarn install
yarn start          # dev server, proxies API per .env REACT_APP_BACKEND_URL
```

## Build for production

```powershell
yarn install
yarn build          # outputs build/
```

Deploying the build to the live box is covered in `../../docs/DEPLOYMENT.md`
(short version: copy `build\*` over `C:\LaIslaNublar\web\frontend\`, and make
sure BOTH hashed bundles — `static/js/main.<hash>.js` AND
`static/css/main.<hash>.css` — that the new `index.html` references are
shipped together with it).

## Notes

- `.env` holds `REACT_APP_BACKEND_URL` (see `.env.example`).
- 3D dino viewers stream models from `/dino-assets/...` served by the backend
  from the box's asset store (`C:\LaIslaNublar\web\assets\dinos`, ~2 GB —
  deliberately not in git).
- `src/constants/testIds/` is a registry of `data-testid` values used by UI
  test tooling; keep new interactive elements registered there.
