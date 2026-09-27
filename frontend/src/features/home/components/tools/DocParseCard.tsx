import { useState } from 'react'
import { FileSearch } from 'lucide-react'
import { toast } from 'sonner'

import { PARSE_BACKENDS, type ParseBackend } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { errMessage } from '../../errors'
import { useDocParse } from './use-doc-parse'
import { FORMAT_HINT, MAX_PARSE_FILE_BYTES, acceptOf, rejectReason, sizeReason } from './doc-parse-formats'

/** 引擎能力速览（对齐后台 workbench 的三个特性位） */
const ENGINE_HINT = `MinerU · 表格 / Textin · 标题树 / 本地 · 无网 · ≤ ${Math.round(MAX_PARSE_FILE_BYTES / (1024 * 1024))}MB`

/** 预览区最大高度：卡片本身不高，Markdown 可能几千字，别把首页撑爆 */
const PREVIEW_MAX_H = 180

/**
 * 文档解析：上传文件 → 选引擎 → 解析为 Markdown。
 *
 * 与后台「文档解析工作台」（/admin/document_parsing/documentparsingtool/）
 * 共用同一套后端能力：POST /document-parsing/parse + GET .../task/{id}。
 * 云端引擎（MinerU / TextinParse）异步返回 task_id，前端轮询到出结果；
 * 本地引擎同步直接返回。
 */
export function DocParseCard() {
  const [backend, setBackend] = useState<ParseBackend>('textin')
  const [file, setFile] = useState<File | null>(null)
  const [extractTables, setExtractTables] = useState(true)
  const { phase, hint, outcome, submit, reset } = useDocParse()

  const busy = phase === 'submitting' || phase === 'polling'
  const done = phase === 'done' && !!outcome
  const ok = done && outcome.ok

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

  const copy = async () => {
    const text = outcome?.markdown || outcome?.text || ''
    if (!text) {
      toast.info('没有可复制的解析内容')
      return
    }
    try {
      await navigator.clipboard.writeText(text)
      toast.success('已复制解析结果')
    } catch {
      toast.error('浏览器拒绝了剪贴板，可手动选中的内容复制')
    }
  }

  const download = () => {
    const text = outcome?.markdown || outcome?.text || ''
    if (!text) {
      toast.info('没有可下载的解析内容')
      return
    }
    // 前端本地合成 Blob 下载——后端 parse 接口只返回内容，没有下载端点。
    // 本地后端不出 Markdown（后端明确「本地后端不支持」），这时内容其实是纯文本，
    // 扩展名跟着真实内容走，别把纯文本命名成 .md 骗人。
    const isMd = !!outcome?.markdown
    const mime = isMd ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8'
    const ext = isMd ? 'md' : 'txt'
    const url = URL.createObjectURL(new Blob([text], { type: mime }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${(file?.name ?? 'document').replace(/\.[^.]+$/, '')}.${ext}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <ToolShell icon={<FileSearch className="h-3.5 w-3.5" />} title="文档解析" endpoint={TOOL_ENDPOINT.docParse}>
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

        <label
          className={`flex items-center gap-2 rounded-[8px] border border-dashed border-input bg-secondary/30 px-[9px] py-[6px] transition-colors ${
            busy ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-ring/40 hover:bg-card'
          }`}
        >
          <input
            type="file"
            accept={acceptOf(backend)}
            className="hidden"
            disabled={busy}
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <span className="text-[11px] font-medium whitespace-nowrap text-secondary-foreground">选择文件</span>
          <span className="truncate text-[10.5px] text-muted-foreground" title={FORMAT_HINT[backend]}>
            {file ? file.name : FORMAT_HINT[backend]}
          </span>
        </label>

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

        {/* 结果区：成功给预览 + 元信息，失败给原因。都放在按钮上方，按钮永远在同一位置 */}
        {done && ok && (
          <div className="flex min-h-0 flex-col gap-1">
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span className="font-medium text-secondary-foreground">{outcome.method || '解析完成'}</span>
              <span>·</span>
              {/* 本地后端不出 Markdown（后端：本地后端不支持），这时 markdown 为空、
                  text 有值。按真实内容报格式，别一律写 Markdown */}
              <span>{(outcome.markdown || outcome.text).length} 字</span>
              {typeof outcome.metadata.page_count === 'number' && (
                <>
                  <span>·</span>
                  <span>{outcome.metadata.page_count} 页</span>
                </>
              )}
              <span className="flex-1" />
              <span className="truncate">{outcome.markdown ? 'Markdown' : '纯文本'}</span>
            </div>
            <pre
              className="min-h-0 overflow-auto rounded-[8px] border border-border bg-background px-2 py-1.5 text-[10px] leading-[1.5] whitespace-pre-wrap break-all text-secondary-foreground"
              style={{ maxHeight: PREVIEW_MAX_H }}
            >
              {outcome.markdown || outcome.text || '（解析结果为空）'}
            </pre>
          </div>
        )}

        {done && !ok && (
          <div className="rounded-[8px] border border-status-red/30 bg-status-red-bg px-2.5 py-[7px] text-[10.5px] leading-[1.5] text-status-red">
            {outcome.error || '解析失败'}
          </div>
        )}

        {busy && (
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <Spinner />
            <span>{hint}</span>
          </div>
        )}

        <div className={`flex items-center gap-2 ${ok ? '' : 'mt-auto'}`}>
          <button type="button" className={BTN_PRIMARY} onClick={run} disabled={busy}>
            {busy && <Spinner />}
            {busy ? '解析中' : '开始解析'}
          </button>
          {ok && (
            <>
              <button
                type="button"
                onClick={copy}
                className="flex h-[32px] items-center rounded-[8px] border border-border px-3 text-[11.5px] text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                复制
              </button>
              <button
                type="button"
                onClick={download}
                className="flex h-[32px] items-center rounded-[8px] border border-border px-3 text-[11.5px] text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {outcome.markdown ? '下载 .md' : '下载 .txt'}
              </button>
            </>
          )}
          <span className="flex-1 truncate text-right text-[9.5px] text-muted-foreground">
            {busy ? hint : ENGINE_HINT}
          </span>
        </div>
      </div>
    </ToolShell>
  )
}
