/** 合同工具结果结构化渲染 */

import { FileText, Calendar, DollarSign, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ToolResultRendererProps } from './index'

export function ContractResult({ output, toolName }: ToolResultRendererProps) {
  if (toolName === 'get_contract' || toolName === 'create_contract') {
    return <SingleContract data={output as Record<string, unknown>} />
  }

  // 列表
  const raw = output as Record<string, unknown>
  const items: unknown[] = Array.isArray(output) ? output : (Array.isArray(raw?.results) ? raw.results as unknown[] : [])
  if (items.length === 0) {
    return <div className="text-muted-foreground text-xs py-1">未找到合同</div>
  }

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-muted-foreground">共 {items.length} 份合同</div>
      {items.slice(0, 5).map((item, i) => (
        <CompactContract key={i} data={item as Record<string, unknown>} />
      ))}
      {items.length > 5 ? (
        <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 份</div>
      ) : null}
    </div>
  )
}

function SingleContract({ data }: { data: Record<string, unknown> }) {
  const status = String(data.status ?? '')
  const statusVariant = status === 'active' ? 'default' : status === 'expired' ? 'outline' : 'secondary'

  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <FileText className="size-3.5 text-primary" />
        <span>{String(data.title ?? data.name ?? '未命名合同')}</span>
        {status ? <Badge variant={statusVariant} className="text-[10px] px-1 py-0 ml-auto">{statusLabel(status)}</Badge> : null}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {data.contract_number != null ? (
          <div className="flex items-center gap-1"><span>编号:</span><span className="text-foreground">{String(data.contract_number)}</span></div>
        ) : null}
        {data.contract_type != null ? (
          <div className="flex items-center gap-1"><span>类型:</span><span className="text-foreground">{String(data.contract_type)}</span></div>
        ) : null}
        {data.amount != null ? (
          <div className="flex items-center gap-1"><DollarSign className="size-3" /><span>金额:</span><span className="text-foreground">¥{Number(data.amount).toLocaleString()}</span></div>
        ) : null}
        {data.sign_date != null ? (
          <div className="flex items-center gap-1"><Calendar className="size-3" /><span>签订:</span><span className="text-foreground">{String(data.sign_date)}</span></div>
        ) : null}
      </div>
      {Array.isArray(data.parties) && data.parties.length > 0 ? (
        <div className="flex items-start gap-1 text-muted-foreground">
          <Users className="size-3 mt-0.5 shrink-0" />
          <span className="truncate">{(data.parties as Record<string, unknown>[]).map(p => String(p.name ?? '')).join('、')}</span>
        </div>
      ) : null}
    </div>
  )
}

function CompactContract({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <FileText className="size-3 shrink-0 text-muted-foreground" />
      <span className="font-medium truncate flex-1">{String(data.title ?? data.name ?? '未命名')}</span>
      {data.amount != null ? (
        <span className="text-muted-foreground shrink-0">¥{Number(data.amount).toLocaleString()}</span>
      ) : null}
    </div>
  )
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    active: '生效中',
    expired: '已到期',
    draft: '草稿',
    terminated: '已终止',
    pending: '待签署',
  }
  return map[s] ?? s
}
