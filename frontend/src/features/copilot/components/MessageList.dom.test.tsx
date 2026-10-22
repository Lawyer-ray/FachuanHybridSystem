// @vitest-environment jsdom
/**
 * MessageList 的 Markdown 渲染单测（jsdom）。
 * assistant 气泡按 Markdown 输出（strong/list/table/code），user 气泡保持纯文本。
 * store 直接 setState 注入转录，不 mock 网络。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useCopilot } from '../store'
import { MessageList } from './MessageList'
import type { ChatMessage } from '../types'

function renderWithMessages(messages: ChatMessage[]) {
  useCopilot.setState({ messages, streaming: false, loadingHistory: false, approvals: [], lastError: null })
  return render(<MessageList />)
}

describe('MessageList Markdown 渲染', () => {
  it('assistant 气泡渲染 strong/列表/行内代码', () => {
    renderWithMessages([
      {
        id: 'a1',
        role: 'assistant',
        content: '**合同总体**\n\n- 总数 **165** 份\n- 在办 `list_contracts`\n',
      },
    ])

    const strong = screen.getByText('合同总体')
    expect(strong.tagName).toBe('STRONG')
    expect(screen.getByText('165').tagName).toBe('STRONG')
    expect(screen.getByText('list_contracts').tagName).toBe('CODE')
    const list = screen.getByRole('list')
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
  })

  it('user 气泡保持纯文本（不解析 markdown 语法）', () => {
    renderWithMessages([{ id: 'u1', role: 'user', content: '**这不是粗体**' }])
    expect(document.body.textContent).toContain('**这不是粗体**')
    expect(document.querySelector('strong')).toBeNull()
  })

  it('gfm 表格渲染成 table（财务口径类回答）', () => {
    renderWithMessages([
      {
        id: 'a2',
        role: 'assistant',
        content: '| 合同 | 应收 |\n| --- | --- |\n| 372 | 9000 |',
      },
    ])
    expect(screen.getByRole('table')).not.toBeNull()
    expect(screen.getByText('9000')).not.toBeNull()
  })

  it('原始 HTML 不被执行（react-markdown 默认转义）', () => {
    renderWithMessages([{ id: 'a3', role: 'assistant', content: '<img src=x onerror=alert(1)>_hi' }])
    expect(document.querySelector('img')).toBeNull()
  })
})
