import { useEffect, useRef } from 'react'
import { FileText, Loader2, TriangleAlert } from 'lucide-react'

import { selectedPendingRows, selectedTextRows, type CandidateRow } from '../domain'
import { useMediaUrlWithAuth } from '../hooks/use-media-url-with-auth'
import { useRecognize } from '../hooks/use-recognize'
import { useCandidateRows } from '../hooks/use-candidate-rows'
import { useConfirmActions } from '../hooks/use-confirm-actions'
import { useDialogWidthDrag, useSplitDrag } from '../hooks/use-split-drag'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

import { RecognitionProgress } from './RecognitionProgress'
import { RecognizeFooter } from './RecognizeFooter'
import { RecognizeSplitPane } from './RecognizeSplitPane'

interface Props {
  open: boolean
  onClose: () => void
  /** 日历等外部状态刷新（确认写入成功后调用） */
  onSaved: () => void
  /** 文件模式：要识别的文书 */
  file: File | null
  /**
   * 法院短信旁线：跟进一个后端**已存在**的识别任务（不重传文件）。
   * 与 `file` 二选一：给了 taskId 就只轮询 + 确认，案件已由短信侧绑定。
   */
  taskId?: number | null
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
 *
 * 法院短信旁线（传 taskId）：跳过上传，直接接管后端已派发的任务。这时案件/日志
 * 由短信侧绑定，**不展示案件选择**——日期写到哪份日历不能在同一张弹窗里被改成别的。
 */
export function RecognizeDialog({ open, onClose, onSaved, file, taskId, textRows, onConfirmText }: Props) {
  const isAttached = taskId != null
  const isFileMode = file !== null || isAttached
  const { phase, hint, error, task, progress, submit, attach, retry, canRetry, retrying, refresh, reset } =
    useRecognize()
  const submittedFile = useRef<File | null>(null)

  // 文件模式：open 时提交一次（同一文件不重复提交）
  useEffect(() => {
    if (!open || !file || submittedFile.current === file) return
    submittedFile.current = file
    void submit(file)
  }, [open, file, submit])

  // 旁线：接管已有任务（换短信/换任务号时重新接管，同号不重复开轮询）
  useEffect(() => {
    if (!open || taskId == null) return
    void attach(taskId)
  }, [open, taskId, attach])

  useEffect(() => {
    if (!open) {
      submittedFile.current = null
      reset()
    }
  }, [open, reset])

  const { rows, setOverrides } = useCandidateRows(isFileMode, task, textRows)
  const { busy, doConfirm, doSkip, doRevoke } = useConfirmActions({
    isFileMode,
    task,
    rows,
    onSaved,
    onClose,
    onConfirmText,
    refresh,
  })

  const writableCount = isFileMode ? selectedPendingRows(rows).length : selectedTextRows(rows).length
  const recognition = task?.recognition
  const showProgress = isFileMode && (phase === 'submitting' || phase === 'polling')
  const showError = isFileMode && phase === 'error'
  // 文字模式无识别阶段，直接进确认；文件模式等识别 ready
  const contentReady = !isFileMode || phase === 'ready'

  // 预览 URL 带下载票据（安全审计 M-2）：<img>/<iframe> 带不上 Authorization 头，
  // 且 JWT 不再允许走 ?token=（会进 access log / Referer）。票据换取是异步的，
  // 由 hook 按 file_url 变化重新取。
  const { url: previewUrl, failed: previewFailed } = useMediaUrlWithAuth(isFileMode ? task?.file_url : null)
  // 换票失败时 previewUrl 可能非空但不带票据（必然 403），此时不应进入分屏态
  const hasPreview = Boolean(previewUrl) && !previewFailed
  // 分屏态 = 识别完成且有原文可预览；等待/错误/文字模式保持紧凑小窗
  const splitReady = contentReady && hasPreview

  // 左栏宽度可拖拽（默认 52%，32–70%，localStorage 记忆）
  const [splitPct, startDragSplit, splitBodyRef, draggingSplit] = useSplitDrag()
  // 弹窗整体宽度可拖拽（960px–视口-32，localStorage 记忆；null = CSS 默认）
  const [dialogWidth, startDragDialog, draggingDialog] = useDialogWidthDrag()
  const resizing = draggingSplit || draggingDialog

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        // 宽度走 CSS 变量、只在 lg 断点生效（<lg 单栏永远 560px，不被历史宽度撑爆）。
        // 拖拽中 useDialogWidthDrag 直接改这个变量（零 setState），松手才提交 state；
        // 没有记忆宽度时变量的初值就是自适应宽 min(95vw, 视口-48px)。
        style={
          splitReady
            ? ({
                '--dr-dialog-w': dialogWidth != null ? `${dialogWidth}px` : 'min(95vw, calc(100vw - 48px))',
              } as React.CSSProperties)
            : undefined
        }
        className={cn(
          'flex w-full flex-col gap-0 overflow-x-hidden p-6 transition-[max-width] duration-300 ease-out',
          splitReady
            ? 'max-h-[88vh] sm:max-w-[560px] lg:h-[88vh] lg:w-(--dr-dialog-w) lg:max-w-none lg:overflow-hidden'
            : 'max-h-[85vh] max-w-[560px] overflow-y-auto',
        )}
      >
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
          // 紧凑小窗内垂直居中，顶部一层环境光晕
          <div className="relative flex min-h-[380px] items-center justify-center">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-status-blue-bg/70 to-transparent" />
            <RecognitionProgress
              phase={phase === 'submitting' ? 'submitting' : 'polling'}
              fileName={file?.name ?? '文书'}
              hint={hint}
              elapsedSeconds={progress.elapsedSeconds}
              level={progress.level}
              onRetry={canRetry && !retrying ? () => void retry() : undefined}
              retrying={retrying}
            />
          </div>
        )}

        {showError && (
          <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 px-6">
            <TriangleAlert className="h-6 w-6 text-status-red" />
            <span className="max-w-[380px] text-center text-[12.5px] text-muted-foreground">{error}</span>
            <div className="flex items-center gap-2">
              {canRetry && (
                <Button size="sm" disabled={retrying} onClick={() => void retry()}>
                  {retrying ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  重试识别
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={onClose}>
                关闭
              </Button>
            </div>
            {canRetry && (
              <span className="text-[11px] text-muted-foreground">重试不会重新上传，直接用已保存的文书再跑一次</span>
            )}
          </div>
        )}

        {contentReady && (
          // lg 双栏：左文书原文（宽度可拖拽）/ 右确认步骤；窄屏单栏整体滚动
          <RecognizeSplitPane
            bodyRef={splitBodyRef}
            resizing={resizing}
            hasPreview={hasPreview}
            previewUrl={previewUrl}
            splitPct={splitPct}
            draggingSplit={draggingSplit}
            onStartDragSplit={startDragSplit}
            isFileMode={isFileMode}
            isAttached={isAttached}
            task={task}
            recognition={recognition}
            rows={rows}
            busy={busy}
            onBound={refresh}
            setOverrides={setOverrides}
            onSkip={(row) => { void doSkip(row) }}
            onRevoke={(row) => { void doRevoke(row) }}
          />
        )}

        {contentReady && (
          <RecognizeFooter
            isFileMode={isFileMode}
            task={task}
            hasPreview={hasPreview}
            previewUrl={previewUrl}
            busy={busy}
            writableCount={writableCount}
            onClose={onClose}
            onConfirm={() => { void doConfirm() }}
          />
        )}

        {/* 弹窗右缘宽度手柄：分屏态独占右缘全高，悬停显色 */}
        {splitReady && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="拖动调整弹窗宽度"
            title="拖动调整弹窗宽度"
            onMouseDown={startDragDialog}
            className="absolute inset-y-3 right-0 z-30 w-[10px] cursor-col-resize"
          >
            <span
              className={cn(
                'absolute right-[2px] top-1/2 h-10 w-[4px] -translate-y-1/2 rounded-full transition-colors duration-150',
                draggingDialog ? 'bg-status-blue' : 'bg-border hover:bg-ring/60',
              )}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
