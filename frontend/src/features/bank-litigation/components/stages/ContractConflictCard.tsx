/**
 * ④ 文书 —— OA 利益冲突检索结果
 *
 * 六方检索结果 + 红色冲突横幅 + 「导出利冲报告」。
 * 导出要**走一段进度**才落 PDF：律师交出去的是一份可归档的审查报告，
 * 不是截个图 —— 报告里有编号、检索库、判定依据和结论。
 */

import { AlertTriangle, CheckCircle2, FileText, ShieldAlert } from 'lucide-react'

import { DEMO_CONFLICT_HITS } from '../demo-data'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

/** 导出进度：复用 useStageAction 的三个字段，不引入新状态机 */
export interface ConflictReportExport {
  phase: 'idle' | 'running' | 'awaiting' | 'done' | 'failed'
  percent: number
  progress: string
  /** 生成好的 PDF 文件名，null = 还没生成 */
  report: string | null
  onExport: () => void
}

export function ConflictCard({
  exportState,
  onOpenHit,
}: {
  exportState: ConflictReportExport
  onOpenHit: (key: string) => void
}) {
  const red = DEMO_CONFLICT_HITS.filter((h) => h.level === 'red')
  const { phase, percent, progress, report, onExport } = exportState

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <ShieldAlert className="size-3.5 flex-none text-muted-foreground" />
        <SectionTitle
          title="OA 利益冲突检索"
          hint="机器人登录 OA 当事人库逐方比对"
          className="w-full"
          action={
            <ActionButton sm disabled={phase === 'running'} onClick={onExport}>
              {phase === 'running' ? '生成中…' : report ? '重新导出' : '导出利冲报告'}
            </ActionButton>
          }
        />
      </div>

      {phase === 'running' ? (
        <div className="border-b border-border-light px-5 py-2">
          <div className="h-1 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-foreground transition-[width] duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">{progress}</div>
        </div>
      ) : null}

      {report ? (
        <div className="flex items-center gap-2 border-b border-border-light bg-status-green-bg/40 px-5 py-2 text-[10.5px] text-status-green">
          <FileText className="size-3 flex-none" />
          已生成 PDF：{report}
        </div>
      ) : null}

      {red.length > 0 ? (
        <div className="border-b border-border-light bg-status-red-bg/50 px-5 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-red" />
            <div className="min-w-0">
              <div className="text-[12px] font-semibold text-status-red">
                命中 {red.length} 处红色冲突 · 已自动阻断立案
              </div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-status-red/90">
                {red[0]!.detail}。同一自然人在对方阵营，按执业规范必须停止。
                机器人已停在利冲结果页，未继续建卷。
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <ul className="divide-y divide-border-light">
        {DEMO_CONFLICT_HITS.map((h, i) => (
          <li
            key={`${h.subject}-${i}`}
            onClick={() => onOpenHit(`${h.subject}-${i}`)}
            className="flex cursor-pointer items-center gap-3 px-5 py-2.5 transition-colors hover:bg-secondary/40"
          >
            <span
              className={cn(
                'grid size-4 flex-none place-items-center rounded-full',
                h.level === 'red'
                  ? 'bg-status-red'
                  : h.level === 'yellow'
                    ? 'bg-status-yellow'
                    : 'bg-status-green',
              )}
            >
              {h.level === 'clear' ? (
                <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
              ) : (
                <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
              )}
            </span>
            <span className="w-[140px] flex-none truncate text-[12px]" title={h.subject}>
              {h.subject}
            </span>
            <Pill>{h.role}</Pill>
            <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={h.detail}>
              {h.detail}
            </span>
            <Pill tone={h.level === 'red' ? 'red' : h.level === 'yellow' ? 'yellow' : 'green'}>
              {h.level === 'red' ? '冲突' : h.level === 'yellow' ? '复核' : '无冲突'}
            </Pill>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}
