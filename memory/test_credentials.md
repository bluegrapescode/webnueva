# Test Credentials — La Isla Nublar LATAM

## Demo / Admin account (preview)
- The backend runs with `ALLOW_DEMO_LOGIN=1` in `/app/backend/.env`.
- Get a token: `POST /api/auth/demo` → `{ "token": "<jwt>" }`
- The demo user has **role = admin** (full access, including `/admin`).
- Frontend stores the JWT in `localStorage` under key **`primal_token`**.
  - To authenticate in a browser/Playwright: go to site root, run
    `localStorage.setItem('primal_token', '<token>')`, then navigate.

Base preview URL: https://synced-animations.preview.emergentagent.com

## Notes
- Real login is Steam OAuth (needs the live game server / not available in preview).
- No standard email/password accounts exist; use the demo login above.

## Owner-in-simulation (2026-06)
- The demo account (`POST /api/auth/demo`) is now the OWNER playing in the sim:
  - `role = admin`, `staff_rank = owner` (full access, owner + glitch lab).
  - Seeds a simulated live in-game dino (prime Apex Tyrannosaurus Rex, 100% growth) so `_is_user_in_game` is true in preview (no RCON). This lights up payout counters, the HUD passive bar, live-dino status and population respawn.
- NOTE: skin apply-to-live (`/api/apply`, `/api/glitch/apply`) still needs the REAL game server (`game_ipc.find_active_dino`) and returns 409 in preview — cannot be simulated.

## Trade en Vivo P2P (test users) — 2026-06
- Usuario A (demo): POST /api/auth/demo -> token. steam_id demo_0000000001, id=3c45966b9bbf4bf59035ebae8237faa4. Inventario: Huevo Común x3, Skin Verde Selva x1. vip_coins(Amberium)=500.
- Usuario B (trader): id=96dffc3fe0de4217a969e56f2eec716f, steam_id demo_0000000002. Inventario: Huevo Raro x5, Cofre Bronce x2. vip_coins=500.
  - Token A (7 días, reseed 2026-06): eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzYzQ1OTY2YjliYmY0YmY1OTAzNWViYWU4MjM3ZmFhNCIsImV4cCI6MTc4ODgxNTI3MH0.gLTiY7CKG-VTEDlDjF9Lr-LOQiyYGxdN1o9q1DwP_F8
  - Token B (7 días, reseed 2026-06): eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NmRmZmMzZmUwZGU0MjE3YTk2OWU1NmYyZWVjNzE2ZiIsImV4cCI6MTc4ODgxNTI3MH0.ya9zVXQhdxY9b0LrPpRBFIj1is-7GunceV9hUluHqm4
- Reseed script: python3 /app/backend/_seed_trade_test.py (re-crea inventario y reimprime tokens).
