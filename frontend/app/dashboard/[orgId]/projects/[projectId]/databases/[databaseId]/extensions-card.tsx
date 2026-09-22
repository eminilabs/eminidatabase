import { Card, CardContent } from "@/components/ui/card";
import { requireApiClient } from "@/lib/api-server";

import { DropExtensionButton } from "./drop-extension-button";
import { InstallExtensionForm } from "./install-extension-form";

export async function ExtensionsCard({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const client = await requireApiClient();
  let extensions: Awaited<ReturnType<typeof client.listExtensions>> = [];
  try {
    extensions = await client.listExtensions(organizationId, projectId, databaseId);
  } catch {
    // Database not running — extensions genuinely unavailable, not an error to surface loudly.
  }

  const installed = extensions.filter((e) => e.installed);

  return (
    <Card>
      <CardContent className="space-y-4">
        <InstallExtensionForm
          organizationId={organizationId}
          projectId={projectId}
          databaseId={databaseId}
        />
        {installed.length === 0 ? (
          <p className="text-sm text-slate-500">No extensions installed.</p>
        ) : (
          <ul className="divide-y divide-slate-800 text-sm">
            {installed.map((ext) => (
              <li key={ext.name} className="flex items-center justify-between py-2">
                <span>
                  {ext.name} {ext.version && <span className="text-slate-500">v{ext.version}</span>}
                </span>
                <DropExtensionButton
                  organizationId={organizationId}
                  projectId={projectId}
                  databaseId={databaseId}
                  name={ext.name}
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
