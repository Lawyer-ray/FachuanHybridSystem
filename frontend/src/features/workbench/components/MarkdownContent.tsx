/** Markdown 内容渲染组件

  流式渲染时用 requestAnimationFrame 节流 markdown 解析，
  每帧只解析一次，并缓存上次解析结果跳过未变化内容。
  参考 Open WebUI 的 Markdown.svelte 实现。
*/

import React, { useState, useRef, useMemo, useEffect } from 'react'
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

/** 在非代码块文本段中查找裸露 JSON 并包裹为 ```json 代码块 */
function wrapBareJsonInSegment(text: string): string {
  let result = ''
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch === '{' || ch === '[') {
      const closeCh = ch === '{' ? '}' : ']'
      let depth = 0
      let end = -1
      for (let j = i; j < text.length; j++) {
        if (text[j] === ch) depth++
        else if (text[j] === closeCh) depth--
        if (depth === 0) { end = j; break }
      }
      if (end > i) {
        const candidate = text.slice(i, end + 1)
        try {
          JSON.parse(candidate)
          result += '```json\n' + candidate + '\n```'
          i = end + 1
          continue
        } catch { /* not valid JSON, fall through */ }
      }
    }
    result += ch
    i++
  }
  return result
}

/** 将裸露 JSON 对象/数组包裹到 ```json 代码块中（跳过已有代码块） */
function wrapBareJson(content: string): string {
  const parts = content.split(/(```[^\n]*\n[\s\S]*?\n\s*```)/g)
  return parts
    .map((part, i) => (i % 2 === 0 ? wrapBareJsonInSegment(part) : part))
    .join('')
}

/** 预处理：去除【案例元数据汇总】块 + 包裹裸露 JSON */
function preprocessContent(content: string): string {
  const cleaned = content.replace(
    /```[^\n]*\n\s*【案例元数据汇总】\s*\n[\s\S]*?\n\s*```\s*$|【案例元数据汇总】\s*\n[\s\S]*$/g,
    '',
  ).trim()
  return wrapBareJson(cleaned)
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

/** 带 rAF 节流的 Markdown 渲染内容 */
function ThrottledMarkdown({ processed, isSystem }: { processed: string; isSystem?: boolean }) {
  const [displayed, setDisplayed] = useState(processed)
  const rafRef = useRef<number>(0)
  const latestRef = useRef(processed)

  useEffect(() => {
    latestRef.current = processed

    // 内容没变则跳过
    if (processed === displayed) return

    // 流式模式：rAF 节流，每帧只更新一次
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => {
      if (latestRef.current !== displayed) {
        setDisplayed(latestRef.current)
      }
    })
    return () => cancelAnimationFrame(rafRef.current)
  }, [processed, displayed])

  // 非流式（内容稳定后）立即同步
  useEffect(() => {
    if (processed !== displayed) {
      setDisplayed(processed)
    }
  }, [processed])

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
        {displayed}
      </ReactMarkdown>
    </div>
  )
}

/** Markdown 内容渲染（memo 优化，避免 streaming 时历史消息重渲染） */
export const MarkdownContent = React.memo(function MarkdownContent({
  content,
  isSystem,
  isStreaming,
}: {
  content: string
  isSystem?: boolean
  isStreaming?: boolean
}) {
  const processed = useMemo(() => preprocessContent(content), [content])

  // 流式模式使用 rAF 节流渲染
  if (isStreaming) {
    return <ThrottledMarkdown processed={processed} isSystem={isSystem} />
  }

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
