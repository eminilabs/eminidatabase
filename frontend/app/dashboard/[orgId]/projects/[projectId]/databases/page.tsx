import { Card, CardContent } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { CreateDatabaseForm } from "./create-database-form";
import { DatabaseRow } from "./database-row";

export default async function DatabasesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = await params;
  const client = await getApiClient();
  const [databases, regions] = await Promise.all([
    client.listDatabases(orgId, projectId),
    client.listRegions(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Databases</h1>
      </div>

      <Card>
        <CardContent className="py-4">
          <CreateDatabaseForm organizationId={orgId} projectId={projectId} regions={regions} />
        </CardContent>
      </Card>

      {databases.length === 0 ? (
        <p className="text-sm text-slate-500">No databases yet — create one above.</p>
      ) : (
        <div className="space-y-3">
          {databases.map((database) => (
            <DatabaseRow
              key={database.id}
              organizationId={orgId}
              projectId={projectId}
              initialDatabase={database}
            />
          ))}
        </div>
      )}
    </div>
  );
}
