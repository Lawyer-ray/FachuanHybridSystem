import { Check, ChevronDown, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { ConvertTemplateGroup } from '../../api'
import type { ConvertTemplate } from '../../types'
import { cn } from '@/lib/utils'
import { FIELD } from '../../ui'

/**
 * 文书类型可搜索组合框（替代原生 select）：
 * 60+ 模板的 原生下拉又长又不能搜，这里点开带输入框、输入即过滤，分组标题保留。
 * 面板开合方向自适应——工具坞在页面底部，下方放不下时朝上弹。
 */
export function TemplateCombobox({
  groups,
  value,
  onChange,
  disabled,
}: {
  groups: ConvertTemplateGroup[]
  /** 当前选中的模板 mbid；空串 = 未选 */
  value: string
  onChange: (mbid: string) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [up, setUp] = useState(false)
  const [kw, setKw] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  // 点击面板外关闭（mousedown 防止先失焦把点击吞掉）
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const selected: ConvertTemplate | null = useMemo(() => {
    for (const g of groups) {
      const hit = g.items.find((it) => it.mbid === value)
      if (hit) return hit
    }
    return null
  }, [groups, value])

  // 过滤：模板名或分类名包含关键词（保留分组结构，空组剔除）
  const filtered = useMemo(() => {
    const kwT = kw.trim()
    if (!kwT) return groups
    return groups
      .map((g) => ({
        ...g,
        items: g.items.filter((it) => it.name.includes(kwT) || g.category.includes(kwT)),
      }))
      .filter((g) => g.items.length > 0)
  }, [groups, kw])

  const openPanel = () => {
    if (disabled) return
    const rect = wrapRef.current?.getBoundingClientRect()
    // 面板约 300px 高：下方放不下就朝上弹（工具坞在页面底部，通常朝上）
    setUp(!!rect && rect.bottom + 300 > window.innerHeight)
    setKw('')
    setOpen(true)
  }

  const pick = (it: ConvertTemplate) => {
    onChange(it.mbid)
    setOpen(false)
  }

  return (
    <div className="relative min-w-0" ref={wrapRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={openPanel}
        className={cn(FIELD, 'flex items-center justify-between gap-2 text-left', disabled && 'opacity-60')}
      >
        <span className={cn('min-w-0 truncate', !selected && 'text-muted-foreground')} title={selected?.name}>
          {selected ? selected.name : '选择文书类型…'}
        </span>
        <ChevronDown className={cn('h-3.5 w-3.5 flex-none text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div
          className={cn(
            'animate-in fade-in absolute inset-x-0 z-30 flex max-h-[300px] flex-col overflow-hidden rounded-[10px] border border-border bg-card shadow-lg duration-200',
            up ? 'bottom-full mb-1 slide-in-from-bottom-1' : 'top-full mt-1 slide-in-from-top-1',
          )}
        >
          <div className="flex flex-none items-center gap-1.5 border-b border-border px-2.5 py-1.5">
            <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" />
            <input
              autoFocus
              value={kw}
              onChange={(e) => setKw(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setOpen(false)
                // 回车：过滤结果唯一时直接选中
                if (e.key !== 'Enter') return
                const sole = filtered.length === 1 ? (filtered[0]?.items[0] ?? undefined) : undefined
                if (sole) pick(sole)
              }}
              placeholder="搜索文书类型…"
              className="min-w-0 flex-1 border-none bg-transparent text-[12px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-center text-[11.5px] text-muted-foreground">没有匹配的文书类型</div>
            ) : (
              filtered.map((g) => (
                <div key={g.category}>
                  <div className="sticky top-0 bg-secondary/80 px-3 py-1 text-[10px] font-semibold text-muted-foreground backdrop-blur-sm">
                    {g.category}
                  </div>
                  {g.items.map((it) => (
                    <button
                      key={it.mbid}
                      type="button"
                      onClick={() => pick(it)}
                      className={cn(
                        'flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-secondary/60',
                        value === it.mbid && 'bg-secondary/40',
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">{it.name}</span>
                      {value === it.mbid && <Check className="h-3.5 w-3.5 flex-none text-status-green" />}
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
