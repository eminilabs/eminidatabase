import { ApiError } from "@eminidatabase/sdk";
import { NextResponse } from "next/server";

/** The client-side TanStack Query calls in this app never talk to the FastAPI
 * backend directly — the session cookie is httpOnly, so only these Next.js
 * Route Handlers can attach it (cf. lib/api-server.ts). This normalizes a
 * thrown ApiError from the SDK into the same shape/status a direct backend
 * call would have produced. */
export function apiErrorResponse(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    return NextResponse.json({ detail: err.detail }, { status: err.statusCode });
  }
  return NextResponse.json({ detail: "Unexpected error" }, { status: 500 });
}
