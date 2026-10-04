import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, SlidersHorizontal, X } from 'lucide-react'

import type { ContractFacetItem, ContractPageResponse, WorkbenchFilter } from '../types'

interface FilterBarProps {
  facets: ContractPageResponse | null
  filter: WorkbenchFilter
  onChange: (f: WorkbenchFilter) => void
}

const STATUS_OPTIONS: Array<{ value: NonNullable<WorkbenchFilter['status']>; label: string }> = [
  { value: '', label: '全部' },
  { value: 'active', label: '在办' },
  { value: 'archived', label: '已归档' },
  { value: 'unsigned', label: '未签约' },
]

const STATUS_LABEL: Record<string, string> = { archived: '已归档', unsigned: '未签约', '': '全部' }

/** 单颗筛选 chip */
function Chip({ label, count, on, onClick }: { label: string; count: number; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-[4.5px] text-xs transition-colors ' +
        (on
          ? 'border-foreground bg-foreground font-[550] text-background'
          : 'border-border bg-card text-secondary-foreground hover:border-input hover:bg-secondary')
      }
    >
      {label}
      <span className={'text-[10.5px] tabular-nums ' + (on ? 'text-background/55' : 'text-muted-foreground/70')}>
        {count}
      </span>
    </button>
  )
}

/** 激活筛选 = 可单独移除的黑底 chip（默认态零 chip；搜索不出 chip——输入框本身即状态） */
function ActiveChip({ text, onRemove }: { text: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-[7px] rounded-full bg-foreground px-3 py-1 text-xs font-[550] text-background">
      {text}
      <button
        type="button"
        title="移除"
        aria-label="移除"
        className="flex size-4 items-center justify-center rounded-full bg-white/20 text-[10px] leading-none hover:bg-white/40"
        onClick={onRemove}
      >
        <X className="size-2.5" />
      </button>
    </span>
  )
}

/**
 * 页头单行工具栏：搜索框 + 筛选弹层（状态/类目/收费 chips）+ 激活 chips。
 * 计数来自后端 facets（全库口径）；`/` 聚焦搜索；弹层内连续调整不关闭，点外部关闭。
 */
export function FilterBar({ facets, filter, onChange }: FilterBarProps) {
  const [panelOpen, setPanelOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  /* `/` 聚焦搜索（输入框聚焦时不抢） */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? '').toUpperCase()
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /* 点弹层外关闭 */
  useEffect(() => {
    if (!panelOpen) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setPanelOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [panelOpen])

  const statusCounts = facets?.status_counts ?? {}
  const total = facets?.total ?? 0
  const catFacets = useMemo(() => facets?.cat_counts ?? [], [facets])
  const feeFacets = useMemo(() => facets?.fee_counts ?? [], [facets])
  const catLabel = (v: string) => catFacets.find((f: ContractFacetItem) => f.value === v)?.label ?? v
  const feeLabel = (v: string) => feeFacets.find((f: ContractFacetItem) => f.value === v)?.label ?? v

  const activeChips: Array<{ key: keyof WorkbenchFilter; text: string }> = []
  if (filter.status !== 'active') activeChips.push({ key: 'status', text: STATUS_LABEL[filter.status] || filter.status })
  if (filter.cat) activeChips.push({ key: 'cat', text: catLabel(filter.cat) })
  if (filter.fee) activeChips.push({ key: 'fee', text: feeLabel(filter.fee) })

  const set = (patch: Partial<WorkbenchFilter>) => onChange({ ...filter, ...patch })

  return (
    <div className="ml-auto flex flex-wrap items-center gap-2" ref={wrapRef}>
      <label className="flex h-[33px] w-[300px] flex-none items-center gap-[7px] rounded-[10px] border border-border bg-card/65 px-3 transition-all focus-within:border-input focus-within:bg-card focus-within:shadow-sm">
        <Search className="size-3.5 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          value={filter.q}
          onChange={(e) => set({ q: e.target.value })}
          type="text"
          placeholder="搜索合同（名称）"
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
        />
        <kbd className="rounded-[5px] border border-border bg-secondary px-1 text-[10px] text-muted-foreground">/</kbd>
      </label>

      <div className="relative flex-none">
        <button
          type="button"
          className={
            'inline-flex h-[33px] items-center gap-[7px] rounded-[11px] border px-3.5 text-xs font-[550] transition-colors ' +
            (panelOpen
              ? 'border-foreground bg-card text-foreground'
              : 'border-border bg-card/65 text-secondary-foreground hover:border-input hover:bg-card')
          }
          onClick={() => setPanelOpen((v) => !v)}
        >
          <SlidersHorizontal className="size-3.5" />
          筛选
          {activeChips.length > 0 && (
            <span className="rounded-full bg-foreground px-[5px] text-[10px] leading-[1.5] font-semibold text-background tabular-nums">
              {activeChips.length}
            </span>
          )}
        </button>

        {panelOpen && (
          <div className="absolute top-[41px] right-0 z-60 max-h-[calc(100vh-120px)] w-[300px] max-w-[calc(100vw-24px)] overflow-y-auto rounded-[14px] border border-border bg-card p-3.5 shadow-lg">
            <div className="mb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">状态</div>
            <div className="flex flex-wrap gap-1.5">
              {STATUS_OPTIONS.map((s) => (
                <Chip
                  key={s.value}
                  label={s.label}
                  count={s.value === '' ? total : (statusCounts[s.value] ?? 0)}
                  on={filter.status === s.value}
                  onClick={() => set({ status: s.value })}
                />
              ))}
            </div>
            <div className="mt-3 mb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">类目</div>
            <div className="flex flex-wrap gap-1.5">
              <Chip label="全部" count={total} on={filter.cat === ''} onClick={() => set({ cat: '' })} />
              {catFacets.map((f) => (
                <Chip key={f.value} label={f.label} count={f.n} on={filter.cat === f.value} onClick={() => set({ cat: f.value })} />
              ))}
            </div>
            <div className="mt-3 mb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">收费方式</div>
            <div className="flex flex-wrap gap-1.5">
              <Chip label="全部" count={total} on={filter.fee === ''} onClick={() => set({ fee: '' })} />
              {feeFacets.map((f) => (
                <Chip key={f.value} label={f.label} count={f.n} on={filter.fee === f.value} onClick={() => set({ fee: f.value })} />
              ))}
            </div>
            <div className="mt-3.5 border-t border-border-light pt-2.5 text-right">
              <button
                type="button"
                className="rounded-[9px] px-2 py-1 text-xs text-muted-foreground underline underline-offset-3 hover:text-foreground"
                onClick={() => onChange({ status: 'active', cat: '', fee: '', q: '' })}
              >
                清除全部筛选
              </button>
            </div>
          </div>
        )}
      </div>

      {activeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {activeChips.map((c) => (
            <ActiveChip
              key={c.key}
              text={c.text}
              onRemove={() => {
                if (c.key === 'status') set({ status: 'active' })
                else if (c.key === 'cat') set({ cat: '' })
                else set({ fee: '' })
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
