export function InfoSection({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <dl className="space-y-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="break-all text-sm text-slate-200">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
