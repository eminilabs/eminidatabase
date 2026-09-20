import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { AddMemberForm } from "./add-member-form";
import { RemoveMemberButton } from "./remove-member-button";

export default async function MembersPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await getApiClient();
  const members = await client.listMembers(orgId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <AddMemberForm organizationId={orgId} />
        <ul className="divide-y divide-slate-100 text-sm">
          {members.map((member) => (
            <li key={member.id} className="flex items-center justify-between py-2">
              <div>
                <p className="font-mono text-xs text-slate-500">{member.user_id}</p>
                <p className="text-slate-700">{member.role}</p>
              </div>
              {member.role !== "owner" && (
                <RemoveMemberButton organizationId={orgId} targetUserId={member.user_id} />
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
