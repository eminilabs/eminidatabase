import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ orgId: string; projectId: string; databaseId: string }> }
) {
  const { orgId, projectId, databaseId } = await params;
  const client = await getApiClient();
  try {
    const database = await client.getDatabase(orgId, projectId, databaseId);
    return NextResponse.json(database);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
