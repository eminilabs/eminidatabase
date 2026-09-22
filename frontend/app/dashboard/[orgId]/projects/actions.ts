"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getApiClient } from "@/lib/api-server";

export type ProjectFormState = { error?: string } | undefined;

export async function createProjectAction(
  organizationId: string,
  _prevState: ProjectFormState,
  formData: FormData
): Promise<ProjectFormState> {
  const name = String(formData.get("name") ?? "");
  const slug = String(formData.get("slug") ?? "");

  const client = await getApiClient();
  try {
    await client.createProject(organizationId, name, slug);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }

  revalidatePath(`/dashboard/${organizationId}/projects`);
  return undefined;
}

export type DeleteProjectState = { error?: string } | undefined;

export async function deleteProjectAction(
  organizationId: string,
  projectId: string
): Promise<DeleteProjectState> {
  const client = await getApiClient();
  try {
    await client.deleteProject(organizationId, projectId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(`/dashboard/${organizationId}/projects`);
  redirect(`/dashboard/${organizationId}/projects`);
}
