import { useNavigate } from 'react-router'
import { Clock, AlertTriangle, CalendarDays } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS } from '@/routes/paths'
import { formatDate } from '@/lib/date'
import type { DashboardStats } from '../types'

export function UpcomingReminders({
  data,
  isLoading,
}: {
  data?: DashboardStats
  isLoading: boolean
}) {
  const navigate = useNavigate()
  const reminders = data?.upcoming_reminders ?? []
  const overdueCount = data?.overdue_count ?? 0
  const todayCount = data?.today_count ?? 0

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-sm font-medium">即将到期提醒</CardTitle>
        {overdueCount > 0 && (
          <Badge variant="destructive" className="text-[10px] gap-1">
            <AlertTriangle className="size-3" />
            {overdueCount} 项逾期
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex-1 pt-0">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : reminders.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <CalendarDays className="size-8 mb-2 opacity-40" />
            <span className="text-xs">暂无待办提醒</span>
          </div>
        ) : (
          <div className="space-y-1.5">
            {reminders.slice(0, 6).map((r) => (
              <div
                key={r.id}
                className={`flex items-center gap-2 rounded-md px-2.5 py-2 text-xs transition-colors ${
                  r.is_overdue
                    ? 'bg-red-50 dark:bg-red-950/30'
                    : 'hover:bg-muted/50'
                }`}
              >
                <Clock
                  className={`size-3.5 shrink-0 ${
                    r.is_overdue ? 'text-red-500' : 'text-muted-foreground'
                  }`}
                />
                <span
                  className={`flex-1 truncate ${
                    r.is_overdue ? 'text-red-700 dark:text-red-400 font-medium' : ''
                  }`}
                >
                  {r.title}
                </span>
                <span
                  className={`shrink-0 tabular-nums ${
                    r.is_overdue ? 'text-red-500' : 'text-muted-foreground'
                  }`}
                >
                  {formatDate(r.due_at)}
                </span>
              </div>
            ))}
            {reminders.length > 6 && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full text-xs h-7 mt-1"
                onClick={() => navigate(PATHS.ADMIN_REMINDERS)}
              >
                查看全部
              </Button>
            )}
          </div>
        )}
        {todayCount > 0 && !isLoading && (
          <div className="mt-3 pt-3 border-t text-xs text-muted-foreground">
            今日有 <span className="font-medium text-foreground">{todayCount}</span> 项提醒
          </div>
        )}
      </CardContent>
    </Card>
  )
}
