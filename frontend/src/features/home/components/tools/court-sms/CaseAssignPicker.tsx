import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Check, Loader2, Search } from 'lucide-react'

import { searchCasesForBinding, type CaseSearchItem } from '@/features/document-recognition'
import { cn } from '@/lib/utils'

/**
 * 人工分配案件的搜索选择器（法院短信匹配不到案件时用）。
 * 挂载即拉一版在办案件作为候选；输入关键词实时检索（名/案号/当事人），
 * 上一请求由 query 的 signal 自动中止，无响应竞态。
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
  const [picked, setPicked] = useState<CaseSearchItem | null>(null)

  // 空关键词 = 后端返回在办案件列表，正好作为初始候选（挂载即查）
  const kwTrim = kw.trim()
  const { data: results = [], isFetching: searching } = useQuery({
    queryKey: ['court-sms-case-search', kwTrim],
    queryFn: ({ signal }) => searchCasesForBinding(kwTrim, { limit: 10, signal }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })

  const inputText = picked ? `${picked.case_numbers?.[0] ?? `案件 ${picked.id}`} · ${picked.name}` : kw

  return (
    <div className="flex flex-col gap-2">
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

      {/* 候选列表放文档流内（不用 absolute 浮层）：弹窗内容区是滚动容器，浮层会被
          裁剪且把下方按钮顶出视口——此前「看不到下拉」就是这个原因 */}
      {results.length > 0 && !picked && (
        <div className="animate-in fade-in slide-in-from-top-1 flex max-h-[200px] flex-col overflow-y-auto rounded-[10px] border border-border bg-card duration-200">
          {results.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => {
                setPicked(c)
              }}
              className="min-w-0 border-b border-border px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
            >
              <span className="block truncate text-[12px] font-semibold">{c.case_numbers?.[0] ?? `案件 ${c.id}`}</span>
              <span className="block truncate text-[10.5px] text-muted-foreground">{c.name}</span>
            </button>
          ))}
        </div>
      )}

      {picked && (
        <div className="animate-in fade-in slide-in-from-bottom-1 flex items-center gap-2 rounded-[10px] border border-status-blue/40 bg-status-blue-bg px-3 py-2">
          <Check className="h-3.5 w-3.5 flex-none text-status-blue" />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold">
            {picked.case_numbers?.[0] ?? `案件 ${picked.id}`} · {picked.name}
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
