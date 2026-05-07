/** 工作台空状态欢迎页面 */

import { Bot, Plus, Loader2, Clock, Briefcase, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useDashboardStats } from '@/features/dashboard'
import { useWorkbenchStore } from '../stores/workbench-store'
import { SuggestedPrompts } from './SuggestedPrompts'
import { formatDate } from '@/lib/date'

interface WorkbenchWelcomeProps {
  onCreateSession: () => void
  isCreating: boolean
  onSelectPrompt: (prompt: string) => void
}

export function WorkbenchWelcome({ onCreateSession, isCreating, onSelectPrompt }: WorkbenchWelcomeProps) {
  const sessions = useWorkbenchStore((s) => s.sessions)
  const { data: stats, isLoading: statsLoading } = useDashboardStats()

  const recentSessions = sessions.slice(0, 3)

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-2xl px-4 py-8 space-y-6">
        {/* 欢迎标题 */}
        <div className="text-center space-y-2">
          <Bot className="mx-auto size-10 text-primary/60" />
          <h2 className="text-lg font-semibold">欢迎使用法穿工作台</h2>
          <p className="text-sm text-muted-foreground">AI 驱动的法律事务助手，帮你高效处理案件、合同和法律检索</p>
          <Button onClick={onCreateSession} disabled={isCreating} className="mt-2">
            {isCreating ? (
              <Loader2 className="size-4 animate-spin mr-2" />
            ) : (
              <Plus className="size-4 mr-2" />
            )}
            新建会话
          </Button>
        </div>

        {/* 今日概览 */}
        <div className="grid grid-cols-3 gap-3">
          <Card className="py-2">
            <CardContent className="px-3 py-1.5 text-center">
              {statsLoading ? (
                <Skeleton className="h-5 w-8 mx-auto" />
              ) : (
                <div className="text-lg font-semibold">{stats?.today_count ?? 0}</div>
              )}
              <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1">
                <Clock className="size-3" />
                今日提醒
              </div>
            </CardContent>
          </Card>
          <Card className="py-2">
            <CardContent className="px-3 py-1.5 text-center">
              {statsLoading ? (
                <Skeleton className="h-5 w-8 mx-auto" />
              ) : (
                <div className="text-lg font-semibold">{stats?.case_count ?? 0}</div>
              )}
              <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1">
                <Briefcase className="size-3" />
                在办案件
              </div>
            </CardContent>
          </Card>
          <Card className="py-2">
            <CardContent className="px-3 py-1.5 text-center">
              {statsLoading ? (
                <Skeleton className="h-5 w-8 mx-auto" />
              ) : (
                <div className="text-lg font-semibold">
                  ¥{Number(stats?.monthly_fee ?? 0).toLocaleString()}
                </div>
              )}
              <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1">
                <TrendingUp className="size-3" />
                本月收入
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 最近会话 */}
        {recentSessions.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-muted-foreground">最近会话</h3>
            <div className="space-y-1">
              {recentSessions.map((session) => (
                <div
                  key={session.id}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-xs hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <Clock className="size-3.5 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate font-medium">{session.title || '新会话'}</span>
                  <span className="text-muted-foreground shrink-0">
                    {formatDate(session.updated_at)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 快速开始 */}
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-muted-foreground">快速开始</h3>
          <SuggestedPrompts onSelect={onSelectPrompt} />
        </div>
      </div>
    </div>
  )
}
