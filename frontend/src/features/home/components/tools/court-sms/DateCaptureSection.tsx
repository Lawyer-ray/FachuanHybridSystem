import { CalendarPlus, Check, Loader2, RefreshCw, TriangleAlert } from 'lucide-react'

import { ROW_BTN } from '../../../ui'
import { cn } from '@/lib/utils'

import type { CaptureTask, UseDateCaptureResult } from './use-date-capture'

/** 识别任务状态的短标签（律师视角，不用内部状态名） */
function taskLabel(t: CaptureTask): string {
  if (t.status === 'pending' || t.status === 'processing') return '识别中'
  if (t.status === 'failed') return '识别失败'
  const pending = t.pending_count ?? 0
  const confirmed = t.confirmed_count ?? 0
  if (pending > 0) return `待确认 ${pending} 条日期`
  if (confirmed > 0) return `已写入日历 ${confirmed} 条`
  return '未识别到关键日期'
}

function dotClass(t: CaptureTask): string {
  if (t.status === 'pending' || t.status === 'processing') return 'bg-status-blue'
  if (t.status === 'failed') return 'bg-status-red'
  if ((t.pending_count ?? 0) > 0) return 'bg-status-yellow'
  if ((t.confirmed_count ?? 0) > 0) return 'bg-status-green'
  return 'bg-muted-foreground/40'
}

/**
 * 「送去记一笔」结果区：法院短信每份文书 → 独立的日期识别任务。
 *
 * 只**展示**识别结论 + 给「确认日期」入口；写入日历必须是律师在确认弹窗里
 * 逐条勾选（法律日期错一天的代价不可接受）。识别为空不算失败——直接告诉
 * 律师「这份文书没日期」，别让他以为坏了。
 */
export function DateCaptureSection({
  capture,
  onOpenTask,
  onRetry,
}: {
  capture: UseDateCaptureResult
  /** 打开某个识别任务的确认弹窗（多份文书时按任务逐个确认） */
  onOpenTask: (taskId: number) => void
  /** 重新识别：force 新建任务 */
  onRetry: () => void
}) {
  if (!capture.started) return null

  const tasks = capture.tasks
  const actionable = tasks.filter((t) => t.status === 'success' && (t.pending_count ?? 0) > 0)
  const failed = tasks.filter((t) => t.status === 'failed')
  const empty = tasks.filter(
    (t) => t.status === 'success' && (t.pending_count ?? 0) === 0 && (t.confirmed_count ?? 0) === 0,
  )

  // 什么都没送成（无文书 / 未绑定案件）——一句话说清，不占地方
  if (tasks.length === 0) {
    if (!capture.reason) return null
    return (
      <div className="rounded-[10px] border border-border bg-secondary/40 px-3 py-2 text-[11.5px] leading-relaxed text-muted-foreground">
        <span className="font-medium text-foreground">记一笔：</span>
        {capture.reason}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 rounded-[10px] border border-border bg-secondary/30 px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        {capture.running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-status-blue" />
        ) : (
          <CalendarPlus className="h-3.5 w-3.5 text-status-blue" />
        )}
        <span className="text-[11.5px] font-semibold">记一笔 · 关键日期</span>
        <span className="text-[10.5px] text-muted-foreground">
          {capture.running
            ? '正在识别文书里的开庭/举证/上诉等日期…'
            : actionable.length > 0
              ? '确认后写入案件日历'
              : '识别完成'}
        </span>
      </div>

      {tasks.map((t) => (
        <div key={t.task_id} className="flex items-center gap-2 rounded-[8px] bg-card/60 px-2.5 py-1.5">
          <span className={cn('h-1.5 w-1.5 flex-none rounded-full', dotClass(t))} />
          <span className="min-w-0 flex-1 truncate text-[11.5px]" title={t.document_name}>
            {t.document_name}
          </span>
          <span
            className={cn(
              'flex-none text-[11px]',
              t.status === 'failed' ? 'text-status-red' : 'text-muted-foreground',
            )}
          >
            {taskLabel(t)}
          </span>
          {(t.classification_hint || t.case_number) && (
            <span className="hidden flex-none text-[10px] text-muted-foreground/80 sm:inline">
              {t.classification_hint ? '类型依短信推定' : ''}
              {t.case_number ? ` ${t.case_number}` : ''}
            </span>
          )}
          {t.status === 'success' && (t.pending_count ?? 0) > 0 && (
            <button type="button" className={ROW_BTN} onClick={() => onOpenTask(t.task_id)}>
              <Check className="h-3 w-3" />
              确认日期
            </button>
          )}
        </div>
      ))}

      {/* 识别为空：不是错误，但律师要知道「这份文书确实没日期」，避免以为坏了 */}
      {!capture.running && empty.length > 0 && (
        <div className="text-[11px] leading-relaxed text-muted-foreground">
          有 {empty.length} 份文书没识别到关键日期（通知书/回证类常见），如确有关键日期可在首页「记一笔」手工录入。
        </div>
      )}

      {failed.length > 0 && (
        <div className="flex items-start gap-1.5 text-[11px] leading-relaxed text-status-red">
          <TriangleAlert className="mt-0.5 h-3 w-3 flex-none" />
          <span className="min-w-0 flex-1 break-words">
            {failed.length} 份识别失败：{failed[0]?.error_message || '未知原因'}
          </span>
        </div>
      )}

      {capture.reason && tasks.length > 0 && (
        <div className="text-[11px] text-muted-foreground">{capture.reason}</div>
      )}

      {!capture.running && (failed.length > 0 || (empty.length > 0 && (capture.reason ?? '') === '')) && (
        <button type="button" className={cn(ROW_BTN, 'self-start')} onClick={onRetry}>
          <RefreshCw className="h-3 w-3" />
          {failed.length > 0 ? '重新识别失败的文书' : '再识别一次'}
        </button>
      )}
    </div>
  )
}
