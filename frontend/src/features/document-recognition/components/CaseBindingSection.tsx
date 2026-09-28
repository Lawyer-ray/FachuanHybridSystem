import { useEffect, useRef, useState } from 'react'
import { Link2, Loader2, Search } from 'lucide-react'
import { toast } from 'sonner'

import { bindTask, searchCasesForBinding } from '../api'
import type { TaskOut } from '../types'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

interface Props {
  task: TaskOut
  onBound: () => Promise<void> | void
}

/**
 * 第 1 步 · 案件绑定：已绑定/管线模式显示案件 chip；
 * 未绑定时给推荐卡片 + 搜索选择，确认后调 bind。
 * 不强制绑定——律师可跳过直接确认日期（创建独立提醒）。
 */
export function CaseBindingSection({ task, onBound }: Props) {
  const [kw, setKw] = useState('')
  const [results, setResults] = useState<{ id: number; name: string; number: string }[]>([])
  const [picked, setPicked] = useState<{ id: number; name: string; number: string } | null>(null)
  const [searching, setSearching] = useState(false)
  const [binding, setBinding] = useState(false)
  const timer = useRef(0)

  const caseName = task.binding?.case_name || null
  const isBound = Boolean(task.binding?.success && caseName)

  // 搜索防抖（300ms，至少 2 字符）
  useEffect(() => {
    if (isBound || kw.trim().length < 2) {
      setResults([])
      return
    }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      setSearching(true)
      try {
        const items = await searchCasesForBinding(kw.trim())
        setResults(
          items.map((c) => ({ id: c.id, name: c.name, number: c.case_numbers?.[0] ?? `案件 ${c.id}` })),
        )
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => window.clearTimeout(timer.current)
  }, [kw, isBound])

  const doBind = async () => {
    if (!picked || binding) return
    setBinding(true)
    try {
      await bindTask(task.task_id, picked.id)
      toast.success(`已绑定案件：${picked.name}`)
      setPicked(null)
      setKw('')
      await onBound()
    } catch (e) {
      toast.error(errMessage(e, '绑定失败，请稍后重试'))
    } finally {
      setBinding(false)
    }
  }

  const reco = task.recommendations ?? []

  // 已绑定（含管线模式）：只读 chip
  if (isBound) {
    return (
      <div className="flex items-center gap-2 rounded-[10px] border border-status-green/40 bg-status-green-bg px-3 py-2">
        <Link2 className="h-3.5 w-3.5 flex-none text-status-green" />
        <span className="text-[12.5px] font-semibold">
          {task.binding_mode === 'pipeline' ? '已由法院短信绑定：' : '已绑定案件：'}
          {caseName}
        </span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {reco.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground">推荐案件</span>
          {reco.slice(0, 3).map((r) => (
            <button
              key={r.case_id}
              type="button"
              disabled={binding}
              onClick={() => setPicked({ id: r.case_id, name: r.case_name, number: r.case_numbers?.[0] ?? `案件 ${r.case_id}` })}
              className={cn(
                'flex items-center gap-2.5 rounded-[10px] border border-border bg-card px-3 py-2 text-left transition-colors hover:border-ring/40',
                picked?.id === r.case_id && 'border-ring/60 bg-secondary/60',
              )}
            >
              <span className="flex-none text-[11px] font-semibold tabular-nums text-status-blue">相关度 {r.score}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-semibold">{r.case_name}</span>
                <span className="block truncate text-[10.5px] text-muted-foreground">
                  {r.case_numbers?.[0] ?? ''}
                  {r.reasons?.length ? ` · ${r.reasons.join(' · ')}` : ''}
                </span>
              </span>
            </button>
          ))}
          {reco.length > 3 && (
            <span className="text-[10.5px] text-muted-foreground">共 {reco.length} 个推荐，更多用下方搜索</span>
          )}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        <div className="flex h-[34px] min-w-0 flex-1 items-center gap-1.5 rounded-[9px] border border-input bg-card px-2.5 focus-within:border-ring/40">
          <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" />
          <input
            className="min-w-0 flex-1 border-none bg-transparent text-[12.5px] outline-none placeholder:text-muted-foreground"
            placeholder="搜索案号 / 案件名 / 当事人"
            value={picked ? `${picked.number} · ${picked.name}` : kw}
            onChange={(e) => {
              setPicked(null)
              setKw(e.target.value)
            }}
          />
          {searching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </div>
        <button
          type="button"
          className="h-[34px] flex-none rounded-[9px] bg-primary px-3 text-[12.5px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          disabled={!picked || binding}
          onClick={doBind}
        >
          {binding ? '绑定中…' : '绑定案件'}
        </button>
      </div>

      {results.length > 0 && !picked && (
        <div className="flex flex-col overflow-hidden rounded-[10px] border border-border">
          {results.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setPicked(c)}
              className="border-b border-border px-3 py-2 text-left last:border-b-0 transition-colors hover:bg-secondary/60"
            >
              <span className="block truncate text-[12px] font-semibold">{c.number}</span>
              <span className="block truncate text-[10.5px] text-muted-foreground">{c.name}</span>
            </button>
          ))}
        </div>
      )}

      <span className="text-[10.5px] text-muted-foreground">
        可暂不关联案件：下方确认的日期将创建独立提醒，后续仍可在后台绑定案件。
      </span>
    </div>
  )
}
