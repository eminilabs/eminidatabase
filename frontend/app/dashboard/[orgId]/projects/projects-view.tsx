"use client";

import { Database as DatabaseIcon, FolderKanban, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableRow, Td, Th, TableHead } from "@/components/ui/table";
import { formatRelativeTime } from "@/lib/utils";

import { CreateProjectForm } from "./create-project-form";

export type ProjectListItem = {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
  databaseCount: number;
  region: string;
  storageGb: number;
};

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-100">{value}</p>
    </div>
  );
}

function formatStorage(gb: number): string {
  if (gb === 0) return "—";
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(gb * 1024).toFixed(0)} MB`;
}

export function ProjectsView({
  organizationId,
  organizationName,
  projects,
  memberCount,
}: {
  organizationId: string;
  organizationName: string;
  projects: ProjectListItem[];
  memberCount: number;
}) {
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");

  const totalDatabases = projects.reduce((sum, p) => sum + p.databaseCount, 0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => p.name.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q));
  }, [projects, query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-xl font-semibold text-slate-100">{organizationName}&apos;s projects</h1>
        <Button onClick={() => setCreating((v) => !v)}>
          <Plus className="mr-1.5 h-4 w-4" />
          New project
        </Button>
      </div>

      {creating && (
        <Card>
          <CardContent className="py-4">
            <CreateProjectForm organizationId={organizationId} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid grid-cols-3 gap-6 py-5">
          <StatBox label="Projects" value={projects.length} />
          <StatBox label="Databases" value={totalDatabases} />
          <StatBox label="Members" value={memberCount} />
        </CardContent>
      </Card>

      <div>
        <p className="mb-3 text-sm font-medium text-slate-300">
          {projects.length} {projects.length === 1 ? "Project" : "Projects"}
        </p>

        {projects.length === 0 ? (
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description="Create your first project to start provisioning databases."
          />
        ) : (
          <>
            <div className="relative mb-3">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search projects..."
                className="pl-9"
              />
            </div>

            <Table>
              <TableHead>
                <tr>
                  <Th>Name</Th>
                  <Th>Region</Th>
                  <Th>Databases</Th>
                  <Th>Storage</Th>
                  <Th>Created at</Th>
                </tr>
              </TableHead>
              <TableBody>
                {filtered.map((project) => (
                  <TableRow key={project.id}>
                    <Td className="p-0">
                      <Link
                        href={`/dashboard/${organizationId}/projects/${project.id}/databases`}
                        className="flex items-center gap-2.5 px-4 py-3"
                      >
                        <FolderKanban className="h-4 w-4 shrink-0 text-slate-500" />
                        <div>
                          <p className="font-medium text-slate-100">{project.name}</p>
                          <p className="font-mono text-xs text-slate-500">{project.slug}</p>
                        </div>
                      </Link>
                    </Td>
                    <Td className="text-slate-400">{project.region}</Td>
                    <Td>
                      <span className="inline-flex items-center gap-1.5 text-slate-400">
                        <DatabaseIcon className="h-3.5 w-3.5" />
                        {project.databaseCount}
                      </span>
                    </Td>
                    <Td className="text-slate-400">{formatStorage(project.storageGb)}</Td>
                    <Td className="text-slate-500">{formatRelativeTime(project.createdAt)}</Td>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </div>
    </div>
  );
}
