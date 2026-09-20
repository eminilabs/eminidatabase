# eminidatabase TypeScript SDK

TypeScript client for the eminidatabase Control Plane API — the TS port of
[`sdk/`](../sdk/README.md) (Python), built for the [`frontend/`](../frontend/) Next.js
app.

Same philosophy as the Python SDK: **every method is a thin wrapper around one API
call** — no client-side business logic, no caching, no retries. That keeps it
trivially easy to keep in sync with the API surface as the backend grows.

## Types

`src/types.gen.ts` is generated from the backend's live OpenAPI schema, not
hand-written — regenerate it whenever the backend's schemas change:

```bash
# with the backend running (uvicorn app.main:app) on 127.0.0.1:8000
npm run generate
```

Only endpoint groups actually consumed by `frontend/` so far have a wrapper method in
`src/client.ts` (auth, organizations, projects, databases, jobs, notifications) —
other groups' *types* are already generated and available for import from
`types.gen.ts`, but their wrapper methods are added incrementally as the pages that
need them are built, exactly like the Python SDK grew phase-by-phase.

## Test

```bash
npm test        # Vitest — mocks fetch, no backend needed
npm run typecheck
```
