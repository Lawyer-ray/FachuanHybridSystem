import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import type { FolderOwnerKind } from '../../api'
import { FindingRow } from './FindingRow'
import { JurisdictionSelect } from './JurisdictionSelect'
import {
  JURISDICTION_CN,
  REJECT_REASONS,
  SEVERITY_LABEL,
  STAGE_LABEL,
  bulkAccept,
  decideFinding,
  fetchLatestRun,
  labelOf,
  startReview,
  type FindingItem,
  type FindingStage,
  type ReviewRunPayload,
  type Severity,
} from './doc-review-api'

/**
 * 右栏风险清单：审查结论的**决策台**。
 *
 * ## 三个「不这么做就会坏」的设计
 *
 * 1. **清单不离开文档**：结论锚在 `quote` 上，点一条就调插件 `locate` 在画布里
 *    定位高亮。锚点失效的条目会显示成「锚点失效」并且**不允许再点采纳**——
 *    否则就是拿一段已经不存在的话去改文件。
 * 2. **驳回必须选理由码**：自由文本没法统计误报率，也给不了「同类条款降权」。
 * 3. **批量采纳必须二次确认**：落笔即写文件，一次误点等于几十条修订同时落下去；
 *    撤销只能走版本回滚。
 *
 * ## 两个分组维度
 *
 * 默认按 severity：律师的时间几乎全花在「高危」上，按档批量采纳能先把低危清掉。
 * 另一个维度是阶段：按转让前/中/后/通用看，某个阶段 0 条本身就是「该阶段查过了」
 * 的覆盖证明，所以空阶段也要出一行分组头，不能因为空就藏掉。
 */

const SEVERITY_ORDER: Severity[] = ['high', 'medium', 'low']
/** 阶段分组的固定顺序（转让前 → 转让中 → 转让后 → 通用），空阶段也列。 */
const STAGE_ORDER: FindingStage[] = ['before', 'during', 'after', 'general']

type GroupMode = 'severity' | 'stage'

const GROUP_TABS: { key: GroupMode; label: string }[] = [
  { key: 'severity', label: '严重度' },
  { key: 'stage', label: '阶段' },
]

const SEVERITY_TONE: Record<Severity, string> = {
  high: 'bg-status-red/10 text-status-red border-status-red/25',
  medium: 'bg-status-yellow/10 text-status-yellow border-status-yellow/25',
  low: 'bg-secondary text-muted-foreground border-border',
}

const STAGE_TONE = 'bg-secondary text-secondary-foreground border-border'

interface ReviewGroup {
  key: string
  label: string
  tone: string
  items: FindingItem[]
  /** 只有严重度分组支持整档批量采纳（阶段分组不提供，避免一次写几十条） */
  bulkSeverity?: Severity
}

