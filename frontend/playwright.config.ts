import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  reporter: "list",
  // Generous — Argon2 password/API-key hashing is deliberately memory/CPU-hard
  // and this suite has been observed taking well over 30s per test under real
  // contention on a shared dev machine (see dashboard-f2-f6.spec.ts).
  timeout: 120_000,
  use: {
    baseURL: "http://127.0.0.1:3000",
  },
  webServer: {
    command: "npm run start",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
