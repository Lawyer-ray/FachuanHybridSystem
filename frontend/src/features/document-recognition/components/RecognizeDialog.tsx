import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, FileText, Loader2, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

import { confirmDates, revokeDate } from '../api'
import { resolveMediaUrl, rowsFromTask, selectedPendingRows, selectedTextRows, type CandidateRow } from '../domain'
import { useRecognize } from '../hooks/use-recognize'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { CaseBindingSection } from './CaseBindingSection'
import { DateCandidateList } from './DateCandidateList'
import { DocumentPreview } from './DocumentPreview'
import { RecognitionProgress } from './RecognitionProgress'
import { RecognitionSummary } from './RecognitionSummary'

interface Props {
  open: boolean
  onClose: () => void
  /** 日历等外部状态刷新（确认写入成功后调用） */
  onSaved: () => void
  /** 文件模式：要识别的文书 */
  file: File | null
  /** 文字模式：/reminders/parse 的候选行 + 创建回调（由 home 注入，避免反向依赖） */
  textRows?: CandidateRow[]
  onConfirmText?: (rows: CandidateRow[]) => Promise<number>
}

/**
 * 记一笔的「识别并确认」弹窗。
 *
 * 文件模式：上传 → 轮询识别 → 第 1 步案件绑定（可跳过）→ 第 2 步日期候选
 * 逐条人工确认 → 写入重要日期提醒（绑定了挂案件日志，没绑创建独立提醒）。
 * 文字模式：parse 出的全部候选进同一套确认 UI，逐条走 /reminders/create。
 */
