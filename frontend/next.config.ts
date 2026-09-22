import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker build only — produces .next/standalone (a pruned server bundle
  // with just the needed node_modules subset), so the production image
  // doesn't have to ship the full node_modules tree. Irrelevant to local dev
  // (`next dev`/`next start` ignore it and behave the same either way).
  output: "standalone",
};

export default nextConfig;
