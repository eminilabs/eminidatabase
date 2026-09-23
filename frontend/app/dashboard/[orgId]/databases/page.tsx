import { requireApiClient } from "@/lib/api-server";

import { OrgDatabasesView } from "./org-databases-view";

export default async function OrgDatabasesPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const projects = await client.listProjects(orgId);

  const databasesByProject = await Promise.all(
    projects.map(async (project) => ({
      project,
      databases: await client.listDatabases(orgId, project.id),
    }))
  );

  const rows = databasesByProject.flatMap(({ project, databases }) =>
    databases.map((database) => ({ project, database }))
  );

  return <OrgDatabasesView organizationId={orgId} rows={rows} />;
}
