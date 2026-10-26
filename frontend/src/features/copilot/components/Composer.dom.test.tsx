// @vitest-environment jsdom
/**
 * TurnStatsView 与 Composer 测试（jsdom）。
 *
 * TurnStatsView：流式中显示 ≈ tok/s、结束后显示精确 tokens 与平均速度、
 * 无数据时不渲染。Composer：Enter 发送、Shift+Enter 换行、IME 组合中不发送、
 * `/` 命令菜单（技能补全 / compact 命令）、底栏上下文水位。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const copilotState = vi.hoisted(() => ({
  streaming: false,
  queuedSteers: [] as string[],
  pendingFiles: [] as File[],
  pendingRefs: [] as { contractId: number; subpath: string; name: string }[],
  uploadingAttachments: false,
  sessionId: null as string | null,
  messages: [] as unknown[],
  contextUsage: { used: null as number | null, total: null as number | null },
  compacting: false,
  turnStats: {
    firstDeltaAt: null as number | null,
    lastDeltaAt: null as number | null,
    doneAt: null as number | null,
    estTokens: 0,
    exactTokens: null as number | null,
    samples: [] as number[],
  },
  send: vi.fn(),
  stop: vi.fn(),
  steer: vi.fn(),
  revokeQueuedSteers: vi.fn(),
  submitTask: vi.fn(),
  addAttachmentFiles: vi.fn(),
  removeAttachmentFile: vi.fn(),
  removeFolderRef: vi.fn(),
  compactContext: vi.fn(),
}))

vi.mock('../store', () => ({
  useCopilot: Object.assign(
    (selector: (s: typeof copilotState) => unknown) => selector(copilotState),
    { getState: () => copilotState },
  ),
}))

/** 技能清单 mock：菜单数据源（避免真实网络请求） */
const skillsMock = vi.hoisted(() => vi.fn())
vi.mock('../api', () => ({
  fetchAgentSkills: skillsMock,
}))

import { TurnStatsView } from './TurnStatsView'
import { Composer } from './Composer'

/** Composer 带 react-query Provider 渲染（useQuery 技能清单依赖） */
function renderComposer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rendered = render(
    <QueryClientProvider client={client}>
      <Composer />
    </QueryClientProvider>,
  )
  return { client, ...rendered }
}

