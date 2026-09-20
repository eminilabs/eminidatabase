# eminidatabase — Frontend (Phase F.1)

Next.js (App Router) dashboard for the eminidatabase Control Plane — see
[../docs/architecture/09-plan-de-phases.md](../docs/architecture/09-plan-de-phases.md#phase-f1--fondations--sdk-typescript-auth-complète-coquille-du-dashboard--implémentée-2026-09-20)
for what this sub-phase covers and what's deferred.

Consumes the backend exclusively through [`../sdk-ts/`](../sdk-ts/README.md) — no
direct database access, matching the same boundary the Python SDK/CLI keep with the
Control Plane API.

## Setup

```bash
# from the repo root — links frontend to the local sdk-ts workspace package
npm install
cp frontend/.env.example frontend/.env.local
```

Requires the backend running (`cd backend && uvicorn app.main:app`) and
`sdk-ts/src/types.gen.ts` generated at least once (`cd sdk-ts && npm run generate`,
with the backend up).

## Run

```bash
cd frontend
npm run dev
```

http://localhost:3000

## Session model

The backend JWT lives in an **httpOnly cookie**, set by this app's own Server
Actions/Route Handlers (a backend-for-frontend), never exposed to client-side JS —
see `lib/session.ts` and doc 04 §4.8 for why (chosen over `localStorage`
deliberately, not by default).

OAuth (Google/GitHub) is a real browser redirect through the provider and back to
`backend`'s `/auth/oauth/{provider}/callback`, which redirects here to
`/auth/callback` with the token in a URL **fragment** (never sent to any server) on
success, or `?error=` on failure. See `app/auth/callback/page.tsx`.

## Test

```bash
npm run lint
npx tsc --noEmit
npm run build            # also type-checks against sdk-ts's generated types
npm run test:e2e         # Playwright — builds/starts the app itself if not already running
```

Playwright tests run against a **production build** (`next start`), not `next dev` —
Turbopack's on-demand route compilation in dev mode can exceed Playwright's default
assertion timeouts on a route's first hit. Requires the backend and its Postgres
reachable at the URLs in `.env.local`.
