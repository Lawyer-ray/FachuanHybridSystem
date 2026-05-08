/** 企业数据工具结果结构化渲染 */

import { Building2, User, MapPin, Shield, TrendingUp, Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ToolResultRendererProps } from './index'

export function CompanyResult({ output, toolName }: ToolResultRendererProps) {
  // 企业详情
  if (toolName === 'get_company_profile') {
    return <CompanyProfile data={output as Record<string, unknown>} />
  }

  // 企业搜索
  if (toolName === 'search_companies') {
    const items = extractList(output)
    if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">未找到企业</div>
    return (
      <div className="space-y-1.5">
        <div className="text-[10px] text-muted-foreground">共 {items.length} 家企业</div>
        {items.slice(0, 5).map((item, i) => (
          <CompactCompany key={i} data={item as Record<string, unknown>} />
        ))}
        {items.length > 5 && (
          <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 家</div>
        )}
      </div>
    )
  }

  // 股东信息
  if (toolName === 'get_company_shareholders') {
    return <SimpleList output={output} icon={User} label="股东" nameKey="name" />
  }

  // 人员信息
  if (toolName === 'get_company_personnel') {
    return <SimpleList output={output} icon={User} label="主要人员" nameKey="name" />
  }

  // 风险信息
  if (toolName === 'get_company_risks') {
    return <RiskList output={output} />
  }

  // 招投标
  if (toolName === 'search_bidding_info') {
    return <SimpleList output={output} icon={Search} label="招投标" nameKey="title" />
  }

  return null
}

function CompanyProfile({ data }: { data: Record<string, unknown> }) {
  const status = String(data.status ?? data.operating_status ?? '')
  const isActive = status.includes('存续') || status.includes('在业') || status.includes('开业')

  return (
    <div className="rounded-md border border-border/60 bg-background p-2.5 space-y-1.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <Building2 className="size-3.5 text-primary" />
        <span>{String(data.name ?? data.company_name ?? '未知企业')}</span>
        {status ? (
          <Badge variant={isActive ? 'default' : 'secondary'} className="text-[10px] px-1 py-0 ml-auto">
            {status}
          </Badge>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
        {data.legal_person != null ? (
          <div className="flex items-center gap-1"><User className="size-3" /><span>法人:</span><span className="text-foreground">{String(data.legal_person)}</span></div>
        ) : null}
        {data.registered_capital != null ? (
          <div className="flex items-center gap-1"><TrendingUp className="size-3" /><span>注册资本:</span><span className="text-foreground">{String(data.registered_capital)}</span></div>
        ) : null}
        {data.establishment_date != null ? (
          <div className="flex items-center gap-1"><span>成立:</span><span className="text-foreground">{String(data.establishment_date)}</span></div>
        ) : null}
        {data.industry != null ? (
          <div className="flex items-center gap-1"><span>行业:</span><span className="text-foreground">{String(data.industry)}</span></div>
        ) : null}
      </div>
      {data.address != null ? (
        <div className="flex items-start gap-1 text-muted-foreground">
          <MapPin className="size-3 mt-0.5 shrink-0" />
          <span className="truncate">{String(data.address)}</span>
        </div>
      ) : null}
      {data.risk_summary != null ? (
        <div className="flex items-center gap-1 text-muted-foreground">
          <Shield className="size-3 shrink-0" />
          <span className="truncate">{String(data.risk_summary)}</span>
        </div>
      ) : null}
    </div>
  )
}

function CompactCompany({ data }: { data: Record<string, unknown> }) {
  const name = String(data.name ?? data.company_name ?? '未知')
  const status = String(data.status ?? data.operating_status ?? '')

  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <Building2 className="size-3 shrink-0 text-muted-foreground" />
      <span className="font-medium truncate flex-1">{name}</span>
      {data.legal_person != null ? (
        <span className="text-muted-foreground truncate max-w-[80px]">{String(data.legal_person)}</span>
      ) : null}
      {status ? (
        <Badge variant="secondary" className="text-[10px] px-1 py-0 shrink-0">{status}</Badge>
      ) : null}
    </div>
  )
}

function RiskList({ output }: { output: unknown }) {
  const items = extractList(output)
  if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">暂无风险信息</div>

  return (
    <div className="space-y-1">
      {items.slice(0, 5).map((item, i) => {
        const d = item as Record<string, unknown>
        return (
          <div key={i} className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
            <Shield className="size-3 shrink-0 text-orange-500" />
            <span className="truncate flex-1">{String(d.title ?? d.risk_type ?? d.content ?? '')}</span>
            {d.risk_level != null ? (
              <Badge variant="secondary" className="text-[10px] px-1 py-0">{String(d.risk_level)}</Badge>
            ) : null}
          </div>
        )
      })}
      {items.length > 5 ? <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 条</div> : null}
    </div>
  )
}

function SimpleList({ output, icon: Icon, label, nameKey }: { output: unknown; icon: typeof Building2; label: string; nameKey: string }) {
  const items = extractList(output)
  if (items.length === 0) return <div className="text-muted-foreground text-xs py-1">暂无{label}信息</div>

  return (
    <div className="space-y-1">
      <div className="text-[10px] text-muted-foreground">{label} ({items.length})</div>
      {items.slice(0, 5).map((item, i) => {
        const d = item as Record<string, unknown>
        return (
          <div key={i} className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
            <Icon className="size-3 shrink-0 text-muted-foreground" />
            <span className="truncate flex-1">{String(d[nameKey] ?? '')}</span>
            {d.role != null ? <span className="text-muted-foreground">{String(d.role)}</span> : null}
            {d.ratio != null ? <span className="text-muted-foreground">{String(d.ratio)}</span> : null}
          </div>
        )
      })}
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
