import "server-only";

import { redirect } from "next/navigation";

import { PlatformClient } from "@eminidatabase/sdk";

import { getSessionToken } from "./session";

const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000/api/v1";

/** A PlatformClient authenticated with the current request's session cookie —
 * the standard way Server Components/Server Actions call the backend (SSR,
 * per the architecture doc's own reason for choosing Next.js). Returns a
 * client with `token: null` if there's no session; callers that require auth
 * should redirect to /login themselves rather than this helper doing it
 * implicitly (matches the "no return null in a shared layout" guidance —
 * auth checks belong close to what actually needs the data). */
export async function getApiClient(): Promise<PlatformClient> {
  const token = await getSessionToken();
  return new PlatformClient(BACKEND_API_URL, token);
}

function isExpired(token: string): boolean {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8")) as {
      exp?: number;
    };
    return typeof payload.exp !== "number" || payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

/** Same as getApiClient, but redirects to /login when the session is missing
 * or the JWT's own `exp` claim has already passed. `proxy.ts` runs this same
 * check ahead of every request to a protected route (including client-side
 * navigations) and is what actually clears the stale cookie — Server
 * Components aren't allowed to mutate cookies themselves. This is a cheap
 * defensive backstop for the rare path that reaches a Server Component
 * without going through the proxy (e.g. a stale RSC prefetch); a token
 * rejected by the backend for another reason (a rotated signing secret) still
 * throws an `ApiError` from the actual API call — that's caught by
 * `app/dashboard/error.tsx`. */
export async function requireApiClient(): Promise<PlatformClient> {
  const token = await getSessionToken();
  if (!token || isExpired(token)) {
    // Route through a handler that clears the cookie first (a Server
    // Component can't do that itself) — redirecting straight to /login
    // would leave a cookie proxy.ts still considers unexpired in place,
    // bouncing this same request right back here in a loop.
    redirect("/api/auth/invalidate-session");
  }
  return new PlatformClient(BACKEND_API_URL, token);
}
