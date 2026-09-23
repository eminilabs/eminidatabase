import { requireApiClient } from "@/lib/api-server";

import { ProjectsView } from "./projects-view";

export default async function ProjectsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const [organization, projects, members, regions, me, subscription, plans] = await Promise.all([
    client.getOrganization(orgId),
    client.listProjects(orgId),
    client.listMembers(orgId),
    client.listRegions(),
    client.me(),
    client.getSubscription(orgId),
    client.listPlans(),
  ]);

  const regionNameById = new Map(regions.map((region) => [region.id, region.name]));
  const plan = plans.find((p) => p.id === subscription.plan_id);
  const quotas = (plan?.quotas ?? {}) as { max_databases?: number; max_storage_gb?: number };
  const myRole = members.find((m) => m.user_id === me.id)?.role ?? null;

  const projectsWithCounts = await Promise.all(
    projects.map(async (project) => {
      const databases = await client.listDatabases(orgId, project.id);
      const regionNames = [...new Set(databases.map((db) => regionNameById.get(db.region_id) ?? "Unknown"))];
      const totalStorageGb = databases.reduce((sum, db) => sum + db.storage_limit_gb, 0);
      const hasFailed = databases.some((db) => db.status === "failed" || db.status === "failing");
      const hasTransitional = databases.some(
        (db) => !["running", "failed", "failing", "deleted"].includes(db.status)
      );

      return {
        id: project.id,
        name: project.name,
        slug: project.slug,
        createdAt: project.created_at,
        databaseCount: databases.length,
        region: regionNames.length === 0 ? "—" : regionNames.length === 1 ? regionNames[0] : "Multiple",
        storageGb: totalStorageGb,
        // Projects have no status of their own — this is a real aggregate of
        // their databases' actual statuses, not a fabricated field.
        health: hasFailed ? ("issue" as const) : hasTransitional ? ("provisioning" as const) : ("healthy" as const),
      };
    })
  );

  const totalDatabases = projectsWithCounts.reduce((sum, p) => sum + p.databaseCount, 0);
  const totalStorageGb = projectsWithCounts.reduce((sum, p) => sum + p.storageGb, 0);

  return (
    <ProjectsView
      organizationId={orgId}
      organizationName={organization.name}
      projects={projectsWithCounts}
      memberCount={members.length}
      myRole={myRole}
      planName={plan?.name ?? null}
      totalDatabases={totalDatabases}
      totalStorageGb={totalStorageGb}
      maxDatabases={quotas.max_databases ?? null}
      maxStorageGb={quotas.max_storage_gb ?? null}
    />
  );
}
