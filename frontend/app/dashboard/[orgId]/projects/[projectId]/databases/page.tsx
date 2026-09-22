import { requireApiClient } from "@/lib/api-server";

import { DatabasesView } from "./databases-view";

export default async function DatabasesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = await params;
  const client = await requireApiClient();
  const [project, databases, regions] = await Promise.all([
    client.getProject(orgId, projectId),
    client.listDatabases(orgId, projectId),
    client.listRegions(),
  ]);

  return (
    <DatabasesView
      organizationId={orgId}
      projectId={projectId}
      projectName={project.name}
      databases={databases}
      regions={regions}
    />
  );
}
