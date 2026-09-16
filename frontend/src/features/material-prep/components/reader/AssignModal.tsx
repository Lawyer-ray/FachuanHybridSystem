import { useEffect, useState } from 'react'
import { Loader2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { searchCases } from '../../api'
import type { AssignInfo, CaseRow, InfoField } from '../../types'
import { cn } from '@/lib/utils'

type Target = 'existing' | 'new'
type ContractOpt = 'has' | 'none'

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
  const [cases, setCases] = useState<CaseRow[]>([])
  const [loading, setLoading] = useState(false)
  const [pickCase, setPickCase] = useState<CaseRow | null>(null)
  const [resetter, setResetter] = useState(0)

  const who = infos.find((f) => f.k === '委托人')?.v || ''
  const [ctWho, setCtWho] = useState(who)

  useEffect(() => {
    if (!open) return
    setTarget('existing')
    setContract('has')
    setQ('')
    setCases([])
    setPickCase(null)
    setCtWho(infos.find((f) => f.k === '委托人')?.v || '')
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || target !== 'existing') return
    if (!q.trim()) {
      setCases([])
      setLoading(false)
      return
    }
    const t = setTimeout(() => {
      setLoading(true)
      searchCases(q)
        .then((rows) => {
          setCases(rows)
          setResetter((n) => n + 1)
        })
        .catch(() => toast.error('案件搜索失败，请检查后端'))
        .finally(() => setLoading(false))
    }, 220)
    return () => clearTimeout(t)
  }, [q, target, open])

  if (!open) return null

  const why =
    target === 'existing'
      ? pickCase
        ? '将追加到所选案件'
        : '先在上面选一个案件'
      : contract === 'none'
        ? ctWho.trim()
          ? '将据此生成委托合同'
          : '写个委托人就能生成合同'
        : '不用再填别的，直接建案'

  const okDisabled =
    (target === 'existing' && !pickCase) ||
    (target === 'new' && contract === 'none' && !ctWho.trim())

  void resetter

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
      assign = { target: 'new', contractFields: { 委托人: ctWho.trim() } }
    }
    onConfirm(assign)
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative flex max-h-[86vh] w-full max-w-[620px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 className="text-[15px] font-semibold">材料归属</h3>
          <button onClick={onCancel} className="grid h-8 w-8 place-items-center rounded-lg text-secondary-foreground hover:bg-secondary">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-2 text-[12.5px] text-muted-foreground">
          {count} 份材料 · {who && <>委托人 {who} · </>}还没记委托人
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
                  {['委托人', '对方当事人', '标的额'].map((k) => {
                    const val = k === '委托人' ? ctWho : infos.find((f) => f.k === k)?.v || ''
                    return (
                      <label key={k} className="mb-2 flex items-center gap-2 text-[12.5px]">
                        <span className="w-[72px] flex-none">{k}</span>
                        <input
                          value={val}
                          placeholder={k === '委托人' ? '姓名或单位' : '可以空'}
                          onChange={(e) => (k === '委托人' ? setCtWho(e.target.value) : undefined)}
                          className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-[13px] outline-none focus:border-blue-300"
                        />
                      </label>
                    )
                  })}
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
