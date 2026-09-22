"use client";

import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { revokeAllSessionsAction } from "./actions";

export function RevokeSessionsButton() {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Sign out of all devices
      </Button>
      <ConfirmDialog
        open={open}
        title="Sign out of all devices?"
        description="This immediately ends every session for your account, including this one — you'll need to sign in again here too."
        confirmLabel="Sign out everywhere"
        pending={pending}
        onConfirm={() => startTransition(() => revokeAllSessionsAction())}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}
