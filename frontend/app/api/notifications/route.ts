import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function GET() {
  const client = await getApiClient();
  try {
    const notifications = await client.listNotifications();
    return NextResponse.json(notifications);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
