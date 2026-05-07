import { useDashboardStats } from '@/features/dashboard'
import { StatsCards } from '@/features/dashboard/components/StatsCards'
import { TrendChart } from '@/features/dashboard/components/TrendChart'
import { CaseDistributionChart } from '@/features/dashboard/components/CaseDistributionChart'
import { CalendarCard } from '@/features/dashboard/components/CalendarCard'

export default function DashboardPage() {
  const { data, isLoading } = useDashboardStats()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">仪表盘</h1>
        <p className="text-muted-foreground text-sm mt-1">欢迎回来。以下是今日概览。</p>
      </div>

      <StatsCards data={data} isLoading={isLoading} />

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        <TrendChart data={data} isLoading={isLoading} />
        <CaseDistributionChart data={data} isLoading={isLoading} />
      </div>

      <CalendarCard />
    </div>
  )
}
