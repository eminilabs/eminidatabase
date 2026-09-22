import { requireApiClient } from "@/lib/api-server";

import { DatabaseHeader } from "./database-header";

export default async function DatabaseDetailLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await requireApiClient();
  const database = await client.getDatabase(orgId, projectId, databaseId);

  return (
    <div className="space-y-6">
      <DatabaseHeader
        organizationId={orgId}
        projectId={projectId}
        databaseId={databaseId}
        initialDatabase={database}
      />
      {children}
    </div>
  );
}
