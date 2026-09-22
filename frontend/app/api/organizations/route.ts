import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function GET() {
  const client = await getApiClient();
  try {
    const organizations = await client.listOrganizations();
    return NextResponse.json(organizations);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
