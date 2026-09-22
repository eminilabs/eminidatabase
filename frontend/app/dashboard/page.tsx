import { redirect } from "next/navigation";

import { requireApiClient } from "@/lib/api-server";

export default async function DashboardIndexPage() {
  const client = await requireApiClient();
  const organizations = await client.listOrganizations();

  if (organizations.length === 0) {
    redirect("/dashboard/organizations/new");
  }
  redirect(`/dashboard/${organizations[0].id}/projects`);
}
