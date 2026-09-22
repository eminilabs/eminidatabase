import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * `middleware.ts` is deprecated in Next.js 16, renamed to `proxy.ts` (same
 * behavior, cf. node_modules/next/dist/docs/.../file-conventions/proxy.md).
 *
 * Decodes the JWT's own `exp` claim (no signature verification — that needs
 * the backend's signing secret, which this runtime deliberately doesn't
 * hold; the backend is still the authoritative check on every actual API
 * call). This is the one place that reliably runs on *every* request to a
 * protected route, including client-side (soft) navigations via <Link> —
 * unlike a layout's own Server Component, which Next.js does not re-execute
 * on a soft navigation. Without this, a token that ages out mid-session
 * (ACCESS_TOKEN_EXPIRE_MINUTES, 30 min) would only be caught the next time a
 * page happens to call the backend and get a 401, which throws instead of
 * redirecting anywhere near the user's actual navigation.
 */
const SESSION_COOKIE = "eminidb_session";
const PROTECTED_PREFIX = "/dashboard";
const AUTH_PAGES = ["/login", "/register"];

function getExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const { exp } = JSON.parse(json) as { exp?: number };
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

function isValidSession(token: string | undefined): boolean {
  if (!token) return false;
  const exp = getExpiry(token);
  return exp !== null && exp * 1000 > Date.now();
}

export function proxy(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const valid = isValidSession(token);
  const { pathname } = request.nextUrl;

  if (pathname.startsWith(PROTECTED_PREFIX) && !valid) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    if (token) response.cookies.delete(SESSION_COOKIE);
    return response;
  }

  if (AUTH_PAGES.includes(pathname) && valid) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