export function ReviewPanel({
  kind,
  ownerId,
  subpath,
  selection,
  onLocate,
  onOpenDoc,
  onChanged,
}: {
  kind: FolderOwnerKind
  ownerId: number
  subpath: string
  /** 画布里当前框选的文字（用于反查对应条目） */
  selection: string
  /** 把某条结论的原文送进画布定位 */
  onLocate: (finding: FindingItem) => void
  /** 文件被改过之后刷新外层（文件夹 mtime / 画布） */
  onChanged?: () => void
  onOpenDoc?: () => void
}) {
  const qc = useQueryClient()
  const [runId, setRunId] = useState<number | null>(null)
  const [rejecting, setRejecting] = useState<FindingItem | null>(null)
  const [rejectCode, setRejectCode] = useState('commercial')
  const [rejectNote, setRejectNote] = useState('')
  const [bulk, setBulk] = useState<Severity | 'all' | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [groupMode, setGroupMode] = useState<GroupMode>('severity')
  // 法域默认中国法；切过一次之后跟随最近一轮的记忆值，免得「上次按泰国法审过，这次悄悄按中国法重审」
  const [jurisdiction, setJurisdiction] = useState<string>(JURISDICTION_CN)
  const [jurisdictionTouched, setJurisdictionTouched] = useState(false)

  const latestKey = ['doc-review', 'latest', kind, ownerId, subpath] as const

  const latest = useQuery({
    queryKey: latestKey,
    queryFn: () => fetchLatestRun(kind, ownerId, subpath),
    // 审查在后台跑：排队/执行中每 2 秒拉一次，结束后停
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 2000 : false
    },
  })

  const run: ReviewRunPayload | undefined = latest.data
  useEffect(() => {
    if (jurisdictionTouched) return
    if (run?.jurisdiction) setJurisdiction(run.jurisdiction)
  }, [run?.jurisdiction, jurisdictionTouched])
  const activeRunId = runId ?? run?.id ?? null
  const running = run?.status === 'queued' || run?.status === 'running'

  const start = useMutation({
    mutationFn: () => startReview(kind, ownerId, subpath, { jurisdiction }),
    onSuccess: (data) => {
      setRunId(data.run_id)
      if (!data.queued && data.hint) toast.warning(data.hint)
      else toast.success('已开始审查', { description: '出结果后右栏会自动出现清单' })
      void qc.invalidateQueries({ queryKey: latestKey })
    },
    onError: (error) => toast.error(errMessage(error, '审查失败，请稍后重试')),
  })

  const decide = useMutation({
    mutationFn: (input: { id: number; action: 'accept' | 'reject' | 'moot'; reasonCode?: string; note?: string }) =>
      decideFinding(input.id, input.action, { reasonCode: input.reasonCode, note: input.note }),
    onSuccess: (result, input) => {
      setBusyId(null)
      if (input.action === 'accept' && !result.ok) {
        // 锚点失效是最需要说清楚的一种失败：文件没动，需要重新框选
        toast.warning(result.stale ? '锚点已失效，本次未改动文件' : result.reason || '未落笔', {
          description: result.stale ? '这段原文已不在文档里，请重新框选后再试' : undefined,
        })
      } else {
        toast.success(input.action === 'accept' ? '已采纳并写入文件' : '已记录决策')
      }
      void qc.invalidateQueries({ queryKey: latestKey })
      onChanged?.()
    },
    onError: (error) => {
      setBusyId(null)
      toast.error(errMessage(error, '决策没有保存，请重试'))
    },
  })

  const runBulk = useMutation({
    mutationFn: (severity: Severity | '') => {
      if (activeRunId == null) throw new Error('还没有可决策的审查轮次')
      return bulkAccept(activeRunId, { severity })
    },
    onSuccess: (result) => {
      setBulk(null)
      toast.success(`批量采纳完成：${result.accepted} 条`, {
        description: result.stale ? `另有 ${result.stale} 条锚点失效、未改动文件` : undefined,
      })
      void qc.invalidateQueries({ queryKey: latestKey })
      onChanged?.()
    },
    onError: (error) => {
      setBulk(null)
      toast.error(errMessage(error, '批量采纳失败，请检查文件是否被占用'))
    },
  })

  const groups = useMemo<ReviewGroup[]>(() => {
    const items = run?.findings ?? []
    if (groupMode === 'stage') {
      // 老轮次没有 stage、或后端新增了未知阶段：一律归到「通用」，不能从清单里消失
      const stageOf = (f: FindingItem): FindingStage =>
        f.stage && STAGE_ORDER.includes(f.stage) ? f.stage : 'general'
      return STAGE_ORDER.map((stage) => ({
        key: stage,
        label: labelOf(STAGE_LABEL, stage),
        tone: STAGE_TONE,
        items: items.filter((f) => stageOf(f) === stage),
      }))
    }
    return SEVERITY_ORDER.map((severity) => ({
      key: severity,
      label: `${SEVERITY_LABEL[severity]}危`,
      tone: SEVERITY_TONE[severity],
      items: items.filter((f) => f.severity === severity),
      bulkSeverity: severity,
    })).filter((g) => g.items.length > 0)
  }, [run, groupMode])

  /** 画布里框选的文字 → 命中的条目（双向定位的另一半）。 */
  const highlighted = useMemo(() => {
    const probe = selection.trim()
    if (!probe) return null
    const items = run?.findings ?? []
    return (
      items.find((f) => f.quote && (f.quote.includes(probe) || probe.includes(f.quote))) ??
      items.find((f) => f.suggestion_original && (f.suggestion_original.includes(probe) || probe.includes(f.suggestion_original))) ??
      null
    )
  }, [selection, run])

  const proposedCount = (run?.findings ?? []).filter((f) => f.status === 'proposed').length

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex flex-none items-center gap-2 border-b border-border px-3 py-2">
        <Sparkles className="size-3.5 text-muted-foreground" />
        <p className="text-[12.5px] font-[650]">风险清单</p>
        {proposedCount > 0 && (
          <span className="rounded-full bg-status-yellow/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-status-yellow">
            {proposedCount} 待决
          </span>
        )}
        <div className="flex-1" />
        <JurisdictionSelect
          value={jurisdiction}
          disabled={running}
          onChange={(next) => {
            setJurisdictionTouched(true)
            setJurisdiction(next)
          }}
        />
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending || running}
          className="inline-flex h-[26px] items-center gap-1 rounded-[7px] bg-foreground px-2 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
        >
          {running ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />}
          {running ? '审查中…' : run?.status === 'done' ? '重新审查' : 'AI 审查'}
        </button>
      </div>

      {(run?.findings?.length ?? 0) > 0 && (
        <div className="flex flex-none items-center border-b border-border px-3 py-1.5">
          <div role="tablist" aria-label="清单分组" className="flex gap-[2px] rounded-[7px] bg-secondary/60 p-[2px]">
            {GROUP_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={groupMode === tab.key}
                onClick={() => setGroupMode(tab.key)}
                className={cn(
                  'rounded-[5px] px-2 py-[2px] text-[10.5px] font-medium transition-colors',
                  groupMode === tab.key
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {latest.isLoading && (
          <p className="px-1 py-6 text-center text-[11.5px] text-muted-foreground">正在读取清单…</p>
        )}

        {!latest.isLoading && run?.status === 'none' && (
          <div className="px-2 py-8 text-center">
            <p className="text-[12px] text-muted-foreground">这份文件还没审查过</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              点上方「AI 审查」。审查结果会以修订和批注直接落在这份文件上，不产生第二份文档。
            </p>
          </div>
        )}

        {run?.status === 'failed' && (
          <div className="mx-1 mb-2 rounded-[8px] border border-status-red/30 bg-status-red/5 px-2 py-2">
            <p className="text-[11.5px] font-semibold text-status-red">审查失败</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{run.error_message || '模型没有返回结果'}</p>
          </div>
        )}

        {highlighted && (
          <div className="mx-1 mb-2 rounded-[8px] border border-primary/30 bg-primary/5 px-2 py-1.5">
            <p className="text-[11px] text-primary">
              画布选区命中了清单条目：<span className="font-semibold">{highlighted.title}</span>
            </p>
          </div>
        )}

        {groups.map((group) => (
          <div key={group.key} className="mb-2">
            <div className="flex items-center gap-1.5 px-1 py-1">
              <span
                className={cn('rounded-[5px] border px-1.5 py-0.5 text-[10.5px] font-semibold', group.tone)}
              >
                {group.label}
              </span>
              <span className="text-[10.5px] text-muted-foreground">{group.items.length} 条</span>
              {groupMode === 'stage' && group.items.length === 0 && (
                <span className="text-[10.5px] text-muted-foreground">本阶段无结论</span>
              )}
              <div className="flex-1" />
              {group.bulkSeverity && group.items.some((f) => f.status === 'proposed') && (
                <button
                  type="button"
                  onClick={() => setBulk(group.bulkSeverity ?? null)}
                  className="text-[10.5px] font-[550] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  全部采纳
                </button>
              )}
            </div>

            {group.items.map((finding) => (
              <FindingRow
                key={finding.id}
                finding={finding}
                busy={busyId === finding.id}
                active={highlighted?.id === finding.id}
                onLocate={() => onLocate(finding)}
                onAccept={() => {
                  setBusyId(finding.id)
                  decide.mutate({ id: finding.id, action: 'accept' })
                }}
                onReject={() => {
                  setRejecting(finding)
                  setRejectCode('commercial')
                  setRejectNote('')
                }}
                onMoot={() => {
                  setBusyId(finding.id)
                  decide.mutate({ id: finding.id, action: 'moot' })
                }}
              />
            ))}
          </div>
        ))}

        {run?.status === 'done' && (run.findings?.length ?? 0) === 0 && (
          <p className="px-2 py-8 text-center text-[11.5px] text-muted-foreground">
            没有发现需要处理的问题。这只代表没发现，不等于没有风险。
          </p>
        )}
      </div>

      {onOpenDoc && (
        <div className="flex-none border-t border-border px-3 py-1.5">
          <button
            type="button"
            onClick={onOpenDoc}
            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            打开文档对照阅读 <ChevronRight className="size-3" />
          </button>
        </div>
      )}

      {/* 逐条驳回：理由码必选 */}
      <AlertDialog open={rejecting !== null} onOpenChange={(open) => !open && setRejecting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>驳回这条建议</AlertDialogTitle>
            <AlertDialogDescription>{rejecting?.title}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <select
              aria-label="驳回理由"
              value={rejectCode}
              onChange={(e) => setRejectCode(e.target.value)}
              className="h-[32px] w-full rounded-[8px] border border-border bg-background px-2 text-[12.5px]"
            >
              {REJECT_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <input
              aria-label="补充说明"
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              placeholder="补充说明（可选）"
              className="h-[32px] w-full rounded-[8px] border border-border bg-background px-2 text-[12.5px]"
            />
            <p className="text-[11px] text-muted-foreground">
              选「误报」会进入 AI 误报率统计；选其他会进入「同类条款降权」。
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!rejecting) return
                setBusyId(rejecting.id)
                decide.mutate({
                  id: rejecting.id,
                  action: 'reject',
                  reasonCode: rejectCode,
                  note: rejectNote,
                })
                setRejecting(null)
              }}
            >
              确认驳回
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 批量采纳：不可撤销，必须二次确认 */}
      <AlertDialog open={bulk !== null} onOpenChange={(open) => !open && setBulk(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              批量采纳{bulk === 'all' ? '全部' : bulk ? SEVERITY_LABEL[bulk] : ''}危建议？
            </AlertDialogTitle>
            <AlertDialogDescription>
              会把这一档的待决结论**全部写进文件**（修订 / 批注）。这一步不可撤销，
              出问题只能靠版本历史回滚。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => runBulk.mutate(bulk === 'all' ? '' : (bulk ?? ''))}>
              确认写入文件
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
