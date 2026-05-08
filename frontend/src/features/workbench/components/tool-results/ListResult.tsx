/** 通用列表工具结果渲染 — 带有 key-value 格式的紧凑列表 */

import React from 'react'
import { List } from 'lucide-react'
import type { ToolResultRendererProps } from './index'

export function ListResult({ output }: ToolResultRendererProps) {
  const items = extractList(output)
  if (items.length === 0) return null

  // 如果只有一条记录且是对象，用 key-value 展示
  if (items.length === 1 && typeof items[0] === 'object' && items[0] !== null) {
    return <SingleRecord data={items[0] as Record<string, unknown>} />
  }

  // 多条记录，紧凑列表
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-muted-foreground flex items-center gap-1">
        <List className="size-3" />
        <span>共 {items.length} 条结果</span>
      </div>
      {items.slice(0, 5).map((item, i) => (
        <CompactItem key={i} data={item} index={i} />
      ))}
      {items.length > 5 && (
        <div className="text-[10px] text-muted-foreground">...还有 {items.length - 5} 条</div>
      )}
    </div>
  )
}

function SingleRecord({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v != null && v !== '')

  return (
    <div className="rounded-md border border-border/60 bg-background p-2 text-xs">
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        {entries.slice(0, 10).map(([key, val]) => (
          <React.Fragment key={key}>
            <span className="text-muted-foreground whitespace-nowrap">{formatKey(key)}:</span>
            <span className="text-foreground truncate">{formatValue(val)}</span>
          </React.Fragment>
        ))}
      </div>
      {entries.length > 10 && (
        <div className="text-[10px] text-muted-foreground mt-1">...共 {entries.length} 个字段</div>
      )}
    </div>
  )
}

function CompactItem({ data, index }: { data: unknown; index: number }) {
  if (typeof data !== 'object' || data === null) {
    return (
      <div className="rounded border border-border/40 bg-background/60 px-2 py-1 text-xs truncate">
        {String(data)}
      </div>
    )
  }

  const obj = data as Record<string, unknown>
  // 尝试找到最有意义的显示字段
  const displayKey = ['name', 'title', 'label', 'description', 'content', 'message'].find(k => obj[k])
  const displayVal = displayKey ? String(obj[displayKey]) : JSON.stringify(obj).slice(0, 100)

  return (
    <div className="flex items-center gap-2 rounded border border-border/40 bg-background/60 px-2 py-1.5 text-xs">
      <span className="text-muted-foreground shrink-0 w-5 text-right">{index + 1}.</span>
      <span className="truncate flex-1">{displayVal}</span>
    </div>
  )
}

function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatValue(val: unknown): string {
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'number') return val.toLocaleString()
  if (Array.isArray(val)) return val.length + ' 项'
  return String(val)
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
