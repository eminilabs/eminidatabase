"use client";

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
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>Create an organization</CardTitle>
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
              <Input id="slug" name="slug" required placeholder="acme-inc" pattern="[a-z0-9-]+" />
            </div>
            <Button type="submit" disabled={pending} className="w-full">
              {pending ? "Creating…" : "Create organization"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
