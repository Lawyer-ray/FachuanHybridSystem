import { useEffect, useRef, useState } from 'react'
import { LoaderCircle, Search, User, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { searchClients } from '../../api'
import type { ClientHit } from '../../types'

/**
 * 当事人检索填报：委托人/对方当事人字段专用。
 * 输入姓名或单位，从后端客户库模糊检索；点选即填入（多条按「、」追加）。
 * 保留手动输入能力，检索结果仅作为快捷填充。
 */
export function PartyPicker({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<ClientHit[]>([])
  const [loading, setLoading] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const startSearch = (kw: string) => {
    setQ(kw)
    if (timer.current) clearTimeout(timer.current)
    const t = kw.trim()
    if (!t) {
      setHits([])
      setLoading(false)
      return
    }
    setLoading(true)
    timer.current = setTimeout(async () => {
      try {
        const list = await searchClients(t)
        setHits(list.slice(0, 12))
      } catch {
        setHits([])
      } finally {
        setLoading(false)
      }
    }, 260)
  }

  const chosen = new Set(value.split('、').map((s) => s.trim()).filter(Boolean))

  const pick = (name: string) => {
    if (chosen.has(name)) return
    onChange(value ? `${value}、${name}` : name)
    setHits([])
    setQ('')
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            'flex h-8 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-2 text-left text-[13px] outline-none transition-colors',
            open && 'border-primary ring-1 ring-ring',
            !value && 'text-muted-foreground',
          )}
        >
          <span className="min-w-0 flex-1 truncate">{value || placeholder || ''}</span>
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={4} className="w-[290px] p-2">
        <div className="relative">
          <Input
            autoFocus
            value={q}
            onChange={(e) => startSearch(e.target.value)}
            placeholder="输入姓名或单位检索当事人"
            className="h-8 pr-7 text-[13px]"
          />
          {loading && (
            <LoaderCircle className="absolute right-2 top-2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
          )}
        </div>
        <div className="mt-1 max-h-52 overflow-y-auto">
          {!q.trim() && (
            <div className="px-2 py-2 text-[12px] text-muted-foreground">
              输入姓名或单位，从客户库检索；找到点选即填入
            </div>
          )}
          {q.trim() && !loading && hits.length === 0 && (
            <div className="px-2 py-2 text-[12px] text-muted-foreground">没有匹配的当事人</div>
          )}
          {hits.map((h) => (
            <button
              key={h.id}
              type="button"
              onClick={() => pick(h.name)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-secondary"
            >
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-secondary">
                <User className="h-3 w-3 text-secondary-foreground" />
              </span>
              <span className="min-w-0 flex-1 truncate">{h.name}</span>
              {chosen.has(h.name) && <span className="shrink-0 text-[11px] text-muted-foreground">已选</span>}
            </button>
          ))}
        </div>
        {value && (
          <div className="mt-1 flex items-center gap-1 border-t border-border pt-1 text-[11px] text-muted-foreground">
            <span className="min-w-0 flex-1 truncate">已选：{value}</span>
            <button
              type="button"
              onClick={() => {
                onChange('')
                setOpen(false)
              }}
              className="flex shrink-0 items-center gap-0.5 text-secondary-foreground hover:text-destructive"
            >
              <X className="h-3 w-3" />
              清空
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
