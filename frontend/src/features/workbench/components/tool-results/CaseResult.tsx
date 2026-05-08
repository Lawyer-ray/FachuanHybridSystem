/** 案件工具结果结构化渲染 */

import { Briefcase, Users, Hash, Calendar, DollarSign } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { formatShortDate } from '@/lib/date'
import type { ToolResultRendererProps } from './index'

interface StatusInfo {
  label: string
  variant: 'default' | 'secondary' | 'destructive' | 'outline'
}

const STATUS_MAP: Record<string, StatusInfo> = {
  active: { label: '进行中', variant: 'default' },
  pending: { label: '待处理', variant: 'secondary' },
  closed: { label: '已结案', variant: 'outline' },
  archived: { label: '已归档', variant: 'outline' },
}

const TYPE_MAP: Record<string, string> = {
  litigation: '诉讼',
  non_litigation: '非诉',
  criminal: '刑事',
  advisory: '顾问',
}

export function CaseResult({ output, toolName }: ToolResultRendererProps) {
  // 单个案件详情
  if (toolName === 'get_case' || toolName === 'create_case') {
    return <SingleCase data={output as Record<string, unknown>} />
  }

  // 列表结果
  const raw = output as Record<string, unknown>
  const items: unknown[] = Array.isArray(output) ? output : (Array.isArray(raw?.results) ? raw.results as unknown[] : [])
  if (items.length === 0) {
    return <div className="text-muted-foreground text-xs py-1">未找到案件</div>
  }

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-muted-foreground">共 {items.length} 个案件</div>
      {items.slice(0, 5).map((item, i) => (
        <CompactCase key={i} data={item as Record<string, unknown>} />
      ))}
      {items.length > 5 && (
        <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 个</div>
      )}
    </div>
  )
}

function SingleCase({ data }: { data: Record<string, unknown> }) {
  const status = String(data.status ?? '')
  const statusInfo = STATUS_MAP[status]

  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <Briefcase className="size-3.5 text-primary" />
        <span>{String(data.name ?? '未命名案件')}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {data.case_type != null && (
          <Row icon={Hash} label="类型" value={TYPE_MAP[String(data.case_type)] ?? String(data.case_type)} />
        )}
        {data.case_number != null && <Row icon={Hash} label="案号" value={String(data.case_number)} />}
        {statusInfo && (
          <div className="flex items-center gap-1">
            <span>状态</span>
            <Badge variant={statusInfo.variant} className="text-[10px] px-1 py-0">{statusInfo.label}</Badge>
          </div>
        )}
        {data.target_amount != null && (
          <Row icon={DollarSign} label="标的额" value={`¥${Number(data.target_amount).toLocaleString()}`} />
        )}
        {data.created_at != null && (
          <Row icon={Calendar} label="创建" value={formatShortDate(String(data.created_at))} />
        )}
      </div>
      {Array.isArray(data.parties) && data.parties.length > 0 && (
        <div className="flex items-start gap-1 text-muted-foreground">
          <Users className="size-3 mt-0.5 shrink-0" />
          <span className="truncate">{(data.parties as Record<string, unknown>[]).map(p => String(p.name ?? '')).join('、')}</span>
        </div>
      )}
    </div>
  )
}

function CompactCase({ data }: { data: Record<string, unknown> }) {
  const status = String(data.status ?? '')
  const statusInfo = STATUS_MAP[status]

  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <Briefcase className="size-3 shrink-0 text-muted-foreground" />
      <span className="font-medium truncate flex-1">{String(data.name ?? '未命名')}</span>
      {data.case_number != null && (
        <span className="text-muted-foreground truncate max-w-[140px]">{String(data.case_number)}</span>
      )}
      {statusInfo && (
        <Badge variant={statusInfo.variant} className="text-[10px] px-1 py-0 shrink-0">{statusInfo.label}</Badge>
      )}
    </div>
  )
}

function Row({ icon: Icon, label, value }: { icon: typeof Briefcase; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1">
      <Icon className="size-3 shrink-0" />
      <span>{label}:</span>
      <span className="text-foreground">{value}</span>
    </div>
  )
}
