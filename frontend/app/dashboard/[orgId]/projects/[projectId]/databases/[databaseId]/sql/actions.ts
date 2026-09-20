"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

type ActionState = { error?: string } | undefined;

export async function saveQueryAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  _prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  const name = String(formData.get("name") ?? "");
  const query = String(formData.get("query") ?? "");
  const client = await getApiClient();
  try {
    await client.createSavedQuery(organizationId, projectId, databaseId, name, query);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(
    `/dashboard/${organizationId}/projects/${projectId}/databases/${databaseId}/sql`
  );
  return undefined;
}

export async function deleteSavedQueryAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  savedQueryId: string
): Promise<void> {
  const client = await getApiClient();
  await client.deleteSavedQuery(organizationId, projectId, databaseId, savedQueryId);
  revalidatePath(
    `/dashboard/${organizationId}/projects/${projectId}/databases/${databaseId}/sql`
  );
}
