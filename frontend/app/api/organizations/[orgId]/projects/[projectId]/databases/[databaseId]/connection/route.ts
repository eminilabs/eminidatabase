import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

/** On-demand only — the connection page never preloads this; it fetches real
 * credentials (including a plaintext password) only when the user explicitly
 * clicks "Reveal" (cf. RBAC's `database:connect` tier, narrower than
 * `database:read`, backend/app/services/rbac.py). An optional `credential_id`
 * picks which role's credentials to return, defaulting to the primary APP role. */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ orgId: string; projectId: string; databaseId: string }> }
) {
  const { orgId, projectId, databaseId } = await params;
  const credentialId = new URL(request.url).searchParams.get("credential_id") ?? undefined;
  const client = await getApiClient();
  try {
    const connection = await client.getConnection(orgId, projectId, databaseId, credentialId);
    return NextResponse.json(connection);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
