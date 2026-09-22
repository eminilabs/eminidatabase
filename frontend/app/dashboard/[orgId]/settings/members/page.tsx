import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { AddMemberForm } from "./add-member-form";
import { RemoveMemberButton } from "./remove-member-button";

export default async function MembersPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const members = await client.listMembers(orgId);

  return (
    <div className="space-y-6">
      <PageHeader title="Members" description="People with access to this organization." />

      <Card>
        <CardContent className="py-4">
          <AddMemberForm organizationId={orgId} />
        </CardContent>
      </Card>

      <Card>
        <ul className="divide-y divide-slate-800 text-sm">
          {members.map((member) => (
            <li key={member.id} className="flex items-center justify-between px-6 py-3">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-slate-500">
                  <Users className="h-4 w-4" />
                </span>
                <div>
                  <p className="font-mono text-xs text-slate-500">{member.user_id}</p>
                  <Badge variant={member.role === "owner" ? "default" : "neutral"} className="mt-1">
                    {member.role}
                  </Badge>
                </div>
              </div>
              {member.role !== "owner" && (
                <RemoveMemberButton organizationId={orgId} targetUserId={member.user_id} />
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
