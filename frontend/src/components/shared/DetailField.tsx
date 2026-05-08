export function DetailField({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-muted-foreground mb-0.5 text-xs">{label}</div>
      <div className={`text-[13px] ${mono ? 'font-mono' : ''}`}>{value || '—'}</div>
    </div>
  )
}
