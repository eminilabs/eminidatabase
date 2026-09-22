# eminidatabase frontend (Next.js standalone build).
#
# Build context is the REPO ROOT, not this directory — the frontend depends
# on the sibling `@eminidatabase/sdk` npm workspace package (source-consumed,
# no publish step), so `npm ci` needs the root package.json/lockfile and both
# workspaces present. See docker-compose.prod.yml's `build.context: ..`.
#
# Next's standalone output mirrors the monorepo path it was built from (a
# known Next.js + npm-workspaces quirk), so the runner stage copies from
# `.next/standalone/frontend/` — not `.next/standalone/` directly.

FROM node:20-slim AS deps
WORKDIR /srv/app
COPY package.json package-lock.json ./
COPY frontend/package.json ./frontend/package.json
COPY sdk-ts/package.json ./sdk-ts/package.json
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /srv/app
COPY package.json package-lock.json ./
# npm workspaces hoist everything into the root node_modules (with a symlink
# for @eminidatabase/sdk -> ../sdk-ts) — there's no separate
# frontend/node_modules or sdk-ts/node_modules to copy.
COPY --from=deps /srv/app/node_modules ./node_modules
COPY sdk-ts ./sdk-ts
COPY frontend ./frontend
# NEXT_PUBLIC_BACKEND_URL is inlined into the client bundle at build time
# (the OAuth buttons navigate the browser straight to it) — a runtime
# `environment:` entry has no effect on already-compiled browser JS.
ARG NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
RUN npm run build --workspace=frontend

FROM node:20-slim AS runner
WORKDIR /srv/app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /srv/app/frontend/public ./public
COPY --from=builder --chown=node:node /srv/app/frontend/.next/standalone/frontend ./
COPY --from=builder --chown=node:node /srv/app/frontend/.next/standalone/node_modules ./node_modules
COPY --from=builder --chown=node:node /srv/app/frontend/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
