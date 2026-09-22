import type { ReactNode } from "react";

/** Stylized cluster illustration — three database nodes wired together, one
 * elevated as primary — built as inline SVG rather than a raster asset so it
 * stays crisp at any size and needs no image hosting. */
function ClusterIllustration() {
  return (
    <svg viewBox="0 0 400 340" className="w-full max-w-md" aria-hidden="true">
      <defs>
        <linearGradient id="node-glow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#059669" stopOpacity="0.6" />
        </linearGradient>
        <radialGradient id="halo" cx="50%" cy="35%" r="65%">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
        </radialGradient>
      </defs>

      <circle cx="200" cy="140" r="180" fill="url(#halo)" />

      {/* connections */}
      <path
        d="M200 110 L100 220 M200 110 L300 220 M100 220 L300 220"
        stroke="#334155"
        strokeWidth="2"
        fill="none"
      />
      <circle cx="150" cy="165" r="3" fill="#10b981">
        <animate attributeName="opacity" values="0.2;1;0.2" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <circle cx="250" cy="165" r="3" fill="#10b981">
        <animate
          attributeName="opacity"
          values="0.2;1;0.2"
          dur="2.4s"
          begin="0.8s"
          repeatCount="indefinite"
        />
      </circle>
      <circle cx="200" cy="220" r="3" fill="#10b981">
        <animate
          attributeName="opacity"
          values="0.2;1;0.2"
          dur="2.4s"
          begin="1.6s"
          repeatCount="indefinite"
        />
      </circle>

      {/* primary node (top) */}
      <g transform="translate(160, 60)">
        <ellipse cx="40" cy="10" rx="40" ry="12" fill="url(#node-glow)" />
        <path d="M0 10 L0 42 A40 12 0 0 0 80 42 L80 10" fill="#064e3b" stroke="#10b981" strokeWidth="1.5" />
        <ellipse cx="40" cy="42" rx="40" ry="12" fill="#065f46" stroke="#10b981" strokeWidth="1.5" />
      </g>

      {/* replica nodes (bottom) */}
      <g transform="translate(60, 190)">
        <ellipse cx="32" cy="8" rx="32" ry="9" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
        <path d="M0 8 L0 34 A32 9 0 0 0 64 34 L64 8" fill="#0f172a" stroke="#475569" strokeWidth="1.5" />
        <ellipse cx="32" cy="34" rx="32" ry="9" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
      </g>
      <g transform="translate(240, 190)">
        <ellipse cx="32" cy="8" rx="32" ry="9" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
        <path d="M0 8 L0 34 A32 9 0 0 0 64 34 L64 8" fill="#0f172a" stroke="#475569" strokeWidth="1.5" />
        <ellipse cx="32" cy="34" rx="32" ry="9" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
      </g>
    </svg>
  );
}

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <div className="flex w-full items-center justify-center px-4 py-12 lg:w-1/2">{children}</div>

      <div className="relative hidden overflow-hidden bg-slate-950 lg:flex lg:w-1/2 lg:items-center lg:justify-center">
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="relative flex flex-col items-center gap-8 px-12 text-center">
          <ClusterIllustration />
          <div className="max-w-sm space-y-2">
            <h2 className="text-xl font-semibold text-slate-100">
              Postgres databases, provisioned in seconds
            </h2>
            <p className="text-sm text-slate-400">
              Branch, back up, and scale your databases from one dashboard — built for teams that
              ship fast.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
