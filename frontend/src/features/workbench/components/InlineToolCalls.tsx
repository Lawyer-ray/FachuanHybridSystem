/** 内联工具调用列表组件 */

import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github-dark.css'
import type { WorkbenchMessage } from '../types'
import { renderToolResult } from './tool-results'

hljs.registerLanguage('json', json)

/** JSON 语法高亮块 */
function JsonBlock({ data }: { data: unknown }) {
  const jsonStr = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  const html = hljs.highlight(jsonStr, { language: 'json' }).value
  return (
    <pre className="whitespace-pre-wrap break-words bg-background/50 rounded p-1.5 text-[11px] overflow-x-auto">
      <code dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  )
}

/** 工具调用结果内容（结构化渲染优先，回退到 JSON） */
function ToolResultContent({ tool }: { tool: WorkbenchMessage }) {
  const hasInput = Object.keys(tool.tool_input).length > 0
  const hasOutput = Object.keys(tool.tool_output).length > 0
  const structured = renderToolResult({
    output: tool.tool_output,
    input: tool.tool_input,
    toolName: tool.tool_name || '',
  })

  if (!structured) {
    return (
      <>
        {hasInput && (
          <div>
            <div className="text-muted-foreground mb-1">输入</div>
            <JsonBlock data={tool.tool_input} />
          </div>
        )}
        {hasOutput && (
          <div>
            <div className="text-muted-foreground mb-1">输出</div>
            <JsonBlock data={tool.tool_output} />
          </div>
        )}
      </>
    )
  }

  return (
    <>
      {structured}
      {hasOutput && (
        <details className="group">
          <summary className="text-[10px] text-muted-foreground cursor-pointer hover:text-foreground">
            原始 JSON
          </summary>
          <div className="mt-1">
            <JsonBlock data={tool.tool_output} />
          </div>
        </details>
      )}
    </>
  )
}

/** 单个内联工具调用（可折叠，支持结构化渲染） */
function InlineToolCall({ tool }: { tool: WorkbenchMessage }) {
  const [expanded, setExpanded] = useState(false)
  const hasError = tool.metadata?.success === false

  return (
    <div className="rounded-md border border-border/50 bg-background/50 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-accent/50 rounded-md transition-colors"
      >
        {hasError ? (
          <XCircle className="size-3 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="size-3 shrink-0 text-green-500" />
        )}
        <span className="font-medium">{tool.tool_name || '工具调用'}</span>
        <span className="flex-1" />
        {expanded ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-border/50 px-2.5 py-2 space-y-2">
          <ToolResultContent tool={tool} />
        </div>
      )}
    </div>
  )
}

/** 内联工具调用列表 */
export function InlineToolCalls({ toolCalls }: { toolCalls: WorkbenchMessage[] }) {
  return (
    <div className="mt-2 space-y-1">
      {toolCalls.map((tc) => (
        <InlineToolCall key={tc.id} tool={tc} />
      ))}
    </div>
  )
}
