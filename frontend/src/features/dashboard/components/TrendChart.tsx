import { memo, useMemo, useState } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import type { DashboardStats } from '../types'

type TrendKey = 'case' | 'contract' | 'fee'

const TAB_CONFIG: { key: TrendKey; label: string }[] = [
  { key: 'case', label: '案件' },
  { key: 'contract', label: '合同' },
  { key: 'fee', label: '收入' },
]

export const TrendChart = memo(function TrendChart({ data, isLoading }: { data?: DashboardStats; isLoading: boolean }) {
  const [activeTab, setActiveTab] = useState<TrendKey>('case')

  const trendData = useMemo(
    () => activeTab === 'case'
      ? data?.case_trend ?? []
      : activeTab === 'contract'
        ? data?.contract_trend ?? []
        : data?.fee_trend ?? [],
    [activeTab, data?.case_trend, data?.contract_trend, data?.fee_trend],
  )

  const dataKey = activeTab === 'fee' ? 'amount' : 'count'
  const yLabel = activeTab === 'fee' ? '金额' : '数量'

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">趋势</CardTitle>
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as TrendKey)}
        >
          <TabsList className="h-7">
            {TAB_CONFIG.map((t) => (
              <TabsTrigger key={t.key} value={t.key} className="text-xs px-2.5 h-5">
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <Skeleton className="h-[240px] w-full" />
        ) : trendData.length === 0 ? (
          <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
            暂无数据
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={trendData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/50" />
              <XAxis
                dataKey="month"
                className="text-xs"
                tick={{ fill: 'hsl(var(--muted-foreground))' }}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
              />
              <YAxis
                className="text-xs"
                tick={{ fill: 'hsl(var(--muted-foreground))' }}
                tickLine={false}
                axisLine={false}
                width={45}
                tickMargin={4}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                  fontSize: '12px',
                }}
                labelStyle={{ color: 'hsl(var(--foreground))' }}
              />
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                fill="url(#colorValue)"
                name={yLabel}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
})
