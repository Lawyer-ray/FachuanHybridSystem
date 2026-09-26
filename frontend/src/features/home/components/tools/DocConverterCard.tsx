import { useEffect, useRef, useState } from 'react'
import { FileType2 } from 'lucide-react'
import { toast } from 'sonner'

import { converterDownloadUrl, createConverterJob, getConverterJob, type ConverterJob } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { errMessage } from '../../errors'

/** DOC 转 DOCX：POST /doc-converter/jobs，轮询进度，完成后下载 zip */
export function DocConverterCard() {
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [job, setJob] = useState<ConverterJob | null>(null)
  const timer = useRef(0)
  // 卸载后取消：轮询在飞时若组件卸载，就不该再排下一轮 / window.open
  const cancelled = useRef(false)

  const stop = () => {
    window.clearTimeout(timer.current)
    setBusy(false)
  }

  // 卸载时停止轮询，避免离开页面还在打接口
  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
      window.clearTimeout(timer.current)
    }
  }, [])

  const poll = (jobId: string) => {
    const tick = async () => {
      if (cancelled.current) return
      try {
        const j = await getConverterJob(jobId)
        if (cancelled.current) return
        setJob(j)
        const settled = j.total > 0 && j.done + j.failed >= j.total
        if (j.status === 'completed' || j.status === 'failed' || settled) {
          stop()
          if (j.done > 0) {
            window.open(converterDownloadUrl(jobId), '_blank', 'noopener')
            toast.success(`转换完成：成功 ${j.done} 个，正在下载`)
          } else {
            toast.warning('转换失败，没有成功的文件')
          }
        } else {
          timer.current = window.setTimeout(tick, 2000)
        }
      } catch {
        if (cancelled.current) return
        stop()
        toast.error('查询转换进度失败')
      }
    }
    void tick()
  }

  const submit = async () => {
    if (files.length === 0) {
      toast.info('先选择 .doc 文件')
      return
    }
    setBusy(true)
    setJob(null)
    try {
      const id = await createConverterJob(files)
      toast.success('转换任务已提交，正在后台处理')
      poll(id)
    } catch (e) {
      stop()
      toast.error(errMessage(e, '提交转换任务失败'))
    }
  }

  return (
    <ToolShell icon={<FileType2 className="h-3.5 w-3.5" />} title="DOC 转 DOCX" endpoint={TOOL_ENDPOINT.docConverter}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <FilePicker label="选择 .doc 文件" hint="法院下发的旧格式文书" accept=".doc" multiple onPick={setFiles} />

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            开始转换
          </button>
          <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">
            {job ? `${job.done}/${job.total || '?'} 已完成` : 'LibreOffice 转换'}
          </span>
        </div>
      </div>
    </ToolShell>
  )
}
