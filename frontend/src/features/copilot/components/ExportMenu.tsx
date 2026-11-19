/**
 * 会话导出入口（侧栏标题栏右侧的下拉钮）。
 *
 * 律师要把回答带进卷宗：Markdown 保留标题/引用结构，纯文本给不进 Markdown
 * 的系统粘贴。数据源与转录视图同源（store.messages），导出范围就是当前
 * 已加载窗口。
 *
 * 空会话置灰而不是隐藏：功能位置固定，没有内容时也能看出「这里能导出」。
 */

import { Download } from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { downloadText, exportFilename, toMarkdown, toPlainText } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'

/** store 空初值（SessionSidebar 的既有单测 mock 未提供 messages，兜底为空而不是崩） */
const EMPTY_MESSAGES: ChatMessage[] = []

export function ExportMenu() {
  const messages = useCopilot((s) => s.messages) ?? EMPTY_MESSAGES
  const sessionId = useCopilot((s) => s.sessionId)
  const empty = !sessionId || messages.length === 0

  const exportAs = (format: 'markdown' | 'text') => {
    const filename = exportFilename(messages)
    if (format === 'markdown') {
      downloadText(filename, toMarkdown(messages), 'text/markdown;charset=utf-8')
      return
    }
    downloadText(filename.replace(/\.md$/, '.txt'), toPlainText(messages), 'text/plain;charset=utf-8')
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={empty}
          aria-label="导出当前会话"
          title={empty ? '当前会话没有可导出的内容' : '导出当前会话'}
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[148px]">
        <DropdownMenuItem onSelect={() => exportAs('markdown')} className="text-[12.5px]">
          导出 Markdown
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => exportAs('text')} className="text-[12.5px]">
          导出纯文本
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
