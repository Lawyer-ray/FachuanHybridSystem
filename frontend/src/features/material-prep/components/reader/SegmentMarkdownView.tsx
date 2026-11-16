import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 右栏正文的「原始 Markdown」视图：渲染 / 源码 / 整段编辑三态。
 *
 * ## 为什么必须有它
 *
 * 有定位块时面板渲染的是 `blocks[].text` 纯文本行——律师看不到 md 里的表格结构与
 * 标题层级，而表格/标题恰恰是 OCR 最易错的地方（合并单元格错列、表头错位、
 * 标题重复）。只给纯文本行，等于让律师对着已经拍平的结果核对拍平前的错误。
 * 而且纯文本行只能逐块改，改不动整段结构。
 *
 * ## 安全口径（与仓内既有 Markdown 渲染一致）
 *
 * react-markdown 默认**不执行原始 HTML**（不挂 rehype-raw，也没有
 * dangerouslySetInnerHTML）：识别产物里泄漏的 `<img>/<div>` 只会被当文本跳过。
 * 图片也不发起请求——md 里的 `imgs/xxx.jpg` 是后端产物相对路径，浏览器解析不到，
 * 渲染成占位说明比挂一个破图（且向未知地址发请求）更诚实。
 */

/** md 里是否含 HTML 标签（识别产物泄漏）：渲染视图会跳过它们，得告诉律师去源码看 */
function hasRawHtml(md: string): boolean {
  return /<\/?[a-z][^>]*>/i.test(md)
}

type ViewMode = 'render' | 'source' | 'edit'

const MODE_LABEL: Record<Exclude<ViewMode, 'edit'>, string> = {
  render: '渲染',
  source: '源码',
}

export function SegmentMarkdownView({
  md,
  onCommit,
  editRequest = 0,
}: {
  md: string
  /** 整段保存（走 setSegmentMarkdown，保 manualEdit 痕迹）；不传 = 只读 */
  onCommit?: (md: string) => void
  /** 递增的一次性「进入编辑态」请求（页面框双击但没有逐块编辑能力时用） */
  editRequest?: number
}) {
  const [mode, setMode] = useState<ViewMode>('render')
  const [draft, setDraft] = useState(md)

  // 与 BlockRow 的 appliedSeed 同型：记住消费过哪个请求号，父级重渲染不覆盖用户正在打的话
  const applied = useRef(0)
  useEffect(() => {
    if (editRequest === applied.current) return
    applied.current = editRequest
    if (editRequest > 0) {
      setDraft(md)
      setMode('edit')
    }
  }, [editRequest, md])

  if (mode === 'edit') {
    return (
      <div className="flex flex-col gap-1">
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setMode('render')
          }}
          spellCheck={false}
          aria-label="整段 Markdown 正文"
          className="max-h-[46vh] min-h-[160px] w-full resize-y overflow-auto rounded-lg border border-sky-300 bg-white p-2 font-mono text-[11px] leading-[1.7] outline-none focus:ring-1 focus:ring-sky-400"
        />
        <div className="flex items-center gap-1.5">
          {/* 显式保存而不是失焦即存：法律正文改错了下游 AI 会拿错文本跑（与逐块编辑同口径） */}
          <button
            type="button"
            onClick={() => {
              onCommit?.(draft)
              setMode('render')
            }}
            className="flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800"
          >
            <Check className="h-3 w-3" aria-hidden />
            保存整段
          </button>
          <button
            type="button"
            onClick={() => setMode('render')}
            className="rounded-md border border-border px-2 py-1 text-[11px] hover:bg-secondary"
          >
            取消
          </button>
          <span className="ml-auto text-[10px] text-muted-foreground">Esc 取消 · 保存后以整段正文为准</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        {(['render', 'source'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            aria-pressed={mode === m}
            className={cn(
              'rounded border px-1.5 py-0.5 text-[10.5px] transition-colors',
              mode === m
                ? 'border-zinc-300 bg-secondary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {MODE_LABEL[m]}
          </button>
        ))}
        {onCommit && (
          <button
            type="button"
            onClick={() => {
              setDraft(md)
              setMode('edit')
            }}
            className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10.5px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            编辑整段
          </button>
        )}
      </div>

      {mode === 'source' ? (
        <pre className="max-h-[46vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-secondary/40 p-2 font-mono text-[11px] leading-[1.7] text-foreground">
          {md}
        </pre>
      ) : (
        <div className="max-h-[46vh] overflow-auto rounded-lg border border-zinc-200 bg-secondary/40 p-2">
          {hasRawHtml(md) && (
            <p className="mb-1 text-[10.5px] leading-4 text-amber-700">
              正文里有 HTML 标签（识别产物泄漏），渲染视图不执行它们——切到「源码」看原文。
            </p>
          )}
          <RenderedMarkdown md={md} />
        </div>
      )}
    </div>
  )
}

/** 渲染视图：标题/段落/表格按文档的样子排。表格可能极宽（实测 744 列），必须能横向滚 */
function RenderedMarkdown({ md }: { md: string }) {
  return (
    <div className="flex flex-col gap-1.5 text-[11.5px] leading-[1.7] text-foreground">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // node 由 react-markdown 单独传，不能随 props 展开到 DOM 上
          h1: ({ node: _n, ...p }) => <h1 className={cn('text-[13.5px] font-[650]', p.className)} {...p} />,
          h2: ({ node: _n, ...p }) => <h2 className={cn('mt-1 text-[12.5px] font-[650]', p.className)} {...p} />,
          h3: ({ node: _n, ...p }) => <h3 className={cn('mt-1 text-[12px] font-[620]', p.className)} {...p} />,
          p: ({ node: _n, ...p }) => <p className={cn('text-secondary-foreground', p.className)} {...p} />,
          strong: ({ node: _n, ...p }) => <strong className={cn('font-[650] text-foreground', p.className)} {...p} />,
          table: ({ node: _n, ...p }) => (
            <div className="max-w-full overflow-x-auto">
              <table className={cn('my-1 w-full border-collapse text-[10.5px] tabular-nums', p.className)} {...p} />
            </div>
          ),
          th: ({ node: _n, ...p }) => (
            <th className={cn('border border-border bg-secondary/60 px-1.5 py-1 text-left font-medium', p.className)} {...p} />
          ),
          td: ({ node: _n, ...p }) => <td className={cn('border border-border px-1.5 py-1 align-top', p.className)} {...p} />,
          ul: ({ node: _n, ...p }) => <ul className={cn('list-disc pl-4', p.className)} {...p} />,
          ol: ({ node: _n, ...p }) => <ol className={cn('list-decimal pl-4', p.className)} {...p} />,
          code: ({ node: _n, ...p }) => (
            <code className={cn('rounded-[3px] bg-secondary px-1 font-mono text-[10.5px]', p.className)} {...p} />
          ),
          // 不发请求：相对路径解析不到，外部地址则会把律师的访问暴露给未知服务
          img: ({ node: _n, src, alt }) => (
            <span className="text-[10.5px] text-muted-foreground">
              [图片{alt ? `：${alt}` : ''}未随正文提供{typeof src === 'string' && src ? `（${src}）` : ''}]
            </span>
          ),
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  )
}
