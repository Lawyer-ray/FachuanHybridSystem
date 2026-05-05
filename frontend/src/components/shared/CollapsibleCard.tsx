import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface CollapsibleCardProps {
  title: string
  defaultCollapsed?: boolean
  headerRight?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export function CollapsibleCard({
  title,
  defaultCollapsed = false,
  headerRight,
  children,
  className,
}: CollapsibleCardProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader
        className="flex flex-row items-center justify-between py-3 px-4 cursor-pointer select-none hover:bg-muted/50 transition-colors"
        onClick={() => setCollapsed(!collapsed)}
      >
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="flex items-center gap-2">
          {headerRight}
          <ChevronDown
            className={cn(
              'w-4 h-4 text-muted-foreground transition-transform duration-200',
              collapsed && '-rotate-90'
            )}
          />
        </div>
      </CardHeader>
      {!collapsed && <CardContent className="px-4 pb-4">{children}</CardContent>}
    </Card>
  )
}
