import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * `middleware.ts` is deprecated in Next.js 16, renamed to `proxy.ts` (same
 * behavior, cf. node_modules/next/dist/docs/.../file-conventions/proxy.md).
 *
 * Optimistic check only — presence of the session cookie, not signature/
 * expiry verification (that needs the JWT secret, which this Edge-ish
 * runtime shouldn't hold; the backend is the authoritative check on every
 * actual API call). This just avoids rendering protected UI for someone with
 * no cookie at all, and keeps a logged-in user off the login/register forms.
 */
const SESSION_COOKIE = "eminidb_session";
const PROTECTED_PREFIX = "/dashboard";
const AUTH_PAGES = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  if (pathname.startsWith(PROTECTED_PREFIX) && !hasSession) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (AUTH_PAGES.includes(pathname) && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
