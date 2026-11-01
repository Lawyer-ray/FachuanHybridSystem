/**
 * markdown 视图三件套：渲染 / 源码 / 原文对照
 *
 * 「读懂」阶段的抽屉要回答的问题是：**机器读出来的东西跟我看到的原件是不是一回事。**
 * 只给一段等宽源码答不了 —— 律师看不出哪里是标题、哪里是表格；
 * 只给渲染结果也答不了 —— 律师没法确认「这段话是不是真的在原件里」。
 * 所以三个视图并排可选，其中「原文对照」把两边的对应行上下对齐摆出来。
 *
 * react-markdown 默认不执行原始 HTML（无注入面），这里也没有 dangerouslySetInnerHTML。
 */

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { DEMO_X1_ORIGINAL_COMPARE } from '../demo-data'
import { InsetBlock, Pill } from '../ui'
import { cn } from '@/lib/utils'

export type MarkdownView = 'render' | 'source' | 'compare'

const MARKDOWN_VIEW_LABEL: Record<MarkdownView, string> = {
  render: '渲染视图',
  source: '源码',
  compare: '原文对照',
}

/** 渲染视图：标题/段落/表格按文档的样子排，不再是等宽源码 */
function RenderedMarkdown({ markdown }: { markdown: string }) {
  return (
    <div className="flex flex-col gap-1.5 text-[11.5px] leading-[1.7]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // node / children 由 react-markdown 单独传，不随 props 展开
          // （展开会把 node="[object Object]" 落成 DOM 属性）；
          // 手写标签会重复子节点，表格会渲染两遍 —— 只挂 className，内容交给插槽。
          h1: ({ node: _n, ...p }) => <h1 className={cn('text-[14px] font-[650]', p.className)} {...p} />,
          h2: ({ node: _n, ...p }) => <h2 className={cn('mt-1 text-[13px] font-[650]', p.className)} {...p} />,
          h3: ({ node: _n, ...p }) => <h3 className={cn('mt-1 text-[12px] font-[620]', p.className)} {...p} />,
          p: ({ node: _n, ...p }) => <p className={cn('text-secondary-foreground', p.className)} {...p} />,
          strong: ({ node: _n, ...p }) => <strong className={cn('font-[650] text-foreground', p.className)} {...p} />,
          table: ({ node: _n, ...p }) => (
            <table className={cn('my-1 w-full border-collapse text-[10.5px] tabular-nums', p.className)} {...p} />
          ),
          th: ({ node: _n, ...p }) => (
            <th
              className={cn('border border-border-light bg-secondary/60 px-1.5 py-1 text-left font-medium', p.className)}
              {...p}
            />
          ),
          td: ({ node: _n, ...p }) => (
            <td className={cn('border border-border-light px-1.5 py-1', p.className)} {...p} />
          ),
          ul: ({ node: _n, ...p }) => <ul className={cn('list-disc pl-4', p.className)} {...p} />,
          ol: ({ node: _n, ...p }) => <ol className={cn('list-decimal pl-4', p.className)} {...p} />,
          code: ({ node: _n, ...p }) => (
            <code className={cn('rounded-[3px] bg-secondary px-1 font-mono text-[10.5px]', p.className)} {...p} />
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  )
}

/** 原文对照：左 markdown / 右扫描件，逐行对齐；OCR 没认清的右侧画虚线下划线 */
function OriginalCompare({ fileName }: { fileName: string }) {
  const rows = DEMO_X1_ORIGINAL_COMPARE[fileName] ?? []
  if (rows.length === 0) {
    return (
      <InsetBlock className="bg-secondary/25">
        <div className="text-[10.5px] text-muted-foreground">这份没有原文对照样本</div>
      </InsetBlock>
    )
  }

  return (
    <div>
      <div className="mb-1 grid grid-cols-2 gap-2 text-[10px] text-muted-foreground">
        <span>markdown（机器读到的）</span>
        <span>扫描件（原件上写的）</span>
      </div>
      <ul className="flex flex-col gap-1">
        {rows.map((r) => (
          <li key={r.md} className="grid grid-cols-2 items-start gap-2 rounded-[6px] bg-secondary/20 px-2 py-1.5">
            <span className="min-w-0 font-mono text-[10px] leading-[1.65] break-words text-secondary-foreground">
              {r.md}
            </span>
            <span className="min-w-0">
              <span
                className={cn(
                  'text-[10px] leading-[1.65] break-words',
                  r.fidelity === 'low'
                    ? 'border-b border-dashed border-status-yellow text-status-yellow'
                    : 'text-secondary-foreground',
                )}
                title={r.fidelity === 'low' ? '这一句 OCR 没完全认准，需对照原图核' : undefined}
              >
                {r.scan}
              </span>
              <span className="ml-1 text-[9px] tabular-nums text-muted-foreground">P{r.page}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 text-[10px] text-muted-foreground">
        虚线下划线 = OCR 没完全认准的那一句，点「换 OCR 重转」可以只重转这些页。
      </div>
    </div>
  )
}

/** 抽屉里的正文区：视图切换 + 三种视图 */
export function MarkdownDoc({
  fileName,
  markdown,
  view,
  onViewChange,
}: {
  fileName: string
  markdown: string
  view: MarkdownView
  onViewChange: (v: MarkdownView) => void
}) {
  const views: MarkdownView[] = ['render', 'source', 'compare']

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5">
        {views.map((v) => {
          const active = v === view
          return (
            <button
              key={v}
              type="button"
              onClick={() => onViewChange(v)}
              aria-pressed={active}
              className={cn(
                'rounded-[6px] border px-2 py-[3px] text-[10.5px] transition-colors',
                active
                  ? 'border-foreground bg-foreground font-medium text-background'
                  : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
              )}
            >
              {MARKDOWN_VIEW_LABEL[v]}
            </button>
          )
        })}
        {view === 'compare' ? (
          <span className="ml-auto">
            <Pill tone="yellow">虚线下划线 = OCR 不确定</Pill>
          </span>
        ) : null}
      </div>

      {view === 'render' ? (
        <InsetBlock className="page-fade">
          <RenderedMarkdown markdown={markdown} />
        </InsetBlock>
      ) : null}

      {view === 'source' ? (
        <InsetBlock className="page-fade bg-secondary/20">
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-[1.75] text-secondary-foreground">
            {markdown}
          </pre>
        </InsetBlock>
      ) : null}

      {view === 'compare' ? (
        <div className="page-fade">
          <OriginalCompare fileName={fileName} />
        </div>
      ) : null}
    </div>
  )
}
