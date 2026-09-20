"use client";

import { useState } from "react";

import type { DatabaseConnectionResponse } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ConnectionCard({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const [connection, setConnection] = useState<DatabaseConnectionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function reveal() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/connection`
      );
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "Failed to load connection details");
      }
      setConnection(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connection details");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <Alert>{error}</Alert>}
        {!connection ? (
          <Button onClick={reveal} disabled={loading} variant="outline">
            {loading ? "Loading…" : "Reveal connection details"}
          </Button>
        ) : (
          <div className="space-y-2 text-sm">
            <Field label="Host" value={connection.host} />
            <Field label="Port" value={String(connection.port)} />
            <Field label="Database" value={connection.database} />
            <Field label="Username" value={connection.username} />
            <Field label="Password" value={connection.password} />
            <Field label="Connection string" value={connection.connection_string} mono />
            <Button variant="ghost" onClick={() => setConnection(null)}>
              Hide
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`break-all ${mono ? "font-mono text-xs" : ""}`}>{value}</p>
    </div>
  );
}
