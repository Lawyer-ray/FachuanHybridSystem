/**
 * 一个案件的**待裁决回传件**清单：客户把出站件签回来、系统比对正文后检出问题，
 * 律师在这里逐件裁决（采纳改动 = 放行，退回重签 = 让客户改了重签，要求重出 = 这版
 * 得由我方重新出）。也可以勾上几条一次批量处置。
 *
 * 为什么逐条列 findings 而不是只报一个状态：律师要判断的是「这个改动我认不认」，
 * 而状态标签只能说「有差异」。所以每条至少给出前三项（红线优先——后端已按 severity
 * 排过序，顺序不再重排），其余折成一句「还有 N 条」。
 *
 * 为什么裁决后要失效整个清单：后端「待裁决」的口径是「没有 accept/reject 裁决」，
 * 裁完这一条就该从清单里消失；本地删行只能骗自己，刷新回来还在。
 *
 * 为什么「要求重出」**不会**把这条从清单里拿掉：后端只把 accept/reject 当「已裁决」
 * （`services/verify/query.py` 的 DECIDED_ACTIONS）。客户会不会回传新版还不知道，
 * 这条仍在进行中，本地删行会让律师误以为已经了结。
 *
 * 批量的口径跟单条完全一样，只是逐条判：已裁决/不可见的条目只把自己算进 skipped 并
 * 写明原因、不会让整批失败——所以 toast 要把「处理几条、跳过几条、为什么」都说出来。
 *
 * 组件自身不吞错：查询失败显示在区块内（不 toast，避免选中案件就弹一次），
 * 裁决失败用 `errMessage` 取后端原因后 toast（这是律师主动点的动作，必须给反馈）。
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import {
  decideBatch,
  decideRun,
  listPending,
  listUnverified,
  type DecisionAction,
  type DecisionBatchOut,
  type VerifyRunOut,
} from './api'
import { coverageTextOf, pageCoverageOf } from './run-coverage'
import { FindingLine } from './run-display'

/** 每件最多摊开几条发现项：三条足够判断「这份到底改了什么」，再多就把清单变成一篇报告。 */
const FINDINGS_SHOWN = 3

/** 批量条只给两个**了结**动作：reissue 不把行拿掉，攒成一批没有意义。 */
type BatchAction = Extract<DecisionAction, 'accept' | 'reject'>

/** 裁决成功后的 toast 标题。reissue 不是了结动作，文案不能跟 accept/reject 共用一套。 */
const DECISION_DONE_LABEL: Record<DecisionAction, string> = {
  accept: '已采纳改动',
  reject: '已退回重签',
  reissue: '已要求重出',
}

/** `items[].skipped_reason` 的机器码（后端 `services/verify/decision.py`）→ 律师读得懂的原因。 */
const SKIP_REASON_LABEL: Record<string, string> = {
  ALREADY_DECIDED: '已有裁决',
  STATE_NOT_NEEDS_DECISION: '状态已不需要裁决',
  CASE_FORBIDDEN: '无权访问该案',
  RUN_NOT_FOUND: '核对记录不存在',
}

/** 跳过原因汇总成一句话；没有跳过时返回空串（不往 toast 里塞空描述）。 */
function skippedSummaryOf(items: DecisionBatchOut['items']): string {
  const counts = new Map<string, number>()
  for (const item of items) {
    const reason = typeof item.skipped_reason === 'string' ? item.skipped_reason : ''
    if (reason) counts.set(reason, (counts.get(reason) ?? 0) + 1)
  }
  return [...counts]
    .map(([reason, count]) => `${SKIP_REASON_LABEL[reason] ?? reason} ${count} 条`)
    .join('、')
}

/** 勾选/取消一条：返回新 Set，不就地改 state 里那个（React 看不见同一个引用的变化）。 */
function withToggled(prev: ReadonlySet<number>, id: number, next: boolean): ReadonlySet<number> {
  const copy = new Set(prev)
  if (next) copy.add(id)
  else copy.delete(id)
  return copy
}

/** 待裁决清单的 query key（裁决成功后按它失效重拉）。 */
function unverifiedKey(caseId: number | undefined) {
  return ['doc-verify-unverified', caseId ?? 'all'] as const
}

interface RunRowProps {
  run: VerifyRunOut
  caseId: number | undefined
  /** 勾选状态由父级持有：批量条要跨行统计 */
  checked: boolean
  onCheckedChange: (next: boolean) => void
}

