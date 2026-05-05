import { cn } from '@/lib/utils'

interface InfoItem {
  label: string
  value?: React.ReactNode
}

interface InfoGridProps {
  items: InfoItem[]
  columns?: 1 | 2 | 3
  className?: string
}

export function InfoGrid({ items, columns = 2, className }: InfoGridProps) {
  const gridCols = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
  }

  return (
    <div className={cn('grid gap-4', gridCols[columns], className)}>
      {items.map((item, i) => (
        <div key={i} className="flex flex-col gap-1.5">
          <label className="text-xs text-muted-foreground">{item.label}</label>
          <div className="px-3 py-2.5 bg-muted/50 border border-border-light rounded-md text-sm text-foreground min-h-[38px] flex items-center">
            {item.value ?? '-'}
          </div>
        </div>
      ))}
    </div>
  )
}