beforeEach(() => {
  copilotState.streaming = false
  copilotState.queuedSteers = []
  copilotState.pendingFiles = []
  copilotState.pendingRefs = []
  copilotState.uploadingAttachments = false
  copilotState.sessionId = null
  copilotState.messages = []
  copilotState.contextUsage = { used: null, total: null }
  copilotState.compacting = false
  copilotState.send = vi.fn()
  copilotState.stop = vi.fn()
  copilotState.steer = vi.fn()
  copilotState.revokeQueuedSteers = vi.fn()
  copilotState.submitTask = vi.fn()
  copilotState.addAttachmentFiles = vi.fn()
  copilotState.removeAttachmentFile = vi.fn()
  copilotState.removeFolderRef = vi.fn()
  copilotState.compactContext = vi.fn()
  skillsMock.mockResolvedValue({
    skills: [
      { name: 'web-research', description: '联网搜索与网页原文抓取', enabled: true },
      { name: 'deadline-queries', description: '期限/排期查询', enabled: true },
      { name: 'disabled-skill', description: '已停用', enabled: false },
    ],
  })
  copilotState.turnStats = {
    firstDeltaAt: null,
    lastDeltaAt: null,
    doneAt: null,
    estTokens: 0,
    exactTokens: null,
    samples: [],
  }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('TurnStatsView（结束后）', () => {
  it('无 doneAt 时不渲染', () => {
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('显示精确 tokens 与平均速度、用时', () => {
    copilotState.turnStats = {
      firstDeltaAt: 1000,
      lastDeltaAt: 3000,
      doneAt: 4000,
      estTokens: 120,
      exactTokens: 150,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    const text = container.textContent ?? ''
    expect(text).toContain('150 tokens')
    expect(text).toContain('平均')
    expect(text).toContain('tok/s')
    // 用时 3s（4000-1000）
    expect(text).toContain('3.0s')
    container.remove()
  })

  it('无精确计数时用估算值并加 ≈ 前缀', () => {
    copilotState.turnStats = {
      firstDeltaAt: 0,
      lastDeltaAt: 2000,
      doneAt: 2000,
      estTokens: 80,
      exactTokens: null,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toContain('≈')
    expect(container.textContent).toContain('80 tokens')
    container.remove()
  })

  it('用时超过 100s 时不显示小数', () => {
    copilotState.turnStats = {
      firstDeltaAt: 0,
      lastDeltaAt: 200_000,
      doneAt: 200_000,
      estTokens: 10,
      exactTokens: 10,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toContain('200s')
    container.remove()
  })
})

describe('TurnStatsView（流式中）', () => {
  it('无数据时不渲染', () => {
    copilotState.streaming = true
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('有样本时以 250ms 刷新显示 ≈ tok/s', () => {
    vi.useFakeTimers()
    copilotState.streaming = true
    const now = Date.now()
    copilotState.turnStats = {
      firstDeltaAt: now - 1000,
      lastDeltaAt: now,
      doneAt: null,
      estTokens: 50,
      exactTokens: null,
      samples: [now - 1000, now - 500, now],
    }
    const { container } = render(<TurnStatsView />)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(container.textContent).toContain('tok/s')
    container.remove()
  })
})

describe('Composer', () => {
  it('Enter 发送并清空输入', () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.send).toHaveBeenCalledWith('你好', expect.any(Function))
    container.remove()
  })

  it('Shift+Enter 换行不发送', () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('空白输入不发送', () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '   ' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('IME 组合中按 Enter 不发送（中文候选确认）', () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('流式中显示停止按钮，点击调用 stop；输入框保持可用', () => {
    copilotState.streaming = true
    const { container } = renderComposer()
    fireEvent.click(within(container).getByRole('button', { name: '停止生成' }))
    expect(copilotState.stop).toHaveBeenCalled()
    // 流式中仍可插话：textarea 未禁用，占位符切为插话提示
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    expect(box.disabled).toBe(false)
    expect(box.placeholder).toContain('插话')
    container.remove()
  })

  it('流式中 Enter 发送的是插话（steer）而不是新消息', () => {
    copilotState.streaming = true
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '补充：只要近一个月' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.steer).toHaveBeenCalledWith('补充：只要近一个月')
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('流式中有已插话时显示计数与撤回按钮', () => {
    copilotState.streaming = true
    copilotState.queuedSteers = ['插话一', '插话二']
    const { container } = renderComposer()
    expect(container.textContent).toContain('已插话 2 条')
    fireEvent.click(within(container).getByRole('button', { name: '撤回插话' }))
    expect(copilotState.revokeQueuedSteers).toHaveBeenCalled()
    container.remove()
  })

  it('后台运行模式：提交走 submitTask 并自动退出模式', () => {
    const { container } = renderComposer()
    const toggle = within(container).getByRole('button', { name: '切换为后台运行' })
    fireEvent.click(toggle)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    expect(box.placeholder).toContain('后台运行')
    fireEvent.change(box, { target: { value: '梳理本案材料' } })
    fireEvent.click(within(container).getByRole('button', { name: '提交后台任务' }))
    expect(copilotState.submitTask).toHaveBeenCalledWith('梳理本案材料')
    expect(copilotState.send).not.toHaveBeenCalled()
    // 提交后模式自动退出，下一次输入回到常规发送
    expect(box.placeholder).not.toContain('后台运行')
    container.remove()
  })

  it('非流式时发送按钮在空输入下禁用', () => {
    const { container } = renderComposer()
    const btn = within(container).getByRole('button', { name: '发送' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    container.remove()
  })

  it('有待发附件时发送按钮可用，chip 可移除（P1-11）', () => {
    copilotState.pendingFiles = [new File(['x'], '合同.pdf', { type: 'application/pdf' })]
    const { container } = renderComposer()
    const btn = within(container).getByRole('button', { name: '发送' }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    expect(container.textContent).toContain('合同.pdf')
    fireEvent.click(within(container).getByRole('button', { name: '移除附件 合同.pdf' }))
    expect(copilotState.removeAttachmentFile).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('回形针按钮可点（选择文件入口）', () => {
    const { container } = renderComposer()
    expect(within(container).getByRole('button', { name: '添加附件' })).toBeTruthy()
    container.remove()
  })
})

describe('Composer `/` 命令菜单', () => {
  it('`/` 打开菜单并列出技能与命令，Enter 补全技能前缀', async () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '/' } })
    // react-query 异步取技能清单后菜单出现（wait 到技能项渲染为止）
    await waitFor(() => expect(within(container).getByRole('listbox').textContent).toContain('/skill:web-research'))
    const menu = within(container).getByRole('listbox')
    expect(within(menu).getAllByRole('option').length).toBeGreaterThan(1)
    // 移到第一个技能按 Enter：不发送消息、文本被替换为 /skill: 前缀
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    fireEvent.keyDown(box, { key: 'ArrowDown' }) // 移到第一个技能
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.send).not.toHaveBeenCalled()
    expect(box.value.startsWith('/skill:')).toBe(true)
    container.remove()
  })

  it('过滤匹配技能名，Tab 同样生效', async () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '/deadline' } })
    await waitFor(() => expect(within(container).getByRole('listbox').textContent).toContain('/skill:deadline-queries'))
    const menu = within(container).getByRole('listbox')
    expect(menu.textContent).not.toContain('web-research')
    fireEvent.keyDown(box, { key: 'Tab' })
    expect(box.value.startsWith('/skill:deadline-queries')).toBe(true)
    container.remove()
  })

  it('Esc 关闭菜单，同查询词不再弹出', async () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '/' } })
    await act(async () => {})
    fireEvent.keyDown(box, { key: 'Escape' })
    expect(within(container).queryByRole('listbox')).toBeNull()
    container.remove()
  })

  it('无会话时 compact 禁用且 Enter 不触发动作；有会话时触发压缩并清空输入', async () => {
    const { container } = renderComposer()
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '/compact' } })
    await act(async () => {})
    const menu = within(container).getByRole('listbox')
    expect(menu.textContent).toContain('先开始对话')
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.compactContext).not.toHaveBeenCalled()
    expect(box.value).toBe('/compact')
    container.remove()

    // 有会话（且已有消息）时命令可用
    copilotState.sessionId = 's-1'
    copilotState.messages = [{ id: 'db-1' }]
    const second = renderComposer()
    const box2 = within(second.container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box2, { target: { value: '/compact' } })
    await act(async () => {})
    fireEvent.keyDown(box2, { key: 'Enter' })
    expect(copilotState.compactContext).toHaveBeenCalled()
    expect(box2.value).toBe('')
    second.container.remove()
  })

  it('已停用技能不出现在菜单里', async () => {
    const { container } = renderComposer()
    fireEvent.change(within(container).getByRole('textbox'), { target: { value: '/' } })
    await act(async () => {})
    expect(container.textContent).not.toContain('disabled-skill')
    container.remove()
  })
})

describe('Composer 上下文水位', () => {
  it('水位已知时显示百分比，≥80% 不再额外强调（样式交给 CSS）', () => {
    copilotState.contextUsage = { used: 65536, total: 131072 }
    const { container } = renderComposer()
    expect(container.textContent).toContain('上下文 50%')
    container.remove()
  })

  it('水位未知（null）时隐藏显示', () => {
    const { container } = renderComposer()
    expect(container.textContent).not.toContain('上下文')
    container.remove()
  })

  it('压缩中显示「正在压缩上下文…」', () => {
    copilotState.compacting = true
    copilotState.contextUsage = { used: 1, total: 2 }
    const { container } = renderComposer()
    expect(container.textContent).toContain('正在压缩上下文…')
    expect(container.textContent).not.toContain('上下文 50%')
    container.remove()
  })
})
