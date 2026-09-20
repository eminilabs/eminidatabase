const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

/** Plain full-page navigations, not fetch calls — the browser has to actually
 * leave the app to reach Google/GitHub's consent screen and come back. */
export function OAuthButtons() {
  return (
    <div className="grid grid-cols-2 gap-3">
      <a
        href={`${BACKEND_URL}/api/v1/auth/oauth/google/login`}
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Google
      </a>
      <a
        href={`${BACKEND_URL}/api/v1/auth/oauth/github/login`}
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        GitHub
      </a>
    </div>
  );
}
