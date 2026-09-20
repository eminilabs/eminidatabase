import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { CreateProjectForm } from "./create-project-form";

export default async function ProjectsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await getApiClient();
  const projects = await client.listProjects(orgId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Projects</h1>
        <p className="text-sm text-slate-500">Databases are organized under projects.</p>
      </div>

      <Card>
        <CardContent className="py-4">
          <CreateProjectForm organizationId={orgId} />
        </CardContent>
      </Card>

      {projects.length === 0 ? (
        <p className="text-sm text-slate-500">No projects yet — create one above.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link key={project.id} href={`/dashboard/${orgId}/projects/${project.id}/databases`}>
              <Card className="transition-shadow hover:shadow-md">
                <CardContent className="py-4">
                  <p className="font-medium text-slate-900">{project.name}</p>
                  <p className="text-sm text-slate-500">{project.slug}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
