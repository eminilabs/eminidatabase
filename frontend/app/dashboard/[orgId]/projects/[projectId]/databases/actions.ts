"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getApiClient } from "@/lib/api-server";

export type DatabaseFormState = { error?: string } | undefined;

export async function createDatabaseAction(
  organizationId: string,
  projectId: string,
  _prevState: DatabaseFormState,
  formData: FormData
): Promise<DatabaseFormState> {
  const name = String(formData.get("name") ?? "");
  const regionCode = String(formData.get("region_code") ?? "");

  const client = await getApiClient();
  try {
    // 202 Accepted — the database starts PENDING and the worker provisions it
    // asynchronously (cf. docs/architecture/03). The list below polls job
    // status client-side rather than this action waiting on it.
    await client.createDatabase(organizationId, projectId, name, regionCode);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }

  revalidatePath(`/dashboard/${organizationId}/projects/${projectId}/databases`);
  return undefined;
}

export async function deleteDatabaseAction(
  organizationId: string,
  projectId: string,
  databaseId: string
): Promise<DatabaseFormState> {
  const client = await getApiClient();
  try {
    await client.deleteDatabase(organizationId, projectId, databaseId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(`/dashboard/${organizationId}/projects/${projectId}/databases`);
  redirect(`/dashboard/${organizationId}/projects/${projectId}/databases`);
}
