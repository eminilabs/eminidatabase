"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";

/**
 * Lands here after backend/app/api/v1/endpoints/auth.py's oauth_callback
 * redirects back from Google/GitHub. On success the token travels in the URL
 * *fragment* (`#access_token=...`) — browsers never send fragments to any
 * server, so only this client-side script ever sees it. It's immediately
 * exchanged for an httpOnly cookie via a same-origin POST, then stripped from
 * the URL. Failures arrive as `?error=` instead (nothing sensitive to
 * protect there) and are shown here, with the user pointed back at
 * password+OTP login for the MFA-blocked case.
 */
export default function OAuthCallbackPage() {
  return (
    <Suspense>
      <OAuthCallbackHandler />
    </Suspense>
  );
}

function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.hash.slice(1)).get("access_token");
}

function OAuthCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Computed during render (lazy initializer), not as a setState-in-effect —
  // reading the fragment is synchronous and has no external system to
  // subscribe to, so it doesn't belong in an effect body.
  const [error, setError] = useState<string | null>(() => {
    const queryError = searchParams.get("error");
    if (queryError) return queryError;
    return readAccessToken()
      ? null
      : "No session token was returned. Please try signing in again.";
  });

  useEffect(() => {
    if (error) return;
    const token = readAccessToken();
    if (!token) return; // already reflected in `error` from the initializer above.

    fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to complete sign-in");
        router.replace("/dashboard");
      })
      .catch(() => setError("Failed to complete sign-in. Please try again."));
  }, [error, router]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-4 text-center">
        {error ? (
          <>
            <Alert>{error}</Alert>
            <a href="/login" className="text-sm font-medium text-slate-900 underline">
              Back to sign in
            </a>
          </>
        ) : (
          <p className="text-sm text-slate-500">Signing you in…</p>
        )}
      </div>
    </div>
  );
}
