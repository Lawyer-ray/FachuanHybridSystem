/**
 * 一个案件的**待裁决回传件**清单：客户把出站件签回来、系统比对正文后检出问题，
 * 律师在这里逐件裁决（采纳改动 = 放行，退回重签 = 让客户改了重签）。
 *
 * 为什么逐条列 findings 而不是只报一个状态：律师要判断的是「这个改动我认不认」，
 * 而状态标签只能说「有差异」。所以每条至少给出前三项（红线优先——后端已按 severity
 * 排过序，顺序不再重排），其余折成一句「还有 N 条」。
 *
 * 为什么裁决后要失效整个清单：后端「待裁决」的口径是「没有 accept/reject 裁决」，
 * 裁完这一条就该从清单里消失；本地删行只能骗自己，刷新回来还在。
 *
 * 组件自身不吞错：查询失败显示在区块内（不 toast，避免选中案件就弹一次），
 * 裁决失败用 `errMessage` 取后端原因后 toast（这是律师主动点的动作，必须给反馈）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import {
  decideRun,
  listPending,
  listUnverified,
  type DecisionAction,
  type FindingOut,
  type VerifyRunOut,
} from './api'

/** 每件最多摊开几条发现项：三条足够判断「这份到底改了什么」，再多就把清单变成一篇报告。 */
const FINDINGS_SHOWN = 3

/** 待裁决清单的 query key（裁决成功后按它失效重拉）。 */
function unverifiedKey(caseId: number | undefined) {
  return ['doc-verify-unverified', caseId ?? 'all'] as const
}

interface SeverityStyle {
  /** 给律师看的档位名，与后端 `domain/contracts.py` 的 Severity 一一对应 */
  label: string
  chip: string
  title: string
}

const SEVERITY_RED: SeverityStyle = {
  label: '红线',
  chip: 'bg-red-50 text-red-700 ring-red-200',
  title: 'text-red-700',
}
const SEVERITY_YELLOW: SeverityStyle = {
  label: '疑似',
  chip: 'bg-amber-50 text-amber-700 ring-amber-200',
  title: 'text-amber-800',
}
const SEVERITY_GRAY: SeverityStyle = {
  label: '无法核对',
  chip: 'bg-zinc-100 text-zinc-600 ring-zinc-200',
  title: 'text-zinc-600',
}

/**
 * severity → 展示样式。三档是三种处置（红线不得放行 / 疑似待确认 / 无法核对），
 * 不是三种装饰。未知值按 gray 渲染：把不认识的档位画成红线会制造假警报。
 */
function severityStyle(severity: string): SeverityStyle {
  if (severity === 'red') return SEVERITY_RED
  if (severity === 'yellow') return SEVERITY_YELLOW
  return SEVERITY_GRAY
}

/** 覆盖度（后端 `domain/compare.py` 写、`services/verify/query.py` 原样回传；缺键按「不知道」处理）。 */
interface PageCoverage {
  total: number | null
  withText: number | null
  noText: number
}

function countOf(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function pageCoverageOf(coverage: VerifyRunOut['coverage']): PageCoverage {
  const total = countOf(coverage.pages_total)
  const noText = countOf(coverage.pages_no_text)
  return {
    total,
    // 后端总会给 pages_with_text；缺的时候按总页数减缺文本页推，总页数也没有就承认不知道
    withText: countOf(coverage.pages_with_text) ?? (total != null && noText != null ? total - noText : null),
    noText: noText ?? 0,
  }
}

/**
 * 覆盖率一句话。
 *
 * `pages_no_text > 0` 必须显式写出来：那几页是图片/无文本层，比对根本没看到内容，
 * 只写「覆盖率 8/10 页」会让律师以为是随便抽了 8 页看看。
 */
function coverageTextOf(page: PageCoverage): string {
  if (page.total == null || page.withText == null) return '覆盖度：未知'
  const base = `覆盖率 ${page.withText}/${page.total} 页`
  return page.noText > 0 ? `${base} · ${page.noText} 页无文本层，未核对` : base
}

/** 一条发现项：档位徽标 + 标题 + `expected → actual`（后端为空串时不渲染箭头）。 */
function FindingLine({ finding }: { finding: FindingOut }) {
  const style = severityStyle(finding.severity)
  const pair =
    finding.expected || finding.actual
      ? `${finding.expected || '（空）'} → ${finding.actual || '（空）'}`
      : ''
  return (
    <div className="flex items-start gap-1.5 text-[11.5px] leading-relaxed">
      <span
        className={cn(
          'mt-px flex-none rounded px-1 text-[10px] leading-4 ring-1 ring-inset',
          style.chip,
        )}
      >
        {style.label}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn('font-medium', style.title)}>{finding.title}</span>
        {pair && <span className="ml-1 text-muted-foreground">{pair}</span>}
      </span>
    </div>
  )
}

/** 一件待裁决的回传件。 */
function RunRow({ run, caseId }: { run: VerifyRunOut; caseId: number | undefined }) {
  const queryClient = useQueryClient()
  const decide = useMutation({
    mutationFn: (action: DecisionAction) => decideRun(run.id, { action, reason: '' }),
    onSuccess: (_decision, action) => {
      toast.success(action === 'accept' ? '已采纳改动' : '已退回重签', {
        description: `「${run.doc_type}」已从待裁决清单移除`,
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
  const { data, error, isPending, isError } = useQuery({
    queryKey: unverifiedKey(caseId),
    // 给了 caseId 就只看该案；没给就是跨案件清单（后端按可见性收窄）。
    // 两条路径共用同一份行渲染与同一个裁决动作，避免「全局能看不能裁」的两套口径。
    queryFn: ({ signal }) => (scoped ? listUnverified(caseId, signal) : listPending(50, signal)),
  })

  return (
    <section aria-label="待裁决的回传件" className="rounded-xl border border-border bg-secondary/30 p-3">
      <div className="text-[12.5px] font-medium">{scoped ? '待裁决的回传件' : '全部待裁决的回传件'}</div>
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
      {data?.map((run) => <RunRow key={run.id} run={run} caseId={caseId} />)}
    </section>
  )
}
