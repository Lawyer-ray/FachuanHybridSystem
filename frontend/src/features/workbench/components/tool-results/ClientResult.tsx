/** 客户工具结果结构化渲染 */

import { User, Phone, Mail, MapPin, Briefcase } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ToolResultRendererProps } from './index'

export function ClientResult({ output, toolName }: ToolResultRendererProps) {
  if (toolName === 'get_client' || toolName === 'create_client' || toolName === 'update_client') {
    return <SingleClient data={output as Record<string, unknown>} />
  }

  // property_clue 结果
  if (toolName === 'list_property_clues' || toolName === 'create_property_clue') {
    const items = extractList(output)
    if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">未找到财产线索</div>
    return (
      <div className="space-y-1">
        <div className="text-[10px] text-muted-foreground">共 {items.length} 条线索</div>
        {items.slice(0, 5).map((item, i) => {
          const d = item as Record<string, unknown>
          return (
            <div key={i} className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
              <Briefcase className="size-3 shrink-0 text-muted-foreground" />
              <span className="truncate flex-1">{String(d.description ?? d.clue_type ?? '')}</span>
              {d.value != null ? <span className="text-muted-foreground">¥{String(d.value)}</span> : null}
            </div>
          )
        })}
      </div>
    )
  }

  // 客户列表
  const items = extractList(output)
  if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">未找到客户</div>

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-muted-foreground">共 {items.length} 位客户</div>
      {items.slice(0, 5).map((item, i) => (
        <CompactClient key={i} data={item as Record<string, unknown>} />
      ))}
      {items.length > 5 ? (
        <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 位</div>
      ) : null}
    </div>
  )
}

function SingleClient({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <User className="size-3.5 text-primary" />
        <span>{String(data.name ?? '未命名')}</span>
        {data.client_type != null ? (
          <Badge variant="secondary" className="text-[10px] px-1 py-0">{String(data.client_type)}</Badge>
        ) : null}
      </div>
      <div className="space-y-0.5 text-muted-foreground">
        {data.phone != null ? <div className="flex items-center gap-1"><Phone className="size-3" /><span>{String(data.phone)}</span></div> : null}
        {data.email != null ? <div className="flex items-center gap-1"><Mail className="size-3" /><span>{String(data.email)}</span></div> : null}
        {data.address != null ? <div className="flex items-center gap-1"><MapPin className="size-3" /><span className="truncate">{String(data.address)}</span></div> : null}
      </div>
      {data.notes != null ? (
        <div className="text-muted-foreground truncate">{String(data.notes)}</div>
      ) : null}
    </div>
  )
}

function CompactClient({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <User className="size-3 shrink-0 text-muted-foreground" />
      <span className="font-medium truncate flex-1">{String(data.name ?? '未命名')}</span>
      {data.phone != null ? <span className="text-muted-foreground">{String(data.phone)}</span> : null}
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
