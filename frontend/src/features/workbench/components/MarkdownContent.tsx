/** Markdown 内容渲染组件 */

import React, { useState, useRef, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github-dark.css'
import { Copy, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { copyToClipboard } from '@/lib/clipboard'
import { LegalText } from './LegalText'

// 只注册 json 语言（工具调用 JSON 高亮用）
hljs.registerLanguage('json', json)

/** 预处理：去除【案例元数据汇总】块（兜底，正常情况下 store 已剥离） */
function preprocessContent(content: string): string {
  return content.replace(
    /```[^\n]*\n\s*【案例元数据汇总】\s*\n[\s\S]*?\n\s*```\s*$|【案例元数据汇总】\s*\n[\s\S]*$/g,
    '',
  ).trim()
}

/** 从 ReactMarkdown children 中提取纯文本，如果包含非文本元素则返回 null */
function extractTextContent(children: React.ReactNode): string | null {
  if (typeof children === 'string') return children
  if (!Array.isArray(children)) return null

  let text = ''
  for (const child of children) {
    if (typeof child === 'string') {
      text += child
    } else if (
      React.isValidElement(child) &&
      typeof child.props === 'object' &&
      child.props !== null &&
      'children' in child.props
    ) {
      const nested = extractTextContent((child.props as { children: React.ReactNode }).children)
      if (nested === null) return null
      text += nested
    } else {
      return null
    }
  }
  return text
}

/** 代码块（带语言标签 + 复制按钮） */
function CodeBlockWithCopy({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
  const codeRef = useRef<HTMLElement>(null)
  const [copied, setCopied] = useState(false)

  const codeChild = React.Children.only(children) as React.ReactElement<{ className?: string }>
  const className = codeChild?.props?.className || ''
  const language = className.replace('hljs language-', '').replace('language-', '') || ''

  const handleCopy = () => {
    const text = codeRef.current?.textContent || ''
    copyToClipboard(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="relative group/code my-2">
      <div className="flex items-center justify-between rounded-t-md border border-border/50 border-b-0 bg-card px-3 py-1 text-[11px] text-muted-foreground">
        <span>{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center justify-center rounded p-0.5 hover:bg-accent hover:text-foreground transition-colors"
          title="复制代码"
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
        </button>
      </div>
      <pre
        {...props}
        className="!rounded-t-none !mt-0 !border-t-0 whitespace-pre-wrap break-words border border-border/50 bg-card p-3 text-xs overflow-x-auto"
      >
        {React.cloneElement(codeChild as React.ReactElement<Record<string, unknown>>, { ref: codeRef })}
      </pre>
    </div>
  )
}

/** Markdown 内容渲染（memo 优化，避免 streaming 时历史消息重渲染） */
export const MarkdownContent = React.memo(function MarkdownContent({
  content,
  isSystem,
}: {
  content: string
  isSystem?: boolean
}) {
  const processed = useMemo(() => preprocessContent(content), [content])

  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none break-words overflow-hidden',
        'prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0',
        'prose-code:before:content-none prose-code:after:content-none',
        'prose-code:bg-card prose-code:border prose-code:border-border/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs',
        'prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1',
        'prose-hr:my-2 prose-blockquote:my-1 prose-blockquote:border-l-2',
        'text-foreground',
        isSystem && 'prose-red',
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: CodeBlockWithCopy,
          p: ({ children, ...props }) => {
            const textContent = extractTextContent(children)
            if (textContent) {
              return <p {...props}><LegalText text={textContent} /></p>
            }
            return <p {...props}>{children}</p>
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  )
})
