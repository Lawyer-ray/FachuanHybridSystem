import { useEffect, useRef, useState } from 'react'
import { FileDown, FileType2 } from 'lucide-react'

import { converterDownloadUrl, createConverterJob, getConverterJob, triggerDownload, type ConverterJob } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN, BTN_PRIMARY } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { FlowNotice, TaskFlowDialog } from './dialog/TaskFlowDialog'

/** 轮询节奏与上限：2s 一次，5 分钟仍没结束就转「后台继续」 */
const DOC_CONVERTER_POLL_MS = 2_000
const DOC_CONVERTER_MAX_POLLS = 150

type Phase = 'idle' | 'running' | 'success' | 'error' | 'timeout'

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

/** DOC 转 DOCX：提交后弹窗展示文件级进度，完成后直接下载 ZIP（不再 window.open，避免被拦截） */
export function DocConverterCard() {
  const [files, setFiles] = useState<File[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<ConverterJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const timer = useRef(0)
  // 卸载后取消：轮询在飞时若组件卸载，就不该再排下一轮
  const cancelled = useRef(false)
  const polls = useRef(0)

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
      window.clearTimeout(timer.current)
    }
  }, [])

  const stop = () => window.clearTimeout(timer.current)

  const poll = (id: string) => {
    const tick = async () => {
      if (cancelled.current) return
      try {
        const j = await getConverterJob(id)
        if (cancelled.current) return
        setJob(j)
        const settled = j.total > 0 && j.done + j.failed >= j.total
        if (j.status === 'completed' || j.status === 'failed' || settled) {
          stop()
          setPhase(j.done > 0 ? 'success' : 'error')
          setError(j.done > 0 ? null : '全部文件转换失败，请确认上传的是 .doc 文件')
        } else if (polls.current >= DOC_CONVERTER_MAX_POLLS) {
          stop()
          setPhase('timeout')
        } else {
          polls.current += 1
          timer.current = window.setTimeout(tick, DOC_CONVERTER_POLL_MS)
        }
      } catch {
        if (cancelled.current) return
        stop()
        setPhase('error')
        setError('查询转换进度失败，可稍后重试')
      }
    }
    polls.current = 0
    void tick()
  }

  const submit = async () => {
    if (files.length === 0) {
      return
    }
    setPhase('running')
    setJob(null)
    setError(null)
    setDialogOpen(true)
    try {
      const id = await createConverterJob(files)
      if (cancelled.current) return
      setJobId(id)
      poll(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交转换任务失败')
      setPhase('error')
    }
  }

  const busy = phase === 'running'

  return (
    <ToolShell icon={<FileType2 className="h-3.5 w-3.5" />} title="DOC 转 DOCX" endpoint={TOOL_ENDPOINT.docConverter}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <FilePicker label="选择 .doc 文件" hint="法院下发的旧格式文书" accept=".doc" multiple onPick={setFiles} />

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            开始转换
          </button>
          {phase === 'success' && !dialogOpen && (
            <button type="button" className={BTN} onClick={() => setDialogOpen(true)}>
              已完成 · 下载 ZIP
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
        footer={
          <>
            {phase === 'timeout' && jobId && (
              <button type="button" className={BTN} onClick={() => {
                setPhase('running')
                poll(jobId)
              }}>
                继续等待
              </button>
            )}
            {phase === 'success' && jobId && (
              <button type="button" className={BTN_PRIMARY} onClick={() => triggerDownload(converterDownloadUrl(jobId))}>
                <FileDown className="h-3.5 w-3.5" />
                下载全部（ZIP）
              </button>
            )}
            <button type="button" className={phase === 'success' ? BTN : BTN_PRIMARY} onClick={() => setDialogOpen(false)}>
              关闭
            </button>
          </>
        }
      >
        {job && (phase === 'running' || phase === 'timeout') && <JobProgressBar job={job} />}
        {phase === 'error' && <FlowNotice kind="error">{error || '转换失败'}</FlowNotice>}
        {phase === 'timeout' && (
          <FlowNotice kind="warn">已等待超过 5 分钟。任务仍在后台执行，可「继续等待」或稍后回来下载。</FlowNotice>
        )}
      </TaskFlowDialog>
    </ToolShell>
  )
}
