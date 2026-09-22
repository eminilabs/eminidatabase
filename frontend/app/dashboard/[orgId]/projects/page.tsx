import { requireApiClient } from "@/lib/api-server";

import { ProjectsView } from "./projects-view";

export default async function ProjectsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const [organization, projects, members, regions] = await Promise.all([
    client.getOrganization(orgId),
    client.listProjects(orgId),
    client.listMembers(orgId),
    client.listRegions(),
  ]);

  const regionNameById = new Map(regions.map((region) => [region.id, region.name]));

  const projectsWithCounts = await Promise.all(
    projects.map(async (project) => {
      const databases = await client.listDatabases(orgId, project.id);
      const regionNames = [...new Set(databases.map((db) => regionNameById.get(db.region_id) ?? "Unknown"))];
      const totalStorageGb = databases.reduce((sum, db) => sum + db.storage_limit_gb, 0);

      return {
        id: project.id,
        name: project.name,
        slug: project.slug,
        createdAt: project.created_at,
        databaseCount: databases.length,
        region: regionNames.length === 0 ? "—" : regionNames.length === 1 ? regionNames[0] : "Multiple",
        storageGb: totalStorageGb,
      };
    })
  );

  return (
    <ProjectsView
      organizationId={orgId}
      organizationName={organization.name}
      projects={projectsWithCounts}
      memberCount={members.length}
    />
  );
}
