// @vitest-environment jsdom
/**
 * MessageList 的 Markdown 渲染单测（jsdom）。
 * assistant 气泡按 Markdown 输出（strong/list/table/code），user 气泡保持纯文本。
 * store 直接 setState 注入转录，不 mock 网络。
 */
import { act, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useCopilot } from '../store'
import { MessageList } from './MessageList'
import type { ChatMessage } from '../types'

/**
 * ReactMarkdown 渲染计数（P1-3 回归用）：mock 掉它并转发给真实实现，
 * 用调用次数直接度量「历史气泡是否被重渲染」。hoisted：vi.mock 工厂先于 import 执行。
 */
const markdownSpy = vi.hoisted(() => vi.fn())
vi.mock('react-markdown', async () => {
  const actual = await vi.importActual<typeof import('react-markdown')>('react-markdown')
  markdownSpy.mockImplementation(actual.default)
  return { ...actual, default: markdownSpy }
})

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

describe('MessageList：流式重渲染（P1-3）', () => {
  it('只更新最后一条消息时，历史气泡不重渲染', () => {
    // 回归 P1-3：每个 delta 都 set({messages: s.messages.map(…)}),
    // 未 memo 的 Bubble 会让全部历史气泡的 Markdown 树重建
    const history: ChatMessage[] = [
      { id: 'a21', role: 'assistant', content: '第一条历史回答' },
      { id: 'a22', role: 'assistant', content: '第二条历史回答' },
      { id: 'a23', role: 'assistant', content: '正文', streaming: true },
    ]
    renderWithMessages(history)
    expect(markdownSpy).toHaveBeenCalledTimes(3)

    markdownSpy.mockClear()
    // 模拟一个 delta：新数组 + 只换最后一条对象，其余引用不变
    act(() => {
      useCopilot.setState({
        messages: [history[0]!, history[1]!, { ...history[2]!, content: '正文…又长了' }],
      })
    })

    // 只有流式那条重算 Markdown，两条历史气泡按引用相等 bail out
    expect(markdownSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByText('第一条历史回答')).toBeTruthy()
    expect(screen.getByText('正文…又长了')).toBeTruthy()
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

describe('MessageList：气泡对位', () => {
  it('用户消息整行贴右（ml-auto），AI 回答贴左——不两边都空', () => {
    const { container } = renderWithMessages([
      { id: 'u1', role: 'user', content: '你谁啊' } as ChatMessage,
      { id: 'a1', role: 'assistant', content: '我是助手' } as ChatMessage,
    ])
    const userRow = Array.from(container.querySelectorAll('div')).find((d) =>
      d.className.includes('max-w-[88%]'),
    )
    // 外层 flex-col 默认 stretch 会拉满整行，没有 ml-auto 时气泡会贴左
    expect(userRow?.className).toContain('ml-auto')
  })

  it('内容区限宽放宽到 max-w-6xl（侧边栏面板里 max-w-3xl 两侧会空一大块）', () => {
    const { container } = renderWithMessages([{ id: 'a1', role: 'assistant', content: 'x' } as ChatMessage])
    const limit = Array.from(container.querySelectorAll('div')).filter((d) =>
      d.className.includes('max-w-6xl'),
    )
    expect(limit.length).toBeGreaterThan(0)
    expect(container.querySelector('.max-w-3xl')).toBeNull()
  })
})

describe('MessageList：思考块自动收起', () => {
  it('思考中展开 → 正文到达（thinkingDone）后自动收起，不再占着一大块', () => {
    const thinking = { id: 'a9', role: 'assistant' as const, content: '', thinking: '推理中…', thinkingDone: false }
    const { container, rerender } = renderWithMessages([thinking as ChatMessage])
    const pick = () =>
      Array.from(container.querySelectorAll('details')).find((d) => d.className.includes('border-dashed'))
    // 思考中：展开，用户能看实时推理
    expect(pick()?.hasAttribute('open')).toBe(true)

    // 正文开始：thinkingDone 置位，同一 details 必须收起
    // （<details open> 是静态属性，只受控于挂载——这条正是那个 bug 的回归）
    useCopilot.setState({
      messages: [{ ...thinking, content: '正文到了', thinkingDone: true } as ChatMessage],
    })
    rerender(<MessageList />)
    expect(pick()?.hasAttribute('open')).toBe(false)
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

describe('MessageList：业务归属 chip（P1-5）', () => {
  it('三段渲染：长标题被截断，但 #id 单独成段完整保留', () => {
    const { container } = renderWithMessages([
      {
        id: 'u30',
        role: 'user',
        content: '梳理材料',
        bizHint: { kind: 'contract', title: '示例甲方专项法律服务合同（二期）', refId: 393 },
      },
    ])
    expect(screen.getByText(/本委托 · 示例甲方/)).toBeTruthy()
    // id 不再被整串 truncate 吃掉
    const ref = screen.getByText('#393')
    expect(ref.className).toContain('flex-none')
    expect(ref.className).not.toContain('truncate')
    // 旧口径的整串 chip 已不存在
    expect(container.textContent).not.toContain('contract_id=')
  })

  it('案件范围用「本案」单位词', () => {
    renderWithMessages([
      {
        id: 'u31',
        role: 'user',
        content: '梳理材料',
        bizHint: { kind: 'case', title: '某公司诉某银行案', refId: 217 },
      },
    ])
    expect(screen.getByText(/本案 · 某公司诉某银行案/)).toBeTruthy()
    expect(screen.getByText('#217')).toBeTruthy()
  })
})

describe('MessageList：豆包式引用卡', () => {
  const ref = (name: string, subpath: string) =>
    ({ kind: 'contract', ownerId: 393, subpath, name }) as ChatMessage['refs'] extends (infer T)[] | undefined ? T : never

  it('单引用：静态卡渲染文件名与来源路径，不再是裸 chip', () => {
    renderWithMessages([
      { id: 'u10', role: 'user', content: '看看这份', refs: [ref('专项合同.docx', '1-律师资料/1-合同/专项合同.docx')] },
    ])
    expect(screen.getByText('专项合同.docx')).toBeTruthy()
    expect(screen.getByText(/1-律师资料\/1-合同\/专项合同\.docx/)).toBeTruthy()
  })

  it('多引用：折叠卡带「共 N 个」徽标，展开列出全部来源', () => {
    renderWithMessages([
      {
        id: 'u11',
        role: 'user',
        content: '对比这两份',
        refs: [
          ref('专项合同.docx', '1-律师资料/1-合同/专项合同.docx'),
          ref('补充协议.docx', '2-补充协议/补充协议.docx'),
          ref('发票.pdf', '3-发票/发票.pdf'),
        ],
      },
    ])
    expect(screen.getByText('共 3 个')).toBeTruthy()
    // 收起时后两个来源不在摘要里（details 内容 jsdom 不做显示裁剪，按 open 态断言）
    const details = document.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    const summary = details.querySelector('summary') as HTMLElement
    summary.click()
    expect(details.open).toBe(true)
    expect(screen.getByText('补充协议.docx')).toBeTruthy()
    expect(screen.getByText('发票.pdf')).toBeTruthy()
  })
})


describe('MessageList：框选引用卡', () => {
  it('user 消息的选段引用渲染成卡：引文 + 文件来源，正文不残留块', () => {
    renderWithMessages([
      {
        id: 'u20',
        role: 'user',
        content: '这段条款什么意思？',
        quote: {
          kind: 'contract',
          ownerId: 393,
          subpath: '1-律师资料/1-合同/专项合同.docx',
          name: '专项合同.docx',
          text: '甲方拟就与对方拖欠货款之事宜，委托乙方提供专项法律服务。',
        },
      } as ChatMessage,
    ])
    expect(screen.getByText(/甲方拟就与对方拖欠货款之事宜/)).toBeTruthy()
    expect(screen.getByText(/专项合同\.docx · 1-律师资料/)).toBeTruthy()
    expect(screen.getByText('这段条款什么意思？')).toBeTruthy()
  })
})
