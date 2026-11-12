// @vitest-environment jsdom
/**
 * PhaseAiDesignPane：「✦ AI 设计（对话）」页签 —— 左活的草稿 / 右对话。
 *
 * 这一页的设计判断是「多轮对话逐步逼近」，所以三条不变式必须钉住：
 * - 发送一句话 = 一次建议器调用（输入带上下文：当前草稿 + 选中阶段），
 *   草稿整树交回父级（父级独占对话历史，关弹窗再开能接着聊）；
 * - 每轮追加**两条**消息（user 原文 + ai 回复及其改动清单），发送后输入框清空；
 * - 空白输入不发送（不发空消息、不改草稿、不调建议器）。
 *
 * 另外覆盖：草稿为空/未命名/有验收标准与子阶段的呈现差异、点 ↑ 与回车等价。
 * 建议器注入假实现，真实规则由 special-design-assistant 自己的测试覆盖。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PhaseAiDesignPane, type AiDesignMessage } from './PhaseAiDesignPane'
import type { PhaseDesignAssistant } from './special-design-assistant'
import type { PhaseNode } from './special-phase-tree'

function node(over: Partial<PhaseNode> = {}): PhaseNode {
  return { key: 'ph_1', name: '尽职调查', acceptance: '', open: false, startDate: '', folders: [], deliverables: [], ...over }
}

const DRAFT: PhaseNode[] = [
  node({
    key: 'a',
    name: '尽职调查',
    acceptance: '报告已交付',
    deliverables: [
      { id: 'd1', date: '2026-10-03', name: '《尽调报告》', version: 'v2', state: 'ok', subpath: 'p/a.pdf', planned: false },
    ],
  }),
  node({ key: 'b', name: '方案设计', folders: [node({ key: 'b1', name: '职工安置' })] }),
]

/** 假建议器：记录入参，返回一棵「改过的」草稿 */
function fakeAssistant(): PhaseDesignAssistant {
  return {
    hints: () => [],
    suggest: vi.fn(() => ({
      draft: [node({ key: 'z', name: '税务清算' })],
      reply: '已把税务清算单独拆成一步',
      changes: ['新增阶段「税务清算」'],
      unchanged: false,
    })),
  }
}

function setup(over: Partial<Parameters<typeof PhaseAiDesignPane>[0]> = {}) {
  const handlers = {
    draft: DRAFT,
    selKey: null as string | null,
    messages: [] as AiDesignMessage[],
    onMessages: vi.fn(),
    onChangeDraft: vi.fn(),
    assistant: fakeAssistant(),
    ...over,
  }
  const view = render(<PhaseAiDesignPane {...handlers} />)
  const input = screen.getByPlaceholderText('说出要改的地方，如「职工安置单独拆一步」') as HTMLInputElement
  return { ...handlers, ...view, input }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PhaseAiDesignPane · 左栏草稿', () => {
  it('按编号与名称列出阶段，并给出交付物/验收/子阶段摘要', () => {
    setup()
    // 「N 阶段」与阶段行文字贴在一起，用容器文本断言
    expect(document.body.textContent).toContain('3 阶段')
    expect(screen.getByText('尽职调查')).toBeTruthy()
    expect(screen.getByText('1 交付物 · 有验收标准')).toBeTruthy()
    expect(screen.getByText('0 交付物 · 缺验收标准 · 1 子')).toBeTruthy()
  })

  it('草稿为空时给空态，不渲染阶段行', () => {
    setup({ draft: [] })
    expect(screen.getByText('还没有阶段')).toBeTruthy()
    expect(screen.getByText('0 阶段')).toBeTruthy()
  })

  it('未命名阶段用占位文案（空名字不占视觉重心）', () => {
    setup({ draft: [node({ key: 'x', name: '' })] })
    expect(screen.getByText('未命名阶段')).toBeTruthy()
  })
})

describe('PhaseAiDesignPane · 对话', () => {
  it('开场白默认就在，父级传来的历史逐条追加', () => {
    setup({
      messages: [
        { role: 'user', text: '把税务清算拆出来', changes: [], unchanged: false },
        { role: 'ai', text: '已拆分', changes: ['新增「税务清算」'], unchanged: false },
      ],
    })
    expect(screen.getByText('把税务清算拆出来')).toBeTruthy()
    expect(screen.getByText('新增「税务清算」')).toBeTruthy()
  })

  it('发送：建议器拿到输入 + 当前草稿 + 选中阶段，结果同时交回 onMessages / onChangeDraft', () => {
    const { input, onMessages, onChangeDraft, assistant, selKey } = setup({ selKey: 'a' })

    fireEvent.change(input, { target: { value: '把税务清算单独拆一步' } })
    fireEvent.click(screen.getByTitle('发送（回车）'))

    expect(assistant.suggest).toHaveBeenCalledWith({
      text: '把税务清算单独拆一步',
      draft: DRAFT,
      selectedKey: selKey,
    })
    // 草稿整树交回（父级是唯一持有者，这里不做二次合并）
    expect(onChangeDraft).toHaveBeenCalledWith([node({ key: 'z', name: '税务清算' })])
    // 每轮追加两条：user 原文（无 changes）+ ai 回复（带 changes）
    expect(onMessages).toHaveBeenCalledWith([
      { role: 'user', text: '把税务清算单独拆一步', changes: [], unchanged: false },
      { role: 'ai', text: '已把税务清算单独拆成一步', changes: ['新增阶段「税务清算」'], unchanged: false },
    ])
    expect(input.value).toBe('')
  })

  it('回车与点 ↑ 等价，且回车不会提交表单默认行为', () => {
    const { input, onMessages } = setup()
    fireEvent.change(input, { target: { value: '拆细一点' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onMessages).toHaveBeenCalledTimes(1)

    fireEvent.change(input, { target: { value: '继续' } })
    fireEvent.keyDown(input, { key: 'a' })
    expect(onMessages).toHaveBeenCalledTimes(1)
  })

  it('空白输入不发送：不调建议器、不改草稿、不清空（保留用户敲的空格便于继续写）', () => {
    const { input, onMessages, onChangeDraft, assistant } = setup()
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByTitle('发送（回车）'))
    expect(assistant.suggest).not.toHaveBeenCalled()
    expect(onMessages).not.toHaveBeenCalled()
    expect(onChangeDraft).not.toHaveBeenCalled()
  })

  it('建议器说「没改」时回复用虚线弱化（unchanged 透传）', () => {
    const assistant: PhaseDesignAssistant = {
      hints: () => [],
      suggest: vi.fn(() => ({ draft: DRAFT, reply: '这句不用改', changes: [], unchanged: true })),
    }
    const messages: AiDesignMessage[] = [{ role: 'ai', text: '这句不用改', changes: [], unchanged: true }]
    setup({ assistant, messages })
    const bubble = screen.getByText('这句不用改')
    expect(bubble.className).toContain('border-dashed')
    expect(bubble.className).toContain('text-muted-foreground')
  })
})
