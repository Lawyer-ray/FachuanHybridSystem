import { cn } from '@/lib/utils'

interface TimelineItem {
  id: string | number
  date: string
  title: string
  description?: string
  icon?: React.ReactNode
  badge?: React.ReactNode
}

interface TimelineGroup {
  date: string
  items: TimelineItem[]
}

interface TimelineProps {
  groups: TimelineGroup[]
  className?: string
}

export function Timeline({ groups, className }: TimelineProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {groups.map((group) => (
        <div key={group.date}>
          <div className="text-xs font-medium text-muted-foreground mb-3 sticky top-0 bg-background py-1">
            {group.date}
          </div>
          <div className="relative pl-6 border-l border-border space-y-4">
            {group.items.map((item) => (
              <div key={item.id} className="relative">
                <div className="absolute -left-[25px] top-1 w-2 h-2 rounded-full bg-foreground" />
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {item.icon}
                      <span className="text-sm font-medium">{item.title}</span>
                      {item.badge}
                    </div>
                    {item.description && (
                      <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
