// @vitest-environment jsdom
/**
 * MessageList 的 Markdown 渲染单测（jsdom）。
 * assistant 气泡按 Markdown 输出（strong/list/table/code），user 气泡保持纯文本。
 * store 直接 setState 注入转录，不 mock 网络。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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

// ============ 工具行 / thinking / 空内容 / 审批 / 错误（覆盖率补测） ============

describe('MessageList：工具行与 thinking', () => {
  it('tool 消息渲染为可折叠行，未完成显示「调用中」', () => {
    renderWithMessages([
      { id: 't1', role: 'tool', content: '', toolName: 'list_contracts' } as ChatMessage,
    ])
    expect(document.body.textContent).toContain('调用中')
    expect(document.querySelector('details')).toBeTruthy()
  })

  it('tool 消息已完成显示「已完成」', () => {
    renderWithMessages([
      { id: 't2', role: 'tool', content: '结果', toolName: 'list_contracts' } as ChatMessage,
    ])
    expect(document.body.textContent).toContain('已完成')
  })

  it('思考未结束：thinking 区默认展开', () => {
    const { container } = renderWithMessages([
      {
        id: 'a2',
        role: 'assistant',
        content: '',
        thinking: '正在推理',
        thinkingDone: false,
      } as ChatMessage,
    ])
    const details = Array.from(container.querySelectorAll('details')).find((d) =>
      d.className.includes('border-dashed'),
    )
    expect(details?.hasAttribute('open')).toBe(true)
  })

  it('思考已结束：thinking 区默认收起', () => {
    const { container } = renderWithMessages([
      {
        id: 'a3',
        role: 'assistant',
        content: '正文',
        thinking: '推理完',
        thinkingDone: true,
      } as ChatMessage,
    ])
    const details = Array.from(container.querySelectorAll('details')).find((d) =>
      d.className.includes('border-dashed'),
    )
    expect(details?.hasAttribute('open')).toBe(false)
  })
})

describe('MessageList：空内容与截断', () => {
  it('非流式且无正文无思考时显示「（无内容）」', () => {
    renderWithMessages([
      { id: 'a4', role: 'assistant', content: '', streaming: false } as ChatMessage,
    ])
    expect(document.body.textContent).toContain('（无内容）')
  })

  it('流式中不显示「（无内容）」', () => {
    renderWithMessages([
      { id: 'a5', role: 'assistant', content: '', streaming: true } as ChatMessage,
    ])
    expect(document.body.textContent).not.toContain('（无内容）')
  })

  it('truncated 时显示截断徽标', () => {
    renderWithMessages([
      { id: 'a6', role: 'assistant', content: '半截', truncated: true } as ChatMessage,
    ])
    expect(document.body.textContent).toContain('半截')
  })
})

describe('MessageList：审批卡与错误', () => {
  it('有审批时渲染 ApprovalCard', () => {
    useCopilot.setState({
      messages: [],
      streaming: false,
      loadingHistory: false,
      approvals: [
        {
          approvalId: 'ap1',
          toolName: 'delete_file',
          toolArgs: {},
          message: '将删除文件',
          receivedAt: Date.now(),
          decided: undefined,
        },
      ],
      lastError: null,
    })
    render(<MessageList />)
    expect(document.body.textContent).toContain('将删除文件')
  })

  it('有 lastError 时显示错误文案', () => {
    useCopilot.setState({
      messages: [],
      streaming: false,
      loadingHistory: false,
      approvals: [],
      lastError: '连接中断，请重试',
    })
    render(<MessageList />)
    expect(document.body.textContent).toContain('连接中断，请重试')
  })
})

describe('MessageList：排队提示与复制（P0 批次）', () => {
  it('queuePosition=3 时显示「前方 2 人」的排队条', () => {
    useCopilot.setState({
      messages: [],
      streaming: true,
      loadingHistory: false,
      approvals: [],
      lastError: null,
      queuePosition: 3,
    })
    render(<MessageList />)
    expect(document.body.textContent).toContain('前方 2 人')
  })

  it('queuePosition=1 时显示「即将开始」', () => {
    useCopilot.setState({
      messages: [],
      streaming: true,
      loadingHistory: false,
      approvals: [],
      lastError: null,
      queuePosition: 1,
    })
    render(<MessageList />)
    expect(document.body.textContent).toContain('即将开始')
    expect(document.body.textContent).not.toContain('前方')
  })

  it('queuePosition=null 时不渲染排队条', () => {
    useCopilot.setState({
      messages: [],
      streaming: true,
      loadingHistory: false,
      approvals: [],
      lastError: null,
      queuePosition: null,
    })
    render(<MessageList />)
    expect(document.body.textContent).not.toContain('排队中')
  })

  it('已完成的助手气泡有复制按钮，点击写入剪贴板', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    renderWithMessages([{ id: 'a9', role: 'assistant', content: '已完成的法律意见' }])

    const btn = screen.getByRole('button', { name: '复制回答' })
    btn.click()
    await Promise.resolve()
    expect(writeText).toHaveBeenCalledWith('已完成的法律意见')
  })

  it('流式中的助手气泡不显示复制按钮', () => {
    useCopilot.setState({
      messages: [{ id: 'a10', role: 'assistant', content: '生成中', streaming: true }],
      streaming: true,
      loadingHistory: false,
      approvals: [],
      lastError: null,
    })
    render(<MessageList />)
    expect(screen.queryByRole('button', { name: '复制回答' })).toBeNull()
  })
})
