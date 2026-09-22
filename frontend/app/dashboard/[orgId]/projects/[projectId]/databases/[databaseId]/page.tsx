import { Database as DatabaseIcon, Plug, Table2, Users } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/badge";
import { Table, TableBody, TableRow, Td, Th, TableHead } from "@/components/ui/table";
import { requireApiClient } from "@/lib/api-server";
import { formatRelativeTime } from "@/lib/utils";

import { ConnectionCard } from "./connection-card";
import { InfoSection } from "./info-section";
import { MetricsCard } from "./metrics-card";

export default async function DatabaseOverviewPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await requireApiClient();
  const [database, project, regions] = await Promise.all([
    client.getDatabase(orgId, projectId, databaseId),
    client.getProject(orgId, projectId),
    client.listRegions(),
  ]);
  const region = regions.find((r) => r.id === database.region_id);

  const [tables, roles, extensions] = await Promise.all([
    client.listTables(orgId, projectId, databaseId).catch(() => []),
    client.listRoles(orgId, projectId, databaseId).catch(() => []),
    client.listExtensions(orgId, projectId, databaseId).catch(() => []),
  ]);
  const installedExtensions = extensions.filter((e) => e.installed);

  const base = `/dashboard/${orgId}/projects/${projectId}/databases/${databaseId}`;

  return (
    <div className="flex gap-8">
      <div className="min-w-0 flex-1 space-y-6">
        <Table>
          <TableHead>
            <tr>
              <Th>Service</Th>
              <Th>Description / Details</Th>
            </tr>
          </TableHead>
          <TableBody>
            <TableRow>
              <Td className="p-0">
                <div className="flex items-center gap-2.5 px-4 py-3 font-medium text-slate-100">
                  <DatabaseIcon className="h-4 w-4 text-slate-500" />
                  Postgres database
                </div>
              </Td>
              <Td className="text-slate-400">
                <div className="flex items-center gap-3">
                  <StatusBadge status={database.status} />
                  <span>
                    {database.cpu_limit} vCPU · {database.ram_limit_mb} MB RAM · {database.storage_limit_gb} GB
                  </span>
                </div>
              </Td>
            </TableRow>
            <TableRow>
              <Td className="p-0">
                <Link
                  href={`${base}/tables`}
                  className="flex items-center gap-2.5 px-4 py-3 font-medium text-slate-100"
                >
                  <Table2 className="h-4 w-4 text-slate-500" />
                  Tables
                </Link>
              </Td>
              <Td className="text-slate-400">{tables.length} tables</Td>
            </TableRow>
            <TableRow>
              <Td className="p-0">
                <Link
                  href={`${base}/roles`}
                  className="flex items-center gap-2.5 px-4 py-3 font-medium text-slate-100"
                >
                  <Users className="h-4 w-4 text-slate-500" />
                  Roles
                </Link>
              </Td>
              <Td className="text-slate-400">{roles.length} roles</Td>
            </TableRow>
            <TableRow>
              <Td className="p-0">
                <Link
                  href={`${base}/extensions`}
                  className="flex items-center gap-2.5 px-4 py-3 font-medium text-slate-100"
                >
                  <Plug className="h-4 w-4 text-slate-500" />
                  Extensions
                </Link>
              </Td>
              <Td className="text-slate-400">{installedExtensions.length} installed</Td>
            </TableRow>
          </TableBody>
        </Table>

        <div className="grid gap-6 lg:grid-cols-2">
          <MetricsCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
          <ConnectionCard
            organizationId={orgId}
            projectId={projectId}
            databaseId={databaseId}
            databaseName={database.name}
            roles={roles}
          />
        </div>
      </div>

      <aside className="hidden w-64 shrink-0 space-y-6 border-l border-slate-800 pl-6 lg:block">
        <InfoSection
          title="Database"
          rows={[
            ["Name", database.name],
            ["ID", database.id],
            ["Region", region?.name ?? "—"],
            ["CPU", `${database.cpu_limit} vCPU`],
            ["Memory", `${database.ram_limit_mb} MB`],
            ["Storage", `${database.storage_limit_gb} GB`],
            ["Created", formatRelativeTime(database.created_at)],
          ]}
        />
        <InfoSection
          title="Project"
          rows={[
            ["Name", project.name],
            ["Slug", project.slug],
          ]}
        />
      </aside>
    </div>
  );
}
