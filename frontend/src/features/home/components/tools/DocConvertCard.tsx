import { useState } from 'react'
import { FileDown, FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { CONVERT_TEMPLATES_KEY, convertDocument, listConvertTemplates, type ConvertResult } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN, BTN_PRIMARY } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { TemplateCombobox } from './TemplateCombobox'
import { FlowNotice, TaskFlowDialog } from './dialog/TaskFlowDialog'
import { HistoryButton } from './history/HistoryParts'
import { ConvertHistoryDialog } from './history/ConvertHistoryDialog'
import { errMessage } from '@/lib/errors'

type Phase = 'idle' | 'running' | 'success' | 'error'

/** blob 现生成现释放的下载（同一结果可反复下载） */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * 要素式转换：提交后弹窗跟进——转换中给动画与提示，完成后可直接下载
 * （自动下载一次，弹窗里可反复重下），失败给出原因。
 */
export function DocConvertCard() {
  const [mbid, setMbid] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [result, setResult] = useState<ConvertResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  const { data: groups = [], isLoading } = useQuery({
    queryKey: CONVERT_TEMPLATES_KEY,
    queryFn: listConvertTemplates,
    staleTime: 5 * 60_000,
  })

  const busy = phase === 'running'

  const submit = async () => {
    if (!mbid) {
      toast.info('先选文书类型')
      return
    }
    if (!file) {
      toast.info('先选择要转换的文书')
      return
    }
    setPhase('running')
    setResult(null)
    setError(null)
    setDialogOpen(true)
    try {
      const res = await convertDocument(mbid, file)
      setResult(res)
      setPhase('success')
      // 转换完成顺手落一份到下载目录；弹窗里保留重下入口
      downloadBlob(res.blob, res.filename)
    } catch (e) {
      setError(errMessage(e, '要素式转换失败，请检查文件格式'))
      setPhase('error')
    }
  }

  return (
    <ToolShell
      icon={<FileText className="h-3.5 w-3.5" />}
      title="要素式转换"
      endpoint={TOOL_ENDPOINT.docConvert}
      headerExtra={<HistoryButton title="历史转换记录" onClick={() => setHistoryOpen(true)} />}
      dropAccept=".doc,.docx,.pdf"
      onDropFiles={(fs) => setFile(fs[0] ?? null)}
    >
      <div className="flex flex-1 flex-col gap-[7px]">
        {/* 可搜索组合框：60+ 模板原生下拉又长又不能搜 */}
        <TemplateCombobox groups={groups} value={mbid} onChange={setMbid} disabled={isLoading || busy} />

        <FilePicker
          label="选择文书"
          hint={file ? file.name : '.doc / .docx / .pdf ≤ 20MB'}
          accept=".doc,.docx,.pdf"
          disabled={busy}
          onPick={(fs) => setFile(fs[0] ?? null)}
        />

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            {busy ? '转换中' : '转换'}
          </button>
          {phase === 'success' && !dialogOpen && (
            <button type="button" className={BTN} onClick={() => setDialogOpen(true)}>
              已完成 · 重下文书
            </button>
          )}
          {phase !== 'success' && phase !== 'running' && (
            <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">→ 要素式文书</span>
          )}
        </div>
      </div>

      <TaskFlowDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        icon={<FileText className="h-5 w-5" />}
        title="要素式转换"
        tone={phase === 'running' ? 'running' : phase === 'success' ? 'success' : 'error'}
        headline={phase === 'running' ? '正在提取要素并生成文书…' : phase === 'success' ? '转换完成' : '转换失败'}
        subline={
          phase === 'running'
            ? '大文件可能要等几十秒，别关弹窗，完成即可下载'
            : phase === 'success'
              ? result?.filename
              : undefined
        }
        footer={
          <>
            {phase === 'success' && result && (
              <button type="button" className={BTN_PRIMARY} onClick={() => downloadBlob(result.blob, result.filename)}>
                <FileDown className="h-3.5 w-3.5" />
                下载要素式文书
              </button>
            )}
            <button type="button" className={phase === 'success' ? BTN : BTN_PRIMARY} onClick={() => setDialogOpen(false)}>
              关闭
            </button>
          </>
        }
      >
        {phase === 'error' && <FlowNotice kind="error">{error || '转换失败，请检查文件格式'}</FlowNotice>}
      </TaskFlowDialog>

      <ConvertHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} />
    </ToolShell>
  )
}
