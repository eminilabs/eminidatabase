import "server-only";

import { cookies } from "next/headers";

/**
 * The backend JWT, held in an httpOnly cookie — never exposed to client-side
 * JS (cf. docs/architecture/04-securite-et-isolation.md §4.8's note that
 * Phase F would change the OAuth callback hand-off, not its logic). Only
 * Server Actions and Route Handlers may call `.set`/`.delete` (Next.js
 * requirement); Server Components may only read it.
 */
const SESSION_COOKIE = "eminidb_session";

export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

export async function setSessionToken(token: string): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Mirrors the backend's own JWT lifetime (ACCESS_TOKEN_EXPIRE_MINUTES,
    // default 30) — no point outliving the token it holds.
    maxAge: 30 * 60,
  });
}

export async function clearSessionToken(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}
