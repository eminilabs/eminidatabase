"use server";

import { ApiError } from "@eminidatabase/sdk";
import { redirect } from "next/navigation";

import { getApiClient } from "@/lib/api-server";

export type OrgFormState = { error?: string } | undefined;

export async function createOrganizationAction(
  _prevState: OrgFormState,
  formData: FormData
): Promise<OrgFormState> {
  const name = String(formData.get("name") ?? "");
  const slug = String(formData.get("slug") ?? "");

  const client = await getApiClient();
  let organization;
  try {
    organization = await client.createOrganization(name, slug);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }

  redirect(`/dashboard/${organization.id}/projects`);
}
