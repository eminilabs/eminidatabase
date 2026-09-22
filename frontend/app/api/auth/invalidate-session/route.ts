import { NextResponse } from "next/server";

import { clearSessionToken } from "@/lib/session";

/** Redirect target for any Server Component that finds its session cookie
 * rejected by the backend (expired signature-wise, or revoked via
 * /auth/sessions/revoke-all) for a reason proxy.ts's own local `exp`-only
 * check can't see. Server Components can't mutate cookies themselves (cf.
 * lib/api-server.ts's requireApiClient docstring) — redirecting straight to
 * /login would leave the stale cookie in place, and since it still looks
 * unexpired to proxy.ts, that redirects it right back to /dashboard,
 * producing an infinite redirect loop instead of landing on /login. Route
 * Handlers CAN mutate cookies, so this one clears it before redirecting. */
export async function GET(request: Request) {
  await clearSessionToken();
  return NextResponse.redirect(new URL("/login", request.url));
}
