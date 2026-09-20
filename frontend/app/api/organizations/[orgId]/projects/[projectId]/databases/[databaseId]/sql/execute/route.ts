import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; projectId: string; databaseId: string }> }
) {
  const { orgId, projectId, databaseId } = await params;
  const body = (await request.json().catch(() => null)) as { query?: string; roleId?: string } | null;
  if (!body?.query) {
    return NextResponse.json({ detail: "Missing query" }, { status: 400 });
  }

  const client = await getApiClient();
  try {
    const result = await client.executeSql(orgId, projectId, databaseId, body.query, body.roleId);
    return NextResponse.json(result);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
