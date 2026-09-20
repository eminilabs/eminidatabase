"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

export type WebhookFormState =
  | { error?: string; created?: { url: string; secret: string } }
  | undefined;

export async function createWebhookAction(
  organizationId: string,
  _prevState: WebhookFormState,
  formData: FormData
): Promise<WebhookFormState> {
  const url = String(formData.get("url") ?? "");
  const eventTypes = formData.getAll("event_types").map(String);
  const client = await getApiClient();
  try {
    const created = await client.createWebhook(organizationId, url, eventTypes);
    revalidatePath(`/dashboard/${organizationId}/settings/webhooks`);
    return { created: { url: created.url, secret: created.secret } };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
}

export async function deleteWebhookAction(organizationId: string, webhookId: string): Promise<void> {
  const client = await getApiClient();
  await client.deleteWebhook(organizationId, webhookId);
  revalidatePath(`/dashboard/${organizationId}/settings/webhooks`);
}
