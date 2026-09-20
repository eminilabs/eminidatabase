import "server-only";

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