/** 一件待裁决的回传件。 */
function RunRow({ run, caseId, checked, onCheckedChange }: RunRowProps) {
  const queryClient = useQueryClient()
  const decide = useMutation({
    mutationFn: (action: DecisionAction) => decideRun(run.id, { action, reason: '' }),
    onSuccess: (_decision, action) => {
      toast.success(DECISION_DONE_LABEL[action], {
        description:
          action === 'reissue'
            ? `「${run.doc_type}」仍在待裁决清单里，等客户回传新版`
            : `「${run.doc_type}」已从待裁决清单移除`,
      })
      void queryClient.invalidateQueries({ queryKey: unverifiedKey(caseId) })
    },
    onError: (error) => toast.error(`裁决失败：${errMessage(error, '未知错误')}`),
  })

  const shown = run.findings.slice(0, FINDINGS_SHOWN)
  const hidden = run.findings.length - shown.length

  return (
    <div className="mt-2 rounded-lg border border-border bg-card p-2.5">
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          className="flex-none"
          checked={checked}
          // 含文书名才能让读屏用户在几十条里分清勾的是哪一件
          aria-label={`选择「${run.doc_type}」（${run.inbound_file_name || '未命名回传件'}）`}
          onChange={(e) => onCheckedChange(e.target.checked)}
        />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{run.doc_type}</span>
        <span className="flex-none text-[11px] text-muted-foreground">{run.state_label}</span>
      </div>
      <div className="mt-0.5 text-[11.5px] text-muted-foreground">
        {coverageTextOf(pageCoverageOf(run.coverage))}
      </div>
      {shown.length > 0 && (
        <div className="mt-1.5 flex flex-col gap-1">
          {shown.map((finding, i) => (
            <FindingLine key={`${finding.code}-${finding.page ?? 'x'}-${i}`} finding={finding} />
          ))}
          {hidden > 0 && (
            <div className="text-[11px] text-muted-foreground">还有 {hidden} 条未显示</div>
          )}
        </div>
      )}
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" disabled={decide.isPending} onClick={() => decide.mutate('accept')}>
          采纳改动
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={decide.isPending}
          onClick={() => decide.mutate('reject')}
        >
          退回重签
        </Button>
        {/* 要求重出：这版由我方重新出。它不是了结动作（这条仍在清单里），用 ghost 弱化。 */}
        <Button
          size="sm"
          variant="ghost"
          disabled={decide.isPending}
          onClick={() => decide.mutate('reissue')}
        >
          要求重出
        </Button>
      </div>
    </div>
  )
}

/**
 * 某案件的待裁决清单。
 *
 * 空态写「本案没有待核对的回传件」而不是整块隐藏：律师在材料归属里选案件时，
 * 「这个案子有没有东西等着我」本身就是答案，缺了它律师会以为是没加载出来。
 */
export function PendingRuns({ caseId }: { caseId?: number }) {
  const scoped = caseId !== undefined
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<ReadonlySet<number>>(() => new Set<number>())
  const { data, error, isPending, isError } = useQuery({
    queryKey: unverifiedKey(caseId),
    // 给了 caseId 就只看该案；没给就是跨案件清单（后端按可见性收窄）。
    // 两条路径共用同一份行渲染与同一个裁决动作，避免「全局能看不能裁」的两套口径。
    queryFn: ({ signal }) => (scoped ? listUnverified(caseId, signal) : listPending(50, signal)),
  })

  // 数据刷新后把已不在清单里的 id 从选中集剔除：已被裁掉/别处已处置的行不该继续
  // 占着「已选 N 条」，否则下一批会把这些脏 id 再提交一遍（后端只会一条条跳过）。
  useEffect(() => {
    if (!data) return
    setSelected((prev) => {
      const visible = new Set(data.map((run) => run.id))
      const next = [...prev].filter((id) => visible.has(id))
      return next.length === prev.size ? prev : new Set(next)
    })
  }, [data])

  // 提交顺序按清单显示顺序：Set 的插入序随勾选先后变，同一批的 run_ids 每次都不一样。
  const selectedIds = data?.filter((run) => selected.has(run.id)).map((run) => run.id) ?? []
  const clearSelection = () => setSelected(new Set<number>())

  const batch = useMutation({
    mutationFn: (action: BatchAction) =>
      decideBatch({ run_ids: selectedIds, action, reason: '' }),
    onSuccess: (result, action) => {
      const skipped = skippedSummaryOf(result.items)
      toast.success(
        `${action === 'accept' ? '批量采纳完成' : '批量退回完成'}：已处理 ${result.decided} 条，跳过 ${result.skipped} 条`,
        { description: skipped || undefined },
      )
      clearSelection()
      void queryClient.invalidateQueries({ queryKey: unverifiedKey(caseId) })
    },
    onError: (error) => toast.error(`批量裁决失败：${errMessage(error, '未知错误')}`),
  })

  return (
    <section aria-label="待裁决的回传件" className="rounded-xl border border-border bg-secondary/30 p-3">
      <div className="text-[12.5px] font-medium">{scoped ? '待裁决的回传件' : '全部待裁决的回传件'}</div>
      {/* 批量条只在有选中时出现：常驻一条「已选 0 条」会让人以为默认全选。 */}
      {selectedIds.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5">
          <span className="text-[12px] font-medium tabular-nums">已选 {selectedIds.length} 条</span>
          <Button size="sm" disabled={batch.isPending} onClick={() => batch.mutate('accept')}>批量采纳</Button>
          <Button size="sm" variant="outline" disabled={batch.isPending} onClick={() => batch.mutate('reject')}>批量退回</Button>
          <Button size="sm" variant="ghost" disabled={batch.isPending} onClick={clearSelection}>取消选择</Button>
        </div>
      )}
      {isPending && (
        <div className="mt-1.5 flex items-center gap-2 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> 加载中…
        </div>
      )}
      {isError && (
        <div className="mt-1.5 text-[12px] text-muted-foreground">
          待裁决清单加载失败：{errMessage(error, '未知错误')}
        </div>
      )}
      {data?.length === 0 && (
        <div className="mt-1.5 text-[12px] text-muted-foreground">
          {scoped ? '本案没有待核对的回传件' : '没有待核对的回传件'}
        </div>
      )}
      {data?.map((run) => (
        <RunRow
          key={run.id}
          run={run}
          caseId={caseId}
          checked={selected.has(run.id)}
          onCheckedChange={(next) => setSelected((prev) => withToggled(prev, run.id, next))}
        />
      ))}
    </section>
  )
}
