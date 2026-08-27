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
