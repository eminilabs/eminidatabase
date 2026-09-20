"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

export type ApiKeyFormState = { error?: string; created?: { name: string; apiKey: string } } | undefined;

export async function createApiKeyAction(
  organizationId: string,
  _prevState: ApiKeyFormState,
  formData: FormData
): Promise<ApiKeyFormState> {
  const name = String(formData.get("name") ?? "");
  const client = await getApiClient();
  try {
    const created = await client.createApiKey(organizationId, name);
    revalidatePath(`/dashboard/${organizationId}/settings/api-keys`);
    return { created: { name: created.name, apiKey: created.api_key } };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
}

export async function revokeApiKeyAction(organizationId: string, apiKeyId: string): Promise<void> {
  const client = await getApiClient();
  await client.revokeApiKey(organizationId, apiKeyId);
  revalidatePath(`/dashboard/${organizationId}/settings/api-keys`);
}
