"use client";

import type { MembershipRole } from "@eminidatabase/sdk";
import {
  Database as DatabaseIcon,
  FolderKanban,
  HardDrive,
  Plus,
  Search,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { formatRelativeTime } from "@/lib/utils";

import { CreateProjectForm } from "./create-project-form";
import { ProjectCardMenu } from "./project-card-menu";

export type ProjectHealth = "healthy" | "provisioning" | "issue";

export type ProjectListItem = {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
  databaseCount: number;
  region: string;
  storageGb: number;
  health: ProjectHealth;
};

const HEALTH_LABEL: Record<ProjectHealth, string> = {
  healthy: "Healthy",
  provisioning: "Provisioning",
  issue: "Needs attention",
};
const HEALTH_VARIANT: Record<ProjectHealth, "success" | "warning" | "danger"> = {
  healthy: "success",
  provisioning: "warning",
  issue: "danger",
};

function StatCard({
  icon: Icon,
  label,
  value,
  sublabel,
  progress,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  sublabel?: string;
  progress?: number; // 0-100, only rendered when a real quota exists
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
          <Icon className="h-4 w-4 text-slate-600" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <p className="text-2xl font-semibold text-slate-100">{value}</p>
          {sublabel && <span className="text-xs text-slate-500">{sublabel}</span>}
        </div>
        {progress !== undefined && (
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-emerald-500"
              style={{ width: `${Math.min(100, progress)}%` }}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ProjectsView({
  organizationId,
  organizationName,
  projects,
  memberCount,
  myRole,
  planName,
  totalDatabases,
  totalStorageGb,
  maxDatabases,
  maxStorageGb,
}: {
  organizationId: string;
  organizationName: string;
  projects: ProjectListItem[];
  memberCount: number;
  myRole: MembershipRole | null;
  planName: string | null;
  totalDatabases: number;
  totalStorageGb: number;
  maxDatabases: number | null;
  maxStorageGb: number | null;
}) {
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"recent" | "name">("recent");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? projects.filter((p) => p.name.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q))
      : projects;
    return [...list].sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );
  }, [projects, query, sort]);

  function formatStorage(gb: number): string {
    if (gb === 0) return "0 GB";
    return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(gb * 1024).toFixed(0)} MB`;
  }

  return (
    <div className="space-y-6 pb-16">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">{organizationName}&apos;s projects</h1>
        {planName && (
          <Badge variant="success" className="mt-2">
            {planName}
          </Badge>
        )}
      </div>

      {creating ? (
        <Card>
          <CardContent className="py-4">
            <CreateProjectForm organizationId={organizationId} />
          </CardContent>
        </Card>
      ) : (
        <Button onClick={() => setCreating(true)} className="w-full sm:w-auto">
          <Plus className="mr-1.5 h-4 w-4" />
          New project
        </Button>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={FolderKanban} label="Projects" value={projects.length} />
        <StatCard
          icon={DatabaseIcon}
          label="Databases"
          value={totalDatabases}
          sublabel={maxDatabases ? `/ ${maxDatabases}` : undefined}
          progress={maxDatabases ? (totalDatabases / maxDatabases) * 100 : undefined}
        />
        <StatCard
          icon={Users}
          label="Members"
          value={memberCount}
          sublabel={myRole ? `You: ${myRole}` : undefined}
        />
        <StatCard
          icon={HardDrive}
          label="Storage"
          value={formatStorage(totalStorageGb)}
          sublabel={maxStorageGb ? `/ ${maxStorageGb} GB` : undefined}
          progress={maxStorageGb ? (totalStorageGb / maxStorageGb) * 100 : undefined}
        />
      </div>

      {projects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start provisioning databases."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search projects..."
                className="pl-9"
              />
            </div>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as "recent" | "name")}
              className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-200"
            >
              <option value="recent">Sort: Recent</option>
              <option value="name">Sort: Name</option>
            </select>
          </div>

          <div className="space-y-3">
            {filtered.map((project) => (
              <Card key={project.id}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between gap-3">
                    <Link
                      href={`/dashboard/${organizationId}/projects/${project.id}/databases`}
                      className="flex min-w-0 flex-1 items-center gap-3"
                    >
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white">
                        <FolderKanban className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate font-medium text-slate-100">{project.name}</p>
                          <Badge variant={HEALTH_VARIANT[project.health]}>
                            {HEALTH_LABEL[project.health]}
                          </Badge>
                        </div>
                        <p className="truncate font-mono text-xs text-slate-500">{project.slug}</p>
                      </div>
                    </Link>
                    <ProjectCardMenu
                      organizationId={organizationId}
                      projectId={project.id}
                      projectName={project.name}
                    />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300">
                      🌐 {project.region}
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300">
                      <DatabaseIcon className="h-3 w-3" />
                      {project.databaseCount} {project.databaseCount === 1 ? "Database" : "Databases"}
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/60 px-2.5 py-1 text-xs text-slate-300">
                      <HardDrive className="h-3 w-3" />
                      {formatStorage(project.storageGb)}
                    </span>
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3 text-xs">
                    <span className="text-slate-500">Created {formatRelativeTime(project.createdAt)}</span>
                    <Link
                      href={`/dashboard/${organizationId}/projects/${project.id}/databases`}
                      className="font-medium text-emerald-400 hover:text-emerald-300"
                    >
                      Manage console →
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
