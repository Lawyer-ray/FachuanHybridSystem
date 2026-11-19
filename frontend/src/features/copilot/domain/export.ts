/**
 * 会话导出：转录 → Markdown / 纯文本（律师要把回答带进卷宗）。
 *
 * 除 `downloadText` 外均为纯函数（无 React、无 IO），node 环境直接单测。
 * 导出内容只取当前已加载窗口，与转录视图看到的完全一致。
 */

import type { ChatMessage } from '../types'
import { DEFAULT_AGENT_KIND } from './dual'
import { bizHintParts } from './transcript'

export interface ExportOptions {
  /** 是否导出思考过程（默认否：卷宗只要结论） */
  includeThinking?: boolean
  /** 是否导出工具调用（默认否：工具结果对卷宗是噪音） */
  includeTools?: boolean
  /** 文档标题（默认「法穿问答」） */
  title?: string
}

const DEFAULT_TITLE = '法穿问答'

/** 引用卡/业务锚点压成一行（气泡上方的 chip 在导出里只留一句可读文本） */
function referenceLine(message: ChatMessage): string | null {
  const parts: string[] = []
  if (message.bizHint) {
    const biz = bizHintParts(message.bizHint)
    parts.push(`${biz.unit}“${biz.title}” ${biz.ref}`)
  }
  if (message.pageHint) parts.push(`页面：${message.pageHint}`)
  for (const ref of message.refs ?? []) parts.push(`${ref.isFolder ? '目录' : '文件'}：${ref.name}`)
  if (message.quote) parts.push(`选段：${message.quote.name}「${clip(message.quote.text, 40)}」`)
  return parts.length > 0 ? parts.join('；') : null
}

/** 单行化并截到 max 字（中文按 code point 数，超出补省略号） */
function clip(text: string, max: number): string {
  const chars = [...text.replace(/\s+/g, ' ').trim()]
  return chars.length > max ? `${chars.slice(0, max).join('')}…` : chars.join('')
}

/** 助手栏头：`pi · kimi-2.6`（旧数据无 agent 时按 pi，与界面同口径） */
function answerHeading(message: ChatMessage): string {
  const agent = message.agentKind || DEFAULT_AGENT_KIND
  const model = message.model?.trim()
  return model ? `${agent} · ${model}` : agent
}

/** 工具行：`- 🔧 工具名：结果首行` */
function toolLine(tool: ChatMessage): string {
  const first = tool.content.split('\n')[0]?.trim() || '（无输出）'
  return `- 🔧 ${tool.toolName || '工具'}：${first}`
}

/** 一条 assistant 消息 → 若干行（多答时每条各成一栏，同一函数渲染） */
function appendAnswer(out: string[], message: ChatMessage, opts: ExportOptions, markdown: boolean): void {
  // 多答里没跑成的那一栏没有正文可导出，跳过整栏（不留下空标题）
  if (message.failed && !message.content.trim()) return
  out.push(markdown ? `### ${answerHeading(message)}` : answerHeading(message), '')
  const thinking = message.thinking?.trim()
  if (opts.includeThinking && thinking) {
    if (markdown) out.push(...thinking.split('\n').map((line, i) => `> ${i === 0 ? '思考：' : ''}${line}`))
    else out.push(`思考：${thinking}`)
    out.push('')
  }
  const body = message.content.trim()
  if (body) out.push(body, '')
  if (message.truncated) {
    out.push(markdown ? '> （本条被中断，内容可能不完整）' : '（本条被中断，内容可能不完整）', '')
  }
  if (opts.includeTools && message.tools?.length) {
    for (const tool of message.tools) out.push(toolLine(tool))
    out.push('')
  }
}

/** 两种格式共用同一遍遍历，只有标题/引用/提示的包装不同 */
function render(messages: ChatMessage[], opts: ExportOptions, markdown: boolean): string {
  const title = opts.title?.trim() || DEFAULT_TITLE
  const out: string[] = [markdown ? `# ${title}` : title, '']
  for (const message of messages) {
    if (message.role === 'user') {
      out.push(markdown ? '## 我：' : '我：', '')
      const ref = referenceLine(message)
      if (ref) out.push(markdown ? `> 引用：${ref}` : `引用：${ref}`, '')
      const body = message.content.trim()
      if (body) out.push(body, '')
      continue
    }
    if (message.role === 'tool') {
      // 工具默认不导出；单栏转录里的 tool 消息开启后才作为行内明细出现
      if (opts.includeTools) out.push(toolLine(message), '')
      continue
    }
    appendAnswer(out, message, opts, markdown)
  }
  return `${out.join('\n').trimEnd()}\n`
}

export function toMarkdown(messages: ChatMessage[], opts: ExportOptions = {}): string {
  return render(messages, opts, true)
}

export function toPlainText(messages: ChatMessage[], opts: ExportOptions = {}): string {
  return render(messages, opts, false)
}

/** `法穿问答-2026-11-20-0930.md`（取用户消息做 slug 会拖长文件名，暂不做） */
export function exportFilename(_messages: ChatMessage[], now = Date.now()): string {
  const d = new Date(now)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `法穿问答-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.md`
}

/** 前端本地合成下载（Blob → ObjectURL → `<a download>`），用完必须回收 URL */
export function downloadText(filename: string, text: string, mime = 'text/plain;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    // 与 lib/download.saveBlob 同口径：Firefox 的 a.click() 异步派发，同步 revoke 会下到空文件
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}
