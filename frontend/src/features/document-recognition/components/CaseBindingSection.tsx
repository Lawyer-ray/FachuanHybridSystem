import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link2, Loader2, Search, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { bindTask, searchCasesForBinding } from '../api'
import { pickAutoRecommendation } from '../domain'
import type { TaskOut } from '../types'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

interface Props {
  task: TaskOut
  onBound: () => Promise<void> | void
}

type Picked = { id: number; name: string; number: string }

/**
 * 第 1 步 · 案件绑定：已绑定/管线模式显示案件 chip；
 * 未绑定时给推荐卡片 + 搜索选择，确认后调 bind。
 * 推荐唯一高分时自动预选（省一次点击，仍可换选）。
 * 不强制绑定——律师可跳过直接确认日期（创建独立提醒）。
 */
export function CaseBindingSection({ task, onBound }: Props) {
  const [kw, setKw] = useState('')
  const [picked, setPicked] = useState<Picked | null>(null)
  const [autoPicked, setAutoPicked] = useState(false)
  // 失焦收起候选；重新输入即展开（对齐旧实现 onBlur 清空 results 的行为）
  const [listHidden, setListHidden] = useState(false)
  const [binding, setBinding] = useState(false)

  const caseName = task.binding?.case_name || null
  const isBound = Boolean(task.binding?.success && caseName)
  const reco = useMemo(() => task.recommendations ?? [], [task.recommendations])

  // 搜索：至少 2 字符才查（与旧防抖版一致）；上一请求由 signal 自动中止，无响应竞态
  const kwTrim = kw.trim()
  const { data: searched = [], isFetching: searching } = useQuery({
    queryKey: ['doc-recognition-case-search', kwTrim],
    queryFn: ({ signal }) => searchCasesForBinding(kwTrim, { signal }),
    enabled: !isBound && kwTrim.length >= 2,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
  const results = useMemo(
    () =>
      listHidden
        ? []
        : searched.map((c) => ({ id: c.id, name: c.name, number: c.case_numbers?.[0] ?? `案件 ${c.id}` })),
    [listHidden, searched],
  )

  // 推荐唯一高分时自动预选（仅一次；用户手动改动后不再覆盖）
  const autoPick = useMemo(() => pickAutoRecommendation(reco), [reco])
  const autoPickedRef = useRef(false)
  useEffect(() => {
    if (!autoPick || autoPickedRef.current) return
    autoPickedRef.current = true
    setPicked({
      id: autoPick.case_id,
      name: autoPick.case_name,
      number: autoPick.case_numbers?.[0] ?? `案件 ${autoPick.case_id}`,
    })
    setAutoPicked(true)
  }, [autoPick])

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

  // 已绑定（含管线模式）：只读 chip
  if (isBound) {
    return (
      <div className="flex animate-in fade-in slide-in-from-bottom-1 duration-300 items-center gap-2 rounded-[10px] border border-status-green/40 bg-status-green-bg px-3 py-2">
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
          <span className="text-[11px] font-semibold text-muted-foreground">
            推荐案件
            {autoPicked && picked && (
              <span className="ml-1.5 inline-flex items-center gap-0.5 rounded-[5px] border border-status-blue/40 bg-status-blue-bg px-1.5 py-[1px] text-[9.5px] font-semibold text-status-blue">
                <Sparkles className="h-2.5 w-2.5" />
                已按相关度预选
              </span>
            )}
          </span>
          {reco.slice(0, 3).map((r, i) => (
            <button
              key={r.case_id}
              type="button"
              style={{ animationDelay: `${i * 70}ms` }}
              disabled={binding}
              onClick={() => {
                setAutoPicked(false)
                setPicked({ id: r.case_id, name: r.case_name, number: r.case_numbers?.[0] ?? `案件 ${r.case_id}` })
              }}
              className={cn(
                'animate-in fade-in slide-in-from-bottom-2 duration-300 flex items-center gap-2.5 rounded-[10px] border bg-card px-3 py-2 text-left transition-all duration-200 hover:border-ring/40',
                picked?.id === r.case_id ? 'border-ring/60 bg-secondary/60 shadow-sm' : 'border-border',
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

      {/* 搜索区：结果为绝对定位浮层（不挤压下方内容；grid item 需 min-w-0 才能让 truncate 生效） */}
      <div
        className="relative min-w-0"
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setListHidden(true)
        }}
      >
        <div className="flex items-center gap-1.5">
          <div className="flex h-[34px] min-w-0 flex-1 items-center gap-1.5 rounded-[9px] border border-input bg-card px-2.5 focus-within:border-ring/40">
            <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" />
            <input
              className="min-w-0 flex-1 border-none bg-transparent text-[12.5px] outline-none placeholder:text-muted-foreground"
              placeholder="搜索案号 / 案件名 / 当事人"
              value={picked ? `${picked.number} · ${picked.name}` : kw}
              onChange={(e) => {
                setPicked(null)
                setAutoPicked(false)
                setListHidden(false)
                setKw(e.target.value)
              }}
            />
            {searching && <Loader2 className="h-3.5 w-3.5 flex-none animate-spin text-muted-foreground" />}
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
          <div className="animate-in fade-in slide-in-from-top-1 duration-200 absolute inset-x-0 top-full z-20 mt-1 flex max-h-[248px] flex-col overflow-y-auto rounded-[10px] border border-border bg-card shadow-lg">
            <span className="border-b border-border bg-secondary/50 px-3 py-1.5 text-[10.5px] font-semibold text-muted-foreground">
              找到 {results.length} 个案件
            </span>
            {results.map((c) => (
              <button
                key={c.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setAutoPicked(false)
                  setPicked(c)
                }}
                className="min-w-0 border-b border-border px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
              >
                <span className="block truncate text-[12px] font-semibold">{c.number}</span>
                <span className="block truncate text-[10.5px] text-muted-foreground">{c.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <span className="text-[10.5px] text-muted-foreground">
        可暂不关联案件：下方确认的日期将创建独立提醒，后续仍可在后台绑定案件。
      </span>
    </div>
  )
}
