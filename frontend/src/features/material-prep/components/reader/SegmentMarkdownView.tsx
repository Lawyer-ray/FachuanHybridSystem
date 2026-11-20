import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 右栏正文的「渲染 / 源码 / 编辑整段」三种呈现。
 *
 * ## 为什么必须有它
 *
 * 有定位块时面板渲染的是 `blocks[].text` 纯文本行——律师看不到 md 里的表格结构与
 * 标题层级，而表格/标题恰恰是 OCR 最易错的地方（合并单元格错列、表头错位、
 * 标题重复）。只给纯文本行，等于让律师对着已经拍平的结果核对拍平前的错误。
 * 而且纯文本行只能逐块改，改不动整段结构。
 *
 * ## 为什么是**受控**的（`mode` / `onModeChange` 从父级来）
 *
 * 这个组件以前自己持有一套「渲染 / 源码 / 编辑整段」按钮，父级 `SegmentMarkdown`
 * 另有一套「定位块 / 原始 Markdown」——两套切换器叠在一起，切过去之后控件从两个
 * 变三个、选中态还换了一套样式。一个侧边栏里最多同时出现三行控件，正是「乱」的
 * 来源。现在视图状态只有一份（在 `SegmentMarkdown`），本组件只负责画。
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

/** 三种呈现。`edit` 不是独立的「视图」，是 `source` 的可编辑态（父级据此高亮「源码」） */
export type MarkdownViewMode = 'render' | 'source' | 'edit'

export function SegmentMarkdownView({
  md,
  mode,
  onModeChange,
  onCommit,
}: {
  md: string
  /** 当前呈现方式（父级持有：切换器只有一套，见文件头） */
  mode: MarkdownViewMode
  onModeChange: (mode: MarkdownViewMode) => void
  /** 整段保存（走 setSegmentMarkdown，保 manualEdit 痕迹）；不传 = 只读 */
  onCommit?: (md: string) => void
}) {
  const [draft, setDraft] = useState(md)
  // 进入编辑态那一下才用最新 md 预填：编辑期间父级重渲染不能覆盖用户正在打的话
  const lastMode = useRef<MarkdownViewMode>(mode)
  useEffect(() => {
    if (mode === 'edit' && lastMode.current !== 'edit') setDraft(md)
    lastMode.current = mode
  }, [mode, md])

  if (mode === 'edit') {
    return (
      <div className="flex flex-col gap-1">
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onModeChange('render')
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
              onModeChange('render')
            }}
            className="flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800"
          >
            <Check className="h-3 w-3" aria-hidden />
            保存整段
          </button>
          <button
            type="button"
            onClick={() => onModeChange('render')}
            className="rounded-md border border-border px-2 py-1 text-[11px] hover:bg-secondary"
          >
            取消
          </button>
          <span className="ml-auto text-[10px] text-muted-foreground">Esc 取消 · 保存后以整段正文为准</span>
        </div>
      </div>
    )
  }

  if (mode === 'source') {
    return (
      <pre className="max-h-[46vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-secondary/40 p-2 font-mono text-[11px] leading-[1.7] text-foreground">
        {md}
      </pre>
    )
  }

  return (
    <div className="max-h-[46vh] overflow-auto rounded-lg border border-zinc-200 bg-secondary/40 p-2">
      {hasRawHtml(md) && (
        <p className="mb-1 text-[10.5px] leading-4 text-amber-700">
          正文里有 HTML 标签（识别产物泄漏），渲染视图不执行它们——切到「源码」看原文。
        </p>
      )}
      <RenderedMarkdown md={md} />
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
