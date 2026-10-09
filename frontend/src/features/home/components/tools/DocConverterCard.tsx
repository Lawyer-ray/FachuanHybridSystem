import { useState } from 'react'
import { CheckCircle2, Copy, FileDown, FileType2, Loader2, XCircle } from 'lucide-react'
import { toast } from 'sonner'

import {
  converterDownloadUrl,
  converterItemDownloadUrl,
  copyConverterItemsToClipboard,
  triggerDownload,
  type ConverterJob,
} from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN, BTN_PRIMARY } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { FlowNotice, TaskFlowDialog } from './dialog/TaskFlowDialog'
import { HistoryButton } from './history/HistoryParts'
import { ConverterHistoryDialog } from './history/ConverterHistoryDialog'
import { useConverterJob } from './use-converter-job'

/** 行内小按钮：描边风格，与法院短信成功弹窗一致 */
const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'

/** 文件数进度条：已完成（绿）/ 失败（红）/ 剩余（灰） */
function JobProgressBar({ job }: { job: ConverterJob }) {
  const total = Math.max(job.total, job.done + job.failed, 1)
  const donePct = Math.round((job.done / total) * 100)
  const failedPct = Math.round((job.failed / total) * 100)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div className="flex h-full w-full">
          <div className="h-full bg-status-green transition-all duration-500" style={{ width: `${donePct}%` }} />
          <div className="h-full bg-status-red transition-all duration-500" style={{ width: `${failedPct}%` }} />
        </div>
      </div>
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>
          进度 <b className="text-foreground">{job.done + job.failed}</b> / {job.total || '?'}
        </span>
        {job.done > 0 && <span className="text-status-green">成功 {job.done}</span>}
        {job.failed > 0 && <span className="text-status-red">失败 {job.failed}</span>}
      </div>
    </div>
  )
}

