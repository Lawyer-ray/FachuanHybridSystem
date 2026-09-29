import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, Search } from 'lucide-react'

import { searchCasesForAssign, type CaseSearchItem } from '../../../api'
import { cn } from '@/lib/utils'

/**
 * 人工分配案件的搜索选择器（法院短信匹配不到案件时用）。
 * 挂载即拉一版在办案件作为候选；输入关键词后 300ms 防抖搜索（名/案号/当事人）。
 * 选中后由父级调 onAssign —— assign 成功后端会继续跑重命名→通知，弹窗回到处理中。
 */
export function CaseAssignPicker({
  busy,
  onAssign,
}: {
  busy: boolean
  onAssign: (caseId: number) => Promise<void>
}) {
  const [kw, setKw] = useState('')
  const [results, setResults] = useState<CaseSearchItem[]>([])
  const [picked, setPicked] = useState<CaseSearchItem | null>(null)
  const [searching, setSearching] = useState(false)
  const timer = useRef(0)

  useEffect(() => {
    const run = async (q: string) => {
      setSearching(true)
      try {
        setResults(await searchCasesForAssign(q))
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }
    // 空关键词 = 后端返回在办案件列表，正好作为初始候选
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => void run(kw.trim()), kw ? 300 : 0)
    return () => window.clearTimeout(timer.current)
  }, [kw])

  const inputText = picked ? `${picked.case_numbers[0] ?? `案件 ${picked.id}`} · ${picked.name}` : kw

  return (
    <div className="flex flex-col gap-2">
      <div className="relative min-w-0" onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setResults([])
      }}>
        <div className="flex h-[36px] items-center gap-2 rounded-[9px] border border-input bg-card px-2.5 focus-within:border-ring/40">
          <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" />
          <input
            className="min-w-0 flex-1 border-none bg-transparent text-[12.5px] outline-none placeholder:text-muted-foreground"
            placeholder="搜索案号 / 案件名 / 当事人"
            value={inputText}
            disabled={busy}
            onChange={(e) => {
              setPicked(null)
              setKw(e.target.value)
            }}
          />
          {searching && <Loader2 className="h-3.5 w-3.5 flex-none animate-spin text-muted-foreground" />}
        </div>

        {results.length > 0 && !picked && (
          <div className="animate-in fade-in slide-in-from-top-1 absolute inset-x-0 top-full z-20 mt-1 flex max-h-[232px] flex-col overflow-y-auto rounded-[10px] border border-border bg-card shadow-lg">
            {results.map((c) => (
              <button
                key={c.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setPicked(c)
                  setResults([])
                }}
                className="min-w-0 border-b border-border px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
              >
                <span className="block truncate text-[12px] font-semibold">{c.case_numbers[0] ?? `案件 ${c.id}`}</span>
                <span className="block truncate text-[10.5px] text-muted-foreground">{c.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {picked && (
        <div className="animate-in fade-in slide-in-from-bottom-1 flex items-center gap-2 rounded-[10px] border border-status-blue/40 bg-status-blue-bg px-3 py-2">
          <Check className="h-3.5 w-3.5 flex-none text-status-blue" />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold">
            {picked.case_numbers[0] ?? `案件 ${picked.id}`} · {picked.name}
          </span>
          <button
            type="button"
            className="text-[11px] font-medium text-muted-foreground underline-offset-2 hover:underline"
            disabled={busy}
            onClick={() => {
              setPicked(null)
              setKw('')
            }}
          >
            重选
          </button>
        </div>
      )}

      <button
        type="button"
        disabled={!picked || busy}
        onClick={async () => {
          if (!picked) return
          await onAssign(picked.id)
        }}
        className={cn(
          'flex h-[34px] items-center justify-center gap-1.5 rounded-[9px] bg-foreground text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85',
          'disabled:cursor-not-allowed disabled:opacity-45',
        )}
      >
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {busy ? '正在指定…' : '指定案件并继续处理'}
      </button>
    </div>
  )
}
