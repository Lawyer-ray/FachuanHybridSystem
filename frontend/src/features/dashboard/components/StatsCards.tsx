import { memo, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Users, FileText, Briefcase, TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { PATHS } from '@/routes/paths'
import { formatAmountInt } from '@/lib/format'
import { Skeleton } from '@/components/ui/skeleton'
import type { DashboardStats } from '../types'

interface StatCard {
  label: string
  value: string
  icon: React.ReactNode
  path: string
  trend?: string
  trendUp?: boolean
}

export const StatsCards = memo(function StatsCards({ data, isLoading }: { data?: DashboardStats; isLoading: boolean }) {
  const navigate = useNavigate()

  const stats: StatCard[] = useMemo(() => [
    {
      label: '当事人总数',
      value: isLoading ? '-' : String(data?.client_count ?? 0),
      icon: <Users className="w-5 h-5" />,
      path: PATHS.ADMIN_CLIENTS,
    },
    {
      label: '合同总数',
      value: isLoading ? '-' : String(data?.contract_count ?? 0),
      icon: <FileText className="w-5 h-5" />,
      path: PATHS.ADMIN_CONTRACTS,
    },
    {
      label: '在办案件',
      value: isLoading ? '-' : String(data?.case_count ?? 0),
      icon: <Briefcase className="w-5 h-5" />,
      path: PATHS.ADMIN_CASES,
    },
    {
      label: '本月律师费',
      value: isLoading ? '-' : formatAmountInt(Number(data?.monthly_fee ?? 0)),
      icon: <TrendingUp className="w-5 h-5" />,
      path: PATHS.ADMIN_CONTRACTS,
    },
  ], [data, isLoading])

  const handleCardClick = useCallback((path: string) => navigate(path), [navigate])

  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card
          key={stat.label}
          className="cursor-pointer hover:shadow-md transition-shadow py-2"
          onClick={() => handleCardClick(stat.path)}
        >
          <CardContent className="py-1.5 px-4">
            <div className="flex items-center justify-between mb-0">
              <span className="text-xs text-muted-foreground">{stat.label}</span>
              <div className="text-muted-foreground opacity-60 [&>svg]:w-4 [&>svg]:h-4">
                {stat.icon}
              </div>
            </div>
            {isLoading ? (
              <Skeleton className="h-6 w-20 mt-1" />
            ) : (
              <div className="text-lg font-semibold">{stat.value}</div>
            )}
            {stat.trend && !isLoading && (
              <div
                className={`flex items-center gap-1 text-xs mt-0.5 ${
                  stat.trendUp ? 'text-green-600' : 'text-red-500'
                }`}
              >
                {stat.trendUp ? (
                  <TrendingUp className="size-3" />
                ) : (
                  <TrendingDown className="size-3" />
                )}
                <span>{stat.trend}</span>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
})