/** DOC 转 DOCX：提交后弹窗展示文件级进度；完成后列出产物，逐件复制/下载 + ZIP */
export function DocConverterCard() {
  const [files, setFiles] = useState<File[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [copyBusy, setCopyBusy] = useState(false)
  // 提交/轮询/终态编排都在 use-converter-job（会话号守卫防重提交竞态）
  const { phase, jobId, job, error, submit, resume } = useConverterJob()

  const start = () => {
    if (files.length === 0) return
    setDialogOpen(true)
    void submit(files)
  }

  const okItems = (job?.items ?? []).filter((it) => it.ok)

  /** 三级降级：后端落板系统剪贴板 → 复制文件名 → 报错 */
  const copyItems = async (items: typeof okItems) => {
    if (!jobId || items.length === 0) return
    setCopyBusy(true)
    try {
      const res = await copyConverterItemsToClipboard(jobId, items.map((it) => it.id))
      if (res.success && res.copied > 0) {
        toast.success(`已复制 ${res.copied} 个文件（同 Finder 复制），到微信对话框直接 ⌘V 粘贴发送`)
        return
      }
      // 降级也要复制「本次选中」的文件名（单件复制时不能变成全部成功件）
      if (await copyNames(items)) toast.info('当前环境不支持复制文件本体，已复制文件名')
      else toast.error('复制失败，请改用打包下载')
    } catch {
      if (await copyNames(items)) toast.info('当前环境不支持复制文件本体，已复制文件名')
      else toast.error('复制失败，请改用打包下载')
    } finally {
      setCopyBusy(false)
    }
  }

  const copyNames = async (items: typeof okItems) => {
    try {
      await navigator.clipboard.writeText(items.map((it) => it.name).join('\n'))
      return true
    } catch {
      return false
    }
  }

  return (
    <ToolShell
      icon={<FileType2 className="h-3.5 w-3.5" />}
      title="DOC 转 DOCX"
      endpoint={TOOL_ENDPOINT.docConverter}
      headerExtra={<HistoryButton title="历史转换任务" onClick={() => setHistoryOpen(true)} />}
      dropAccept=".doc"
      onDropFiles={setFiles}
    >
      <div className="flex flex-1 flex-col gap-[7px]">
        <FilePicker
          label="选择 .doc 文件"
          hint={files.length > 0 ? `已选 ${files.length} 个文件` : '法院下发的旧格式文书'}
          accept=".doc"
          multiple
          disabled={phase === 'running'}
          onPick={setFiles}
        />

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={start} disabled={phase === 'running'}>
            {phase === 'running' && <Spinner />}
            开始转换
          </button>
          {phase === 'success' && !dialogOpen && (
            <button type="button" className={BTN} onClick={() => setDialogOpen(true)}>
              已完成 · 查看结果
            </button>
          )}
          <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">
            {job ? `${job.done}/${job.total || '?'} 已完成` : 'LibreOffice 转换'}
          </span>
        </div>
      </div>

      <TaskFlowDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        icon={<FileType2 className="h-5 w-5" />}
        title="DOC 转 DOCX"
        tone={phase === 'running' ? 'running' : phase === 'success' ? 'success' : phase === 'timeout' ? 'timeout' : 'error'}
        headline={phase === 'running' ? '正在批量转换…' : phase === 'success' ? '转换完成' : phase === 'timeout' ? '转换耗时较长，后台仍在继续' : '转换失败'}
        subline={phase === 'success' && job ? `成功 ${job.done} 个${job.failed > 0 ? `，失败 ${job.failed} 个` : ''}` : undefined}
        wide={phase === 'success'}
        footer={
          <>
            {phase === 'success' && okItems.length > 0 && (
              <button type="button" className={BTN + ' mr-auto'} disabled={copyBusy} onClick={() => void copyItems(okItems)}>
                {copyBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
                全部复制
              </button>
            )}
            {phase === 'timeout' && jobId && (
              <button type="button" className={BTN} onClick={resume}>
                继续等待
              </button>
            )}
            {phase === 'success' && jobId && (
              <button type="button" className={BTN_PRIMARY} onClick={() => void triggerDownload(() => converterDownloadUrl(jobId))}>
                <FileDown className="h-3.5 w-3.5" />
                打包下载（ZIP）
              </button>
            )}
            <button type="button" className={phase === 'success' ? BTN : BTN_PRIMARY} onClick={() => setDialogOpen(false)}>
              关闭
            </button>
          </>
        }
      >
        {job && (phase === 'running' || phase === 'timeout') && <JobProgressBar job={job} />}

        {phase === 'success' && job && (
          <div className="flex flex-col gap-2">
            <div className="text-[11px] font-semibold text-muted-foreground">转换完成 {okItems.length} 件</div>
            {okItems.map((it) => (
              <div
                key={it.id}
                className="flex items-center gap-2.5 rounded-[10px] border border-border bg-secondary/40 px-3 py-2 transition-colors hover:bg-secondary/70"
              >
                <CheckCircle2 className="h-4 w-4 flex-none text-status-green" />
                <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={it.name}>
                  {it.name}
                </span>
                <button
                  type="button"
                  className={ROW_BTN}
                  disabled={copyBusy}
                  title="复制文件，可直接粘贴到对话框发送"
                  onClick={() => void copyItems([it])}
                >
                  {copyBusy ? <Loader2 className="h-3 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
                  复制
                </button>
                <button type="button" className={ROW_BTN} onClick={() => void triggerDownload(() => converterItemDownloadUrl(jobId!, it.id))}>
                  <FileDown className="h-3.5 w-3.5" />
                  下载
                </button>
              </div>
            ))}
            {job.failed > 0 && (
              <div className="flex flex-col gap-1">
                <div className="text-[11px] font-semibold text-status-red">失败 {job.failed} 件</div>
                {job.items
                  .filter((it) => !it.ok)
                  .map((it) => (
                    <div key={it.id} className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
                      <XCircle className="h-3.5 w-3.5 flex-none text-status-red" />
                      <span className="min-w-0 flex-1 truncate">{it.name}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {phase === 'error' && <FlowNotice kind="error">{error || '转换失败'}</FlowNotice>}
        {phase === 'timeout' && (
          <FlowNotice kind="warn">已等待超过 5 分钟。任务仍在后台执行，可「继续等待」或稍后回来下载。</FlowNotice>
        )}
      </TaskFlowDialog>

      <ConverterHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} />
    </ToolShell>
  )
}
