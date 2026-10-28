import { useState } from 'react'
import { Copy, FileDown, FileSearch } from 'lucide-react'
import { toast } from 'sonner'

import { PARSE_BACKENDS, type ParseBackend, type ParseOutcome } from '../../api'
import { BTN, BTN_PRIMARY, FIELD } from '../../ui'
import { FilePicker, Spinner, ToolShell } from './shared'
import { FlowNotice, TaskFlowDialog } from './dialog/TaskFlowDialog'
import { errMessage } from '@/lib/errors'
import { useDocParse } from './use-doc-parse'
import { copyOutcome, downloadOutcome } from './doc-parse-outcome'
import { HistoryButton } from './history/HistoryParts'
import { ParseHistoryDialog } from './history/ParseHistoryDialog'
import { BlockReviewPanel } from './review/BlockReviewPanel'
import { reviewStats } from './review/review-domain'
import { cn } from '@/lib/utils'
import { FORMAT_HINT, MAX_PARSE_FILE_BYTES, acceptOf, rejectReason, sizeReason } from './doc-parse-formats'

/**
 * 结果区双视图：「全文」看最终 Markdown，「逐块复核」看待核对的块。
 *
 * 为什么拆两个视图而不是把块内嵌进全文：全文是要复制走的东西，
 * 块列表是要逐条看的东西，混在一起两边都做不好。
 * 默认落在「逐块复核」当且有低分块时——这时用户最需要看到的是"哪里可能错了"，
 * 而不是"整体读起来很顺"（顺的文本恰恰是最危险的，它掩盖了错字）。
 */
function ResultTabs({
  outcome,
  baseName,
  onCopy,
  onDownload,
}: {
  outcome: ParseOutcome
  baseName: string
  onCopy: () => void
  onDownload: () => void
}) {
  const blocks = outcome.blocks
  const hasBlocks = !!blocks && blocks.length > 0
  const stats = reviewStats(blocks ?? [])
  // 只有真有低分块时才默认跳到复核视图；否则默认看全文（不要无谓地改用户习惯）
  const [view, setView] = useState<'text' | 'blocks'>(stats.flagged > 0 ? 'blocks' : 'text')

  if (!hasBlocks) {
    return (
      <div className="flex min-h-0 flex-col gap-2">
        <pre className="max-h-[320px] min-h-0 overflow-auto rounded-[10px] border border-border bg-background px-3 py-2.5 text-[11.5px] leading-[1.7] whitespace-pre-wrap break-all">
          {outcome.markdown || outcome.text || '（解析结果为空）'}
        </pre>
        <BlockReviewPanel blocks={blocks} coverage={outcome.coverage} />
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="flex flex-none items-center gap-1">
        {(
          [
            { key: 'blocks', label: `逐块复核 ${blocks.length}` },
            { key: 'text', label: '全文' },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setView(t.key)}
            className={cn(
              'rounded-[7px] px-2.5 py-[4px] text-[11px] font-medium transition-colors',
              view === t.key
                ? 'bg-foreground text-background'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
          >
            {t.label}
            {t.key === 'blocks' && stats.flagged > 0 && (
              <span className="ml-1 rounded-[99px] bg-status-red px-1 text-[9px] font-bold text-white">
                {stats.flagged}
              </span>
            )}
          </button>
        ))}
      </div>

      {view === 'text' ? (
        <pre className="max-h-[320px] min-h-0 overflow-auto rounded-[10px] border border-border bg-background px-3 py-2.5 text-[11.5px] leading-[1.7] whitespace-pre-wrap break-all">
          {outcome.markdown || outcome.text || '（解析结果为空）'}
        </pre>
      ) : (
        <div className="max-h-[360px] overflow-y-auto">
          <BlockReviewPanel blocks={blocks} coverage={outcome.coverage} />
        </div>
      )}

      {/* 复核视图下也保留复制/下载入口，避免为了导出再切回全文 */}
      {view === 'blocks' && (
        <div className="flex flex-none items-center gap-2">
          <button type="button" className={BTN} onClick={onCopy}>
            <Copy className="h-3.5 w-3.5" />
            复制全文
          </button>
          <button type="button" className={BTN} onClick={onDownload}>
            <FileDown className="h-3.5 w-3.5" />
            {outcome.markdown ? '下载 .md' : '下载 .txt'}
          </button>
          <span className="ml-auto truncate text-[9.5px] text-muted-foreground">{baseName}</span>
        </div>
      )}
    </div>
  )
}

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
          <ResultTabs
            outcome={result}
            baseName={baseName}
            onCopy={() => void copyOutcome(result)}
            onDownload={() => downloadOutcome(result, baseName)}
          />
        )}
        {!ok && !busy && <FlowNotice kind="error">{outcome?.error || '解析失败，请重试或换个引擎'}</FlowNotice>}
      </TaskFlowDialog>

      <ParseHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} />
    </ToolShell>
  )
}
