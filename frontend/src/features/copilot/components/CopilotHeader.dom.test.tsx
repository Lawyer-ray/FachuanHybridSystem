// @vitest-environment jsdom
/**
 * CopilotHeader（jsdom）：把 header 从 CopilotPanel 拆出后最容易漂的接线。
 *
 * 拆组件时只有两类错误会静默发生：回调接错（点了没反应 / 关错东西）和条件
 * 渲染漏传（按钮该出现时没出现）。所以断言都落在「点了调到谁」与「什么状态
 * 显示什么」上，不测样式。
 *
 * 另有一条与本次需求直接相关：agent 后端标识必须出现在 header 里，且由
 * `currentAgentKind` 决定可切换还是只读——它就是用户理解「下一个会话用谁」
 * 的唯一入口。
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  backends: [
    { kind: 'pi', label: 'Pi', description: '', available: true, reason: '', capabilities: {} },
    { kind: 'dsh', label: 'DeepSeek Harness', description: '', available: true, reason: '', capabilities: {} },
  ],
  selectedAgentKind: 'pi',
  selectAgentKind: vi.fn<(kind: string) => void>(),
}))

vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))

import { CopilotHeader, type CopilotHeaderProps } from './CopilotHeader'

/** 默认值 = 普通对话、无业务范围、窄屏（不可并排）、无模型 */
function makeProps(overrides: Partial<CopilotHeaderProps> = {}): CopilotHeaderProps {
  return {
    railVisible: true,
    onToggleRail: vi.fn(),
    context: null,
    onExitContext: vi.fn(),
    treeDrawerOpen: false,
    onToggleTreeDrawer: vi.fn(),
    dockCapable: false,
    docked: false,
    currentTitle: '',
    currentModel: '',
    currentAgentKind: null,
    onNewSession: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  }
}

beforeEach(() => {
  storeMock.selectedAgentKind = 'pi'
  storeMock.selectAgentKind.mockClear()
})

describe('CopilotHeader：标题与开关', () => {
  it('无标题无上下文时显示默认「AI 助手」', () => {
    render(<CopilotHeader {...makeProps()} />)
    expect(screen.getByText('AI 助手')).toBeTruthy()
  })

  it('有会话标题时显示标题；业务范围内显示范围名', () => {
    render(<CopilotHeader {...makeProps({ context: { origin: 'case', refId: 7, title: '张三诉李四' } })} />)
    expect(screen.getByText('AI 助手 · 张三诉李四')).toBeTruthy()
    // 业务范围内的退出按钮（「本案」）
    expect(screen.getByRole('button', { name: '退出业务范围，回到全部会话' })).toBeTruthy()
  })

  it('会话栏开关回调接的是 onToggleRail', () => {
    const props = makeProps()
    render(<CopilotHeader {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /收起会话栏/ }))
    expect(props.onToggleRail).toHaveBeenCalledTimes(1)
  })

  it('「新对话」与「收起面板」各自只调自己的回调', () => {
    const props = makeProps()
    render(<CopilotHeader {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /新对话/ }))
    expect(props.onNewSession).toHaveBeenCalledTimes(1)
    expect(props.onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '收起 AI 助手' }))
    expect(props.onClose).toHaveBeenCalledTimes(1)
    expect(props.onNewSession).toHaveBeenCalledTimes(1)
  })
})

describe('CopilotHeader：条件渲染', () => {
  it('目录树按钮只在合同范围内出现', () => {
    const { unmount } = render(<CopilotHeader {...makeProps({ context: { origin: 'case', refId: 1, title: '某案' } })} />)
    expect(screen.queryByRole('button', { name: /合同材料目录/ })).toBeNull()
    unmount()

    render(<CopilotHeader {...makeProps({ context: { origin: 'contract', refId: 2, title: '某合同' } })} />)
    expect(screen.getByRole('button', { name: /合同材料目录/ })).toBeTruthy()
  })

  it('不传 onClose 时不渲染收起钮（独立页 AssistantPage 没有收起语义）', () => {
    render(<CopilotHeader {...makeProps({ onClose: undefined })} />)
    expect(screen.queryByRole('button', { name: '收起 AI 助手' })).toBeNull()
    // 其余开关照旧：会话栏 / 新对话仍在位
    expect(screen.getByRole('button', { name: /收起会话栏/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /新对话/ })).toBeTruthy()
  })

  it('并排按钮要同时满足「可并排」与「有回调」', () => {
    const { unmount } = render(<CopilotHeader {...makeProps({ dockCapable: false, onDockToggle: vi.fn() })} />)
    expect(screen.queryByRole('button', { name: /并排模式/ })).toBeNull()
    unmount()

    const props = makeProps({ dockCapable: true, onDockToggle: vi.fn() })
    render(<CopilotHeader {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /并排模式/ }))
    expect(props.onDockToggle).toHaveBeenCalledTimes(1)
  })

  it('模型标签只在会话有模型时出现', () => {
    const { unmount } = render(<CopilotHeader {...makeProps()} />)
    expect(screen.queryByText('qwen-max')).toBeNull()
    unmount()

    render(<CopilotHeader {...makeProps({ currentModel: 'qwen-max' })} />)
    expect(screen.getByText('qwen-max')).toBeTruthy()
  })
})

describe('CopilotHeader：agent 后端入口', () => {
  it('没有当前会话时是可切换的下拉（决定新会话用谁）', () => {
    render(<CopilotHeader {...makeProps({ currentAgentKind: null })} />)
    expect(screen.getByRole('button', { name: /后端：Pi，点击更换/ })).toBeTruthy()
  })

  it('已有会话时是只读标识（显示该会话的后端，不能改）', () => {
    render(<CopilotHeader {...makeProps({ currentAgentKind: 'dsh' })} />)
    const locked = screen.getByRole('button', { name: /本会话使用 DeepSeek Harness，不可更换/ })
    expect(locked).toBeTruthy()
    // 只读态不再提供 listbox
    fireEvent.click(locked)
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})

describe('CopilotHeader：全屏入口', () => {
  // 顶栏左侧导航里也有一个叫「AI 助手」的入口，但那是跳到 /assistant 新页面；
  // 顶栏右侧同名按钮开的是抽屉。两个入口同名，用户点了右边的就以为「跳转坏了」
  // （真实反馈）。所以抽屉头部必须有一个明确的「全屏」钮。
  it('传了 onExpand 才渲染全屏钮，点击回调它', () => {
    const onExpand = vi.fn()
    render(<CopilotHeader {...makeProps({ onExpand })} />)

    const button = screen.getByLabelText('在全屏窗口中打开 AI 助手')
    button.click()

    expect(onExpand).toHaveBeenCalledTimes(1)
  })

  it('没传 onExpand 时不渲染（独立页自己就是全屏，再放一个没意义）', () => {
    render(<CopilotHeader {...makeProps()} />)

    expect(screen.queryByLabelText('在全屏窗口中打开 AI 助手')).toBeNull()
  })
})
