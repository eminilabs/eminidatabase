"use client";

import QRCode from "qrcode";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { enableMfaAction, verifyMfaAction } from "./actions";

export function MfaSetup() {
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [pending, startTransition] = useTransition();

  function handleEnable() {
    setError(null);
    startTransition(async () => {
      const result = await enableMfaAction();
      if (result.error || !result.provisioningUri) {
        setError(result.error ?? "Something went wrong.");
        return;
      }
      setQrDataUrl(await QRCode.toDataURL(result.provisioningUri));
    });
  }

  function handleVerify(formData: FormData) {
    setError(null);
    const otpCode = String(formData.get("otp_code") ?? "");
    startTransition(async () => {
      const result = await verifyMfaAction(otpCode);
      if (result.error) {
        setError(result.error);
        return;
      }
      setSuccess(true);
    });
  }

  if (success) {
    return <Alert className="border-emerald-900 bg-emerald-950/40 text-emerald-300">MFA is now enabled.</Alert>;
  }

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}

      {!qrDataUrl ? (
        <Button onClick={handleEnable} disabled={pending}>
          {pending ? "Starting…" : "Enable two-factor authentication"}
        </Button>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            Scan this with your authenticator app, then enter the 6-digit code it shows.
          </p>
          {/* eslint-disable-next-line @next/next/no-img-element -- a locally
              generated data: URI, not a remote image Next's optimizer applies to. */}
          <img src={qrDataUrl} alt="MFA QR code" className="h-48 w-48" />
          <form action={handleVerify} className="flex items-end gap-3">
            <div>
              <Label htmlFor="otp_code">Code</Label>
              <Input
                id="otp_code"
                name="otp_code"
                inputMode="numeric"
                placeholder="123456"
                autoFocus
                className="w-40"
              />
            </div>
            <Button type="submit" disabled={pending}>
              {pending ? "Verifying…" : "Verify"}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
