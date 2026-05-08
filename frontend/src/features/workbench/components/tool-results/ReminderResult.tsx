/** 提醒/财务工具结果结构化渲染 */

import { Bell, Calendar, DollarSign, Clock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { formatAmountInt } from '@/lib/format'
import type { ToolResultRendererProps } from './index'

export function ReminderResult({ output, toolName }: ToolResultRendererProps) {
  // LPR 利率
  if (toolName.includes('lpr_rate') || toolName === 'calculate_interest') {
    return <LprResult output={output} />
  }

  // 财务统计
  if (toolName === 'get_finance_stats') {
    return <FinanceStats data={output as Record<string, unknown>} />
  }

  // 单个提醒
  if (toolName === 'get_reminder' || toolName === 'create_new_reminder' || toolName === 'update_reminder') {
    return <SingleReminder data={output as Record<string, unknown>} />
  }

  // 列表
  const items = extractList(output)
  if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">未找到提醒</div>

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-muted-foreground">共 {items.length} 个提醒</div>
      {items.slice(0, 5).map((item, i) => (
        <CompactReminder key={i} data={item as Record<string, unknown>} />
      ))}
      {items.length > 5 && (
        <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 个</div>
      )}
    </div>
  )
}

function SingleReminder({ data }: { data: Record<string, unknown> }) {
  const priority = String(data.priority ?? '')
  const isUrgent = priority === 'high' || priority === 'urgent'

  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <Bell className={cn('size-3.5', isUrgent ? 'text-destructive' : 'text-primary')} />
        <span>{String(data.title ?? data.name ?? '未命名提醒')}</span>
        {isUrgent && <Badge variant="destructive" className="text-[10px] px-1 py-0">紧急</Badge>}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {data.reminder_type != null && (
          <div className="flex items-center gap-1"><span>类型:</span><span className="text-foreground">{String(data.reminder_type)}</span></div>
        )}
        {data.due_date != null && (
          <div className="flex items-center gap-1"><Calendar className="size-3" /><span>截止:</span><span className="text-foreground">{String(data.due_date)}</span></div>
        )}
        {data.remind_at != null && (
          <div className="flex items-center gap-1"><Clock className="size-3" /><span>提醒:</span><span className="text-foreground">{String(data.remind_at)}</span></div>
        )}
      </div>
    </div>
  )
}

function CompactReminder({ data }: { data: Record<string, unknown> }) {
  const priority = String(data.priority ?? '')
  const isUrgent = priority === 'high' || priority === 'urgent'

  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <Bell className={cn('size-3 shrink-0', isUrgent ? 'text-destructive' : 'text-muted-foreground')} />
      <span className="font-medium truncate flex-1">{String(data.title ?? data.name ?? '未命名')}</span>
      {data.due_date != null && <span className="text-muted-foreground shrink-0">{String(data.due_date)}</span>}
    </div>
  )
}

function LprResult({ output }: { output: unknown }) {
  const data = output as Record<string, unknown>

  // calculate_interest 结果
  if (data.interest != null || data.total != null) {
    return (
      <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1 text-xs">
        <div className="flex items-center gap-1.5 font-medium">
          <DollarSign className="size-3.5 text-primary" />
          <span>利息计算结果</span>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
          {data.principal != null && <div>本金: <span className="text-foreground">{formatAmountInt(Number(data.principal))}</span></div>}
          {data.rate != null && <div>利率: <span className="text-foreground">{String(data.rate)}%</span></div>}
          {data.days != null && <div>天数: <span className="text-foreground">{String(data.days)}</span></div>}
          {data.interest != null && <div>利息: <span className="text-foreground font-medium">{formatAmountInt(Number(data.interest))}</span></div>}
          {data.total != null && <div>合计: <span className="text-foreground font-medium">{formatAmountInt(Number(data.total))}</span></div>}
        </div>
      </div>
    )
  }

  // LPR 利率列表
  const items = extractList(output)
  if (items.length > 0) {
    return (
      <div className="space-y-1">
        <div className="text-[10px] text-muted-foreground">LPR 利率 ({items.length})</div>
        {items.slice(0, 3).map((item, i) => {
          const d = item as Record<string, unknown>
          return (
            <div key={i} className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
              <DollarSign className="size-3 shrink-0 text-muted-foreground" />
              <span>{String(d.term ?? d.type ?? '')}</span>
              <span className="font-medium ml-auto">{String(d.rate ?? '')}%</span>
              {d.date != null && <span className="text-muted-foreground">{String(d.date)}</span>}
            </div>
          )
        })}
      </div>
    )
  }

  return null
}

function FinanceStats({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium mb-1.5">
        <DollarSign className="size-3.5 text-primary" />
        <span>财务统计</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {Object.entries(data).map(([key, val]) => (
          <div key={key}>{key}: <span className="text-foreground">{String(val)}</span></div>
        ))}
      </div>
    </div>
  )
}

function extractList(output: unknown): unknown[] {
  if (Array.isArray(output)) return output
  if (output && typeof output === 'object') {
    const obj = output as Record<string, unknown>
    if (Array.isArray(obj.results)) return obj.results
    if (Array.isArray(obj.data)) return obj.data
    if (Array.isArray(obj.items)) return obj.items
    if (Array.isArray(obj.list)) return obj.list
  }
  return []
}
