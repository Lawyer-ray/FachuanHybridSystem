import { useState } from 'react'
import { Copy, FileDown, FileSearch } from 'lucide-react'
import { toast } from 'sonner'

import { PARSE_BACKENDS, type ParseBackend } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN, BTN_PRIMARY, FIELD } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { FlowNotice, TaskFlowDialog } from './dialog/TaskFlowDialog'
import { errMessage } from '@/lib/errors'
import { useDocParse } from './use-doc-parse'
import { copyOutcome, downloadOutcome } from './doc-parse-outcome'
import { HistoryButton } from './history/HistoryParts'
import { ParseHistoryDialog } from './history/ParseHistoryDialog'
import { FORMAT_HINT, MAX_PARSE_FILE_BYTES, acceptOf, rejectReason, sizeReason } from './doc-parse-formats'

/** 引擎能力速览（对齐后台 workbench 的三个特性位） */
const ENGINE_HINT = `MinerU · 表格 / Textin · 标题树 / 本地 · 无网 · ≤ ${Math.round(MAX_PARSE_FILE_BYTES / (1024 * 1024))}MB`

/**
 * 文档解析：上传文件 → 选引擎 → 弹窗跟进解析进度，完成后在弹窗里
 * 预览全文并复制 / 下载（.md 或 .txt，随真实内容走）。
 */
export function DocParseCard() {
  const [backend, setBackend] = useState<ParseBackend>('textin')
  const [file, setFile] = useState<File | null>(null)
  const [extractTables, setExtractTables] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const { phase, hint, outcome, submit, reset } = useDocParse()

  const busy = phase === 'submitting' || phase === 'polling'
  // 局部收窄：done/result 为 const 别名，TS 可沿别名条件把 result 收窄为非空
  const result = phase === 'done' ? outcome : null
  const done = result !== null
  const ok = done && result.ok
  const baseName = (file?.name ?? 'document').replace(/\.[^.]+$/, '')

  const pick = (f: File | null) => {
    setFile(f)
    reset()
  }

  const run = async () => {
    if (!file) {
      toast.info('先选择要解析的文件')
      return
    }
    const bad = rejectReason(file.name, backend)
    if (bad) {
      toast.warning(bad)
      return
    }
    const tooBig = sizeReason(file.size)
    if (tooBig) {
      toast.warning(tooBig)
      return
    }
    setDialogOpen(true)
    try {
      await submit(file, {
        backend,
        extractTables,
        extractImages: false,
        returnMarkdown: true,
      })
    } catch (e) {
      // submit 内部已把异常转成失败 outcome，这里只是双保险
      toast.error(errMessage(e, '解析失败'))
    }
  }

  return (
    <ToolShell
      icon={<FileSearch className="h-3.5 w-3.5" />}
      title="文档解析"
      endpoint={TOOL_ENDPOINT.docParse}
      headerExtra={<HistoryButton title="历史解析记录" onClick={() => setHistoryOpen(true)} />}
      dropAccept={acceptOf(backend)}
      onDropFiles={(fs) => pick(fs[0] ?? null)}
    >
      <div className="flex flex-1 flex-col gap-[7px]">
        <select
          className={FIELD}
          value={backend}
          onChange={(e) => setBackend(e.target.value as ParseBackend)}
          disabled={busy}
          title="解析引擎"
        >
          {PARSE_BACKENDS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label} — {b.desc}
            </option>
          ))}
        </select>

        <FilePicker
          label="选择文件"
          hint={file ? file.name : FORMAT_HINT[backend]}
          accept={acceptOf(backend)}
          disabled={busy}
          onPick={(fs) => pick(fs[0] ?? null)}
        />

        <label className="flex cursor-pointer items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <input
            type="checkbox"
            className="size-3.5"
            checked={extractTables}
            onChange={(e) => setExtractTables(e.target.checked)}
            disabled={busy}
          />
          提取表格结构
        </label>

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={() => { void run() }} disabled={busy}>
            {busy && <Spinner />}
            {busy ? '解析中' : '开始解析'}
          </button>
          {done && !dialogOpen && (
            <button type="button" className={BTN} onClick={() => setDialogOpen(true)}>
              {ok ? '已完成 · 查看结果' : '解析失败 · 查看'}
            </button>
          )}
          {!done && <span className="flex-1 truncate text-right text-[9.5px] text-muted-foreground">{busy ? hint : ENGINE_HINT}</span>}
        </div>
      </div>

      <TaskFlowDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        icon={<FileSearch className="h-5 w-5" />}
        title="文档解析"
        tone={busy ? 'running' : ok ? 'success' : 'error'}
        headline={busy ? '正在解析文档…' : ok ? '解析完成' : '解析失败'}
        subline={
          busy
            ? hint
            : ok
              ? `${result.method || '解析完成'} · ${(result.markdown || result.text).length}${
                  typeof result.metadata.page_count === 'number' ? ` · ${result.metadata.page_count} 页` : ''
                }`
              : undefined
        }
        wide={!!ok}
        footer={
          <>
            {ok && (
              <>
                <button type="button" className={BTN} onClick={() => void copyOutcome(result)}>
                  <Copy className="h-3.5 w-3.5" />
                  复制全文
                </button>
                <button type="button" className={BTN_PRIMARY} onClick={() => downloadOutcome(result, baseName)}>
                  <FileDown className="h-3.5 w-3.5" />
                  {result.markdown ? '下载 .md' : '下载 .txt'}
                </button>
              </>
            )}
            {!ok && !busy && (
              <button type="button" className={BTN_PRIMARY} onClick={() => { void run() }}>
                再次解析
              </button>
            )}
            <button type="button" className={ok ? BTN : BTN_PRIMARY} onClick={() => setDialogOpen(false)}>
              关闭
            </button>
          </>
        }
      >
        {ok && (
          <pre className="max-h-[320px] min-h-0 overflow-auto rounded-[10px] border border-border bg-background px-3 py-2.5 text-[11.5px] leading-[1.7] whitespace-pre-wrap break-all">
            {result.markdown || result.text || '（解析结果为空）'}
          </pre>
        )}
        {!ok && !busy && <FlowNotice kind="error">{outcome?.error || '解析失败，请重试或换个引擎'}</FlowNotice>}
      </TaskFlowDialog>

      <ParseHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} />
    </ToolShell>
  )
}
