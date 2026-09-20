import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const client = await getApiClient();
  try {
    await client.markNotificationRead(id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return apiErrorResponse(err);
  }
}