export function RecognizeDialog({ open, onClose, onSaved, file, textRows, onConfirmText }: Props) {
  const isFileMode = file !== null
  const { phase, hint, error, task, submit, refresh, reset } = useRecognize()
  const submittedFile = useRef<File | null>(null)
  const [busy, setBusy] = useState(false)

  // 文件模式：open 时提交一次（同一文件不重复提交）
  useEffect(() => {
    if (!open || !file || submittedFile.current === file) return
    submittedFile.current = file
    void submit(file)
  }, [open, file, submit])

  useEffect(() => {
    if (!open) {
      submittedFile.current = null
      reset()
    }
  }, [open, reset])

  // 候选行：base 由任务候选签名驱动（绑定刷新不冲掉本地编辑，仅状态变化时重建）
  const candidateSignature = useMemo(
    () => (task?.date_candidates ?? []).map((c) => `${c.id}:${c.status}`).join('|'),
    [task],
  )
  const baseRows = useMemo(
    () => (isFileMode && task ? rowsFromTask(task) : (textRows ?? [])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [candidateSignature, textRows, isFileMode],
  )
  const [overrides, setOverrides] = useState<Record<string, Partial<CandidateRow>>>({})
  useEffect(() => setOverrides({}), [candidateSignature, textRows])
  const rows = useMemo(
    () => baseRows.map((r) => (overrides[r.key] ? { ...r, ...overrides[r.key] } : r)),
    [baseRows, overrides],
  )

  const writableCount = isFileMode ? selectedPendingRows(rows).length : selectedTextRows(rows).length
  const recognition = task?.recognition
  const showProgress = isFileMode && (phase === 'submitting' || phase === 'polling')
  const showError = isFileMode && phase === 'error'
  // 文字模式无识别阶段，直接进确认；文件模式等识别 ready
  const contentReady = !isFileMode || phase === 'ready'

  const doConfirm = async () => {
    if (busy) return
    if (writableCount === 0) {
      toast.info('请先勾选要写入的日期')
      return
    }
    setBusy(true)
    try {
      if (isFileMode && task) {
        const items = selectedPendingRows(rows).map((r) => ({
          candidate_id: r.candidateId as number,
          action: 'confirm' as const,
          // datetime-local 原文（naive 本地）上送，服务端补时区——不能 toISOString
          due_at: r.dueLocal,
          reminder_type: r.reminderType,
        }))
        const res = await confirmDates(task.task_id, items)
        const errors = res.results.filter((x) => x.status === 'error')
        if (errors.length) {
          toast.warning(`${errors.length} 条未写入：${errors[0]?.message ?? '未知原因'}`)
        } else {
          const reused = res.results.filter((x) => x.message.includes('复用')).length
          toast.success(`已写入 ${res.results.length} 条提醒${reused ? `（${reused} 条复用了既有提醒）` : ''}`)
        }
        await refresh()
        onSaved()
      } else if (onConfirmText) {
        const created = await onConfirmText(selectedTextRows(rows))
        toast.success(`已加入日历 ${created} 条`)
        onClose()
        onSaved()
      }
    } catch (e) {
      toast.error(errMessage(e, '写入失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  const doSkip = async (row: CandidateRow) => {
    if (!task || busy || row.candidateId == null) return
    setBusy(true)
    try {
      await confirmDates(task.task_id, [{ candidate_id: row.candidateId, action: 'skip' }])
      await refresh()
    } catch (e) {
      toast.error(errMessage(e, '操作失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  const doRevoke = async (row: CandidateRow) => {
    if (!task || busy || row.candidateId == null) return
    setBusy(true)
    try {
      await revokeDate(task.task_id, row.candidateId)
      toast.success('已撤销并删除该条提醒')
      await refresh()
      onSaved()
    } catch (e) {
      toast.error(errMessage(e, '撤销失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  const previewUrl = isFileMode && task?.file_url ? resolveMediaUrl(task.file_url) : ''
  const hasPreview = Boolean(previewUrl)
  const fileUrl = hasPreview ? previewUrl : isFileMode && task?.file_url ? task.file_url : ''

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="flex max-h-[88vh] w-full flex-col gap-0 overflow-x-hidden overflow-y-auto p-6 sm:max-w-[560px] lg:h-[88vh] lg:max-w-[1120px] lg:overflow-hidden">
        <DialogHeader className="shrink-0 pb-2">
          <DialogTitle className="flex min-w-0 items-start gap-2 text-[15px]">
            <FileText className="mt-0.5 h-4 w-4 flex-none text-muted-foreground" />
            <span className="min-w-0 break-all">{file ? file.name : '文字记一笔 · 确认日期'}</span>
          </DialogTitle>
          <DialogDescription className="text-[12px]">
            只有确认过的日期才会写入重要日期提醒
          </DialogDescription>
        </DialogHeader>

        {showProgress && (
          <RecognitionProgress
            phase={phase === 'submitting' ? 'submitting' : 'polling'}
            fileName={file?.name ?? '文书'}
            hint={hint}
          />
        )}

        {showError && (
          <div className="flex flex-col items-center gap-3 py-10">
            <TriangleAlert className="h-6 w-6 text-status-red" />
            <span className="text-[12.5px] text-muted-foreground">{error}</span>
            <Button variant="outline" size="sm" onClick={onClose}>
              关闭
            </Button>
          </div>
        )}

        {contentReady && (
          // lg 双栏：左文书原文（独立滚动）/ 右确认步骤；窄屏单栏整体滚动
          <div className="grid min-h-0 flex-1 gap-3.5 pt-1 lg:grid-cols-[minmax(0,44%)_minmax(0,1fr)] lg:overflow-hidden">
            {hasPreview && <DocumentPreview url={previewUrl} className="hidden animate-in fade-in slide-in-from-left-2 duration-300 lg:flex" />}

            <div
              className={cn(
                'flex animate-in fade-in flex-col gap-3.5 duration-300 lg:min-h-0 lg:overflow-y-auto lg:pr-1',
                !hasPreview && 'w-full',
              )}
            >
              {isFileMode && task && recognition && <RecognitionSummary task={task} recognition={recognition} />}

              {isFileMode && task && <CaseBindingSection task={task} onBound={refresh} />}

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-semibold">
                    {isFileMode ? '第 2 步 · 确认关键日期' : '确认日期'}
                  </span>
                  {rows.length > 0 && (
                    <span className="text-[11px] text-muted-foreground">
                      {rows.filter((r) => r.status === 'confirmed').length}/{rows.length} 已确认
                    </span>
                  )}
                </div>
                <DateCandidateList
                  rows={rows}
                  interactive={isFileMode}
                  busy={busy}
                  onToggle={(key) => {
                    const row = rows.find((r) => r.key === key)
                    if (row) setOverrides((prev) => ({ ...prev, [key]: { checked: !row.checked } }))
                  }}
                  onPatch={(key, patch) => setOverrides((prev) => patchRowWithOverride(prev, key, patch))}
                  onSkip={doSkip}
                  onRevoke={doRevoke}
                />
                {rows.length > 0 && rows.every((r) => r.status !== 'pending') && (
                  <span className="text-center text-[11.5px] text-status-green">全部处理完成</span>
                )}
              </div>
            </div>
          </div>
        )}

        {contentReady && (
          <DialogFooter className="mt-3 shrink-0 gap-2 border-t border-border pt-3">
            <span className="mr-auto text-[11px] text-muted-foreground">
              {isFileMode && task && !task.binding?.success ? '未关联案件，将创建独立提醒' : ''}
            </span>
            {!hasPreview && fileUrl && (
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
              >
                <ExternalLink className="h-3 w-3" />
                查看文书
              </a>
            )}
            <Button variant="outline" onClick={onClose} disabled={busy}>
              关闭
            </Button>
            <Button onClick={doConfirm} disabled={busy || writableCount === 0} className={cn(busy && 'opacity-80')}>
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              写入 {writableCount} 条提醒
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

function patchRowWithOverride(
  prev: Record<string, Partial<CandidateRow>>,
  key: string,
  patch: Partial<CandidateRow>,
): Record<string, Partial<CandidateRow>> {
  return { ...prev, [key]: { ...(prev[key] ?? {}), ...patch } }
}
