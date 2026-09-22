"use client";

import { useQuery } from "@tanstack/react-query";
import type { DatabaseConnectionResponse, RoleResponse } from "@eminidatabase/sdk";
import { Copy, Eye, EyeOff, Zap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";

async function fetchConnection(
  organizationId: string,
  projectId: string,
  databaseId: string,
  credentialId: string
): Promise<DatabaseConnectionResponse> {
  const res = await fetch(
    `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/connection?credential_id=${encodeURIComponent(credentialId)}`
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "Failed to load connection details");
  }
  return res.json();
}

export function ConnectionCard({
  organizationId,
  projectId,
  databaseId,
  databaseName,
  roles,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  databaseName: string;
  roles: RoleResponse[];
}) {
  const [open, setOpen] = useState(false);
  const primaryRole = roles.find((r) => r.is_primary) ?? roles[0];
  const [roleId, setRoleId] = useState<string | undefined>(primaryRole?.id);
  const [showPassword, setShowPassword] = useState(false);
  const [copied, setCopied] = useState(false);

  const activeRoleId = roleId ?? primaryRole?.id;

  const { data: connection, error } = useQuery({
    queryKey: ["connection", databaseId, activeRoleId],
    enabled: open && !!activeRoleId,
    queryFn: () => fetchConnection(organizationId, projectId, databaseId, activeRoleId as string),
  });

  function maskPassword(connectionString: string, password: string): string {
    if (!password) return connectionString;
    return connectionString.replace(password, "•".repeat(Math.min(password.length, 16)));
  }

  async function copy() {
    if (!connection) return;
    await navigator.clipboard.writeText(connection.connection_string);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connection</CardTitle>
      </CardHeader>
      <CardContent>
        <Button onClick={() => setOpen(true)} disabled={roles.length === 0}>
          <Zap className="mr-1.5 h-4 w-4" />
          Connect
        </Button>
        {roles.length === 0 && (
          <p className="mt-2 text-xs text-slate-500">No roles available yet.</p>
        )}
      </CardContent>

      <Modal open={open} title={`Connection details for ${databaseName}`} onClose={() => setOpen(false)}>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Database</Label>
              <p className="flex h-10 items-center rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-200">
                {databaseName}
              </p>
            </div>
            <div>
              <Label htmlFor="connection-role">Role</Label>
              <select
                id="connection-role"
                value={activeRoleId}
                onChange={(e) => setRoleId(e.target.value)}
                className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-200"
              >
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name ?? role.role_name}
                    {role.is_primary ? " (primary)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <Label className="mb-0">Connection string</Label>
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-100"
              >
                {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                {showPassword ? "Hide password" : "Show password"}
              </button>
            </div>
            {error ? (
              <p className="text-sm text-red-400">{error instanceof Error ? error.message : "Failed to load"}</p>
            ) : !connection ? (
              <p className="text-sm text-slate-500">Loading…</p>
            ) : (
              <div className="rounded-md border border-slate-700 bg-slate-950 p-3">
                <p className="break-all font-mono text-xs text-slate-300">
                  {showPassword
                    ? connection.connection_string
                    : maskPassword(connection.connection_string, connection.password)}
                </p>
              </div>
            )}
          </div>

          <Button variant="outline" onClick={copy} disabled={!connection}>
            <Copy className="mr-1.5 h-4 w-4" />
            {copied ? "Copied!" : "Copy"}
          </Button>
        </div>
      </Modal>
    </Card>
  );
}
