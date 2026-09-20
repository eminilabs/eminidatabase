import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function GET(
  _request: Request,
  {
    params,
  }: {
    params: Promise<{ orgId: string; projectId: string; databaseId: string; backupId: string }>;
  }
) {
  const { orgId, projectId, databaseId, backupId } = await params;
  const client = await getApiClient();
  try {
    const backup = await client.getBackup(orgId, projectId, databaseId, backupId);
    return NextResponse.json(backup);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
