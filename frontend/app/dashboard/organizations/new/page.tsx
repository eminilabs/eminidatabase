"use client";

import { Building2 } from "lucide-react";
import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { createOrganizationAction } from "./actions";

export default function NewOrganizationPage() {
  const [state, action, pending] = useActionState(createOrganizationAction, undefined);

  return (
    <div className="flex justify-center py-8">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600 text-white">
            <Building2 className="h-6 w-6" />
          </span>
          <h1 className="mt-4 text-lg font-semibold text-slate-100">Create your organization</h1>
          <p className="mt-1 text-sm text-slate-500">
            Organizations hold your projects, databases, and billing.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization details</CardTitle>
          </CardHeader>
          <CardContent>
            <form action={action} className="space-y-4">
              {state?.error && <Alert>{state.error}</Alert>}
              <div>
                <Label htmlFor="name">Name</Label>
                <Input id="name" name="name" required placeholder="Acme Inc." />
              </div>
              <div>
                <Label htmlFor="slug">Slug</Label>
                <Input id="slug" name="slug" required placeholder="acme-inc" pattern="[a-z0-9\-]+" />
                <p className="mt-1 text-xs text-slate-500">Lowercase letters, numbers, and hyphens only.</p>
              </div>
              <Button type="submit" disabled={pending} className="w-full">
                {pending ? "Creating…" : "Create organization"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
