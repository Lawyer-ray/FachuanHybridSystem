/**
 * 代码块渲染：语言标签 + 一键复制。
 *
 * 为什么需要它：原先唯一的复制按钮复制的是**整条回答的 Markdown 源码**
 * （`title="复制 Markdown 源码"`）。律师的真实动作是「把这一段法条/这张表
 * 单独复制走」，整条复制等于让他自己再从几千字里挑一遍——而这个动作在一次
 * 咨询里要重复十几次。
 *
 * 为什么不改高亮方案：`rehype-highlight` 已把代码内容改写成 `<span class=
 * "hljs-*">` 树，所以「原文」不能再从 `children` 直接读字符串，必须递归取
 * 文本节点（`textOf`）。这里只做这件事，不碰高亮本身。
 */

import { memo } from 'react'
import { Check, Copy } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

/** 从 React 节点树里取纯文本（高亮后的代码被拆成多层 span，只能递归取） */
function textOf(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (typeof node === 'object' && 'props' in node) {
    return textOf((node as React.ReactElement<{ children?: React.ReactNode }>).props.children)
  }
  return ''
}

/** 从 `<code class="language-ts">` 里取语言名（取不到就返回空串，不显示标签） */
function languageOf(node: React.ReactNode): string {
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  const className = (node as React.ReactElement<{ className?: string }>).props.className ?? ''
  return /language-([\w+#-]+)/.exec(className)?.[1] ?? ''
}

export const CodeBlock = memo(function CodeBlock({
  children,
}: {
  children?: React.ReactNode
}) {
  const { copied, copy } = useCopyFeedback()
  const code = textOf(children)
  // 行尾统一去掉末尾空行：复制到 Word/邮件里多一个空行比少一行更烦人
  const payload = code.replace(/\n+$/, '')
  const lang = languageOf(children)

  return (
    <div className="group relative my-2 rounded-[9px] border border-border bg-secondary/40">
      <div className="flex items-center justify-between gap-2 border-b border-border/70 px-2.5 py-1">
        <span className="font-mono text-[10.5px] uppercase tracking-wide text-muted-foreground">
          {lang || 'code'}
        </span>
        <button
          type="button"
          className="flex items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          title={copied ? '已复制' : '复制这段代码'}
          aria-label={copied ? '已复制' : '复制这段代码'}
          onClick={() => void copy(payload)}
        >
          {copied ? <Check className="size-3" aria-hidden /> : <Copy className="size-3" aria-hidden />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="overflow-x-auto px-2.5 py-2 text-[12.5px] leading-relaxed [&>code]:bg-transparent [&>code]:p-0">
        {children}
      </pre>
    </div>
  )
})
