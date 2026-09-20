import { NextResponse } from "next/server";

import { setSessionToken } from "@/lib/session";

/** Called from app/auth/callback's client component with the token it read
 * out of the URL fragment (never sent here by the browser automatically —
 * fragments never leave the client — so this only ever receives it via an
 * explicit fetch from that page). Sets the same httpOnly cookie the
 * email/password Server Actions set, so both paths converge on one session
 * mechanism. */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { access_token?: string } | null;
  const token = body?.access_token;
  if (!token) {
    return NextResponse.json({ error: "Missing access_token" }, { status: 400 });
  }

  await setSessionToken(token);
  return NextResponse.json({ ok: true });
}
