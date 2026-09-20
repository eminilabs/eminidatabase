import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { CreateRoleForm } from "./create-role-form";
import { RoleRowActions } from "./role-row-actions";

export async function RolesCard({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const client = await getApiClient();
  const roles = await client.listRoles(organizationId, projectId, databaseId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Roles</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <CreateRoleForm organizationId={organizationId} projectId={projectId} databaseId={databaseId} />
        <ul className="divide-y divide-slate-100 text-sm">
          {roles.map((role) => (
            <li key={role.id} className="flex items-center justify-between py-2">
              <div>
                <span className="font-medium text-slate-900">{role.name ?? role.role_name}</span>{" "}
                <span className="text-slate-400">
                  ({role.scope}
                  {role.is_primary ? ", primary" : ""})
                </span>
              </div>
              <RoleRowActions
                organizationId={organizationId}
                projectId={projectId}
                databaseId={databaseId}
                credentialId={role.id}
                isPrimary={role.is_primary}
              />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
