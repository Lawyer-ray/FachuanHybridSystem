/** 对话导出工具 */

import type { WorkbenchMessage } from '../types'

/** 将消息列表导出为 Markdown 字符串 */
export function exportToMarkdown(messages: WorkbenchMessage[], title: string): string {
  const lines: string[] = [
    `# ${title}`,
    '',
    `> 导出时间: ${new Date().toLocaleString('zh-CN')}`,
    '',
  ]

  for (const msg of messages) {
    switch (msg.role) {
      case 'user':
        lines.push(`## 用户`, '', msg.content, '')
        break
      case 'assistant':
        lines.push(`## 助手`, '', msg.content, '')
        if (msg.llm_model) {
          lines.push(`*模型: ${msg.llm_model}*`, '')
        }
        break
      case 'tool':
        lines.push(`### 工具: ${msg.tool_name || '未知'}`, '')
        if (msg.tool_output && Object.keys(msg.tool_output).length > 0) {
          lines.push('```json', JSON.stringify(msg.tool_output, null, 2), '```', '')
        }
        break
      case 'system':
        lines.push(`> ${msg.content}`, '')
        break
    }
    lines.push('---', '')
  }

  return lines.join('\n')
}

/** 触发浏览器文件下载 */
export function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
