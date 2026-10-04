import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Loader2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { searchCases } from '../../api'
import type { AssignInfo, CaseRow, InfoField } from '../../types'
import { cn } from '@/lib/utils'

type Target = 'existing' | 'new'
type ContractOpt = 'has' | 'none'

/** 弹窗内可聚焦元素（按 Tab 顺序）；每次按键实时查询，适配切 tab 增删的输入 */
function focusablesOf(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'input, textarea, button, select, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !(el as HTMLButtonElement).disabled && el.offsetParent !== null)
}

export function AssignModal({
  open,
  count,
  infos,
  onCancel,
  onConfirm,
}: {
  open: boolean
  count: number
  infos: InfoField[]
  onCancel: () => void
  onConfirm: (assign: AssignInfo) => void
}) {
  const [target, setTarget] = useState<Target>('existing')
  const [contract, setContract] = useState<ContractOpt>('has')
  const [q, setQ] = useState('')
  const [pickCase, setPickCase] = useState<CaseRow | null>(null)

  const who = infos.find((f) => f.k === '委托人')?.v || ''
  // 生成委托合同要用的字段：委托人不填不能提交，另两个可空
  const [fields, setFields] = useState<Record<string, string>>({
    委托人: '',
    对方当事人: '',
    标的额: '',
  })
  const setField = (k: string, v: string) => setFields((prev) => ({ ...prev, [k]: v }))

  // 案件检索：queryKey 用防抖值（输入停 250ms 才请求，不再每键一发），
  // 上一请求由 signal 自动中止（无响应竞态）；raw 值只管「清空即清列表」
  const rawKw = q.trim()
  const kw = useDebouncedValue(rawKw, 250)
  const { data: searched = [], isFetching: loading, error } = useQuery({
    queryKey: ['mp-case-search', kw],
    queryFn: ({ signal }) => searchCases(kw, signal),
    enabled: open && target === 'existing' && !!kw,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
  // 空关键词不显示旧候选（对齐旧实现「清空输入即清列表」）
  const cases = rawKw ? searched : []

  useEffect(() => {
    if (error) toast.error('案件搜索失败，请检查后端')
  }, [error])

  useEffect(() => {
    if (!open) return
    setTarget('existing')
    setContract('has')
    setQ('')
    setPickCase(null)
    setFields({
      委托人: infos.find((f) => f.k === '委托人')?.v || '',
      对方当事人: infos.find((f) => f.k === '对方当事人')?.v || '',
      标的额: infos.find((f) => f.k === '标的额')?.v || '',
    })
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Esc 关闭本弹窗（capture 阶段拦截）。本弹窗是手写 DOM 层，不在 Radix
  // DismissableLayer 体系内：搜索框又 autoFocus，焦点落在 input 上时
  // use-reader-keys 的输入框守卫会直接吞掉 Esc。这里在 capture 阶段拦下并
  // stopPropagation，既保证弹窗内任何焦点位置按 Esc 都能关闭，又不会落进
  // use-reader-keys 的冒泡监听把整个阅读器关掉。
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      onCancel()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onCancel])

  // 焦点陷阱：本弹窗是手写 DOM 层、不在 Radix Dialog 体系内，Tab 必须圈在
  // 弹窗内循环，否则键盘用户会聚焦到被遮住的背景内容上
  const panelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    if (!panel) return
    // 打开即聚焦：优先输入框（搜索框），没有再落到首个可交互元素
    const list = focusablesOf(panel)
    ;(list.find((el) => el.tagName === 'INPUT') ?? list[0])?.focus()
    const onTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const list = focusablesOf(panel)
      if (!list.length) return
      const first = list[0]!
      const last = list[list.length - 1]!
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    panel.addEventListener('keydown', onTab)
    return () => panel.removeEventListener('keydown', onTab)
  }, [open])

  if (!open) return null

  const why =
    target === 'existing'
      ? pickCase
        ? '将追加到所选案件'
        : '先在上面选一个案件'
      : contract === 'none'
        ? (fields['委托人'] ?? '').trim()
          ? '将据此生成委托合同'
          : '写个委托人就能生成合同'
        : '不用再填别的，直接建案'

  const okDisabled =
    (target === 'existing' && !pickCase) ||
    (target === 'new' && contract === 'none' && !(fields['委托人'] ?? '').trim())

  const confirm = () => {
    if (okDisabled) return
    let assign: AssignInfo
    if (target === 'existing' && pickCase) {
      assign = {
        target: 'existing',
        caseId: pickCase.id,
        caseNo: pickCase.filing_number || pickCase.case_numbers?.[0]?.number,
        caseTitle: pickCase.name,
      }
    } else if (target === 'new' && contract === 'has') {
      assign = { target: 'new' }
    } else {
      // 只带上非空字段，别把空串塞给后端
      const contractFields: Record<string, string> = {}
      for (const [k, v] of Object.entries(fields)) {
        if (v.trim()) contractFields[k] = v.trim()
      }
      assign = { target: 'new', contractFields }
    }
    onConfirm(assign)
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="assign-modal-title"
        className="relative flex max-h-[86vh] w-full max-w-[620px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
      >
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 id="assign-modal-title" className="text-[15px] font-semibold">材料归属</h3>
          <button onClick={onCancel} aria-label="关闭" className="grid h-8 w-8 place-items-center rounded-lg text-secondary-foreground hover:bg-secondary">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-2 text-[12.5px] text-muted-foreground">
          {count} 份材料{who && <> · 委托人 {who}</>}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
          {/* 追加到已有案件 */}
          <label
            className={cn(
              'flex cursor-pointer gap-3 rounded-xl border p-3.5 transition-colors',
              target === 'existing' ? 'border-blue-300 bg-blue-50/40' : 'border-border hover:bg-secondary/50',
            )}
          >
            <input type="radio" name="t" checked={target === 'existing'} onChange={() => setTarget('existing')} className="mt-0.5" />
            <div>
              <div className="text-[13.5px] font-medium">追加到已有案件</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground">同一案子收到的新材料 —— 输入案号或当事人自己找</div>
            </div>
          </label>
          {target === 'existing' && (
            <div className="mt-2 rounded-xl border border-border bg-card p-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  autoFocus
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value)
                    setPickCase(null)
                  }}
                  placeholder="输入案号 / 当事人 / 案由"
                  className="h-9 w-full rounded-lg border border-input bg-background pl-8 pr-3 text-[13px] outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <div className="mt-2 max-h-[220px] overflow-y-auto">
                {loading && <div className="flex items-center gap-2 px-1 py-2 text-[12px] text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> 搜索中…</div>}
                {!q && <div className="px-1 py-2 text-[12px] text-muted-foreground">输入关键词后会在这里显示匹配的案件</div>}
                {q && !loading && cases.length === 0 && (
                  <div className="px-1 py-2 text-[12px] text-muted-foreground">没有匹配的案件 —— 换个关键词，或改用「新建案件」</div>
                )}
                {cases.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setPickCase(c)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-secondary',
                      pickCase?.id === c.id && 'bg-blue-50 ring-1 ring-blue-200',
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px]">{c.name}</span>
                    <span className="flex-none text-[11px] tabular-nums text-muted-foreground">
                      {c.filing_number || c.case_numbers?.[0]?.number || '无案号'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 新建案件 */}
          <label
            className={cn(
              'mt-2.5 flex cursor-pointer gap-3 rounded-xl border p-3.5 transition-colors',
              target === 'new' ? 'border-blue-300 bg-blue-50/40' : 'border-border hover:bg-secondary/50',
            )}
          >
            <input type="radio" name="t" checked={target === 'new'} onChange={() => setTarget('new')} className="mt-0.5" />
            <div>
              <div className="text-[13.5px] font-medium">新建案件</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground">这批材料属于一个新案子</div>
            </div>
          </label>
          {target === 'new' && (
            <div className="mt-2 rounded-xl border border-border bg-card p-3">
              <label className="flex items-center gap-2 text-[13px]">
                <input type="radio" name="c" checked={contract === 'has'} onChange={() => setContract('has')} />
                已有委托合同，直接建案
              </label>
              <div className="mt-2 rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-[12px] text-muted-foreground">
                合同检索为占位模块，后续接入真实合同库。现在就按「直接建案」处理。
              </div>

              <label className="mt-3 flex items-center gap-2 text-[13px]">
                <input type="radio" name="c" checked={contract === 'none'} onChange={() => setContract('none')} />
                还没有合同，先创建合同
              </label>
              {contract === 'none' && (
                <div className="mt-2 rounded-lg border border-border p-3">
                  <div className="mb-2 text-[12px] text-muted-foreground">生成委托合同要用到这些 —— 在这儿补就行，右栏没记也没关系。</div>
                  {['委托人', '对方当事人', '标的额'].map((k) => (
                    <label key={k} className="mb-2 flex items-center gap-2 text-[12.5px]">
                      <span className="w-[72px] flex-none">{k}</span>
                      <input
                        value={fields[k] ?? ''}
                        placeholder={k === '委托人' ? '姓名或单位' : '可以空'}
                        onChange={(e) => setField(k, e.target.value)}
                        className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-[13px] outline-none focus:border-blue-300"
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 底部 */}
        <div className="flex items-center gap-2 border-t border-border px-5 py-3.5">
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-muted-foreground">{why}</span>
          <Button variant="outline" size="sm" onClick={onCancel}>
            取消
          </Button>
          <Button size="sm" disabled={okDisabled} onClick={confirm}>
            确认并继续
          </Button>
        </div>
      </div>
    </div>
  )
}
