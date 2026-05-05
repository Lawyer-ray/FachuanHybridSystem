import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { InfoGrid } from './InfoGrid'
import { cn } from '@/lib/utils'

interface InfoItem {
  label: string
  value?: React.ReactNode
}

interface DetailCardGridProps {
  title: string
  items: InfoItem[]
  columns?: 1 | 2 | 3
  headerRight?: React.ReactNode
  className?: string
}

export function DetailCardGrid({
  title,
  items,
  columns = 2,
  headerRight,
  className,
}: DetailCardGridProps) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {headerRight}
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <InfoGrid items={items} columns={columns} />
      </CardContent>
    </Card>
  )
}
