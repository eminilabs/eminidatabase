import { redirect } from "next/navigation";

import { getApiClient } from "@/lib/api-server";

export default async function DashboardIndexPage() {
  const client = await getApiClient();
  const organizations = await client.listOrganizations();

  if (organizations.length === 0) {
    redirect("/dashboard/organizations/new");
  }
  redirect(`/dashboard/${organizations[0].id}/projects`);
}
