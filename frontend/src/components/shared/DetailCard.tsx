export function DetailCard({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
      {extra ? (
        <div className="flex items-center justify-between mb-3.5">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {extra}
        </div>
      ) : (
        <h3 className="text-sm font-semibold text-foreground mb-3.5">{title}</h3>
      )}
      {children}
    </div>
  )
}
