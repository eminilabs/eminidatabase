import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker build only (frontend/Dockerfile sets DOCKER_BUILD=1) — produces
  // .next/standalone (a pruned server bundle with just the needed
  // node_modules subset), so the production image doesn't have to ship the
  // full node_modules tree. Gated behind the env var rather than always on:
  // "next start" (used by local `npm run start` and Playwright's webServer)
  // warns that it "does not work with output: standalone" and wants
  // `node .next/standalone/server.js` instead — true unconditionally, so
  // local dev stays on the plain build instead.
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
};

export default nextConfig;
