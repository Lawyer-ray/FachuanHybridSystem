// @vitest-environment jsdom
/**
 * AgentBackendPicker（jsdom）：切换语义与不可用置灰。
 *
 * 本组件只有一种形态：新对话的下拉（「已有会话」由 CopilotHeader 不渲染它，
 * 后端名改成标题后缀——那条断言在 CopilotHeader.dom.test.tsx 里）。所以这里只测
 * 下拉本身：
 *  · 选项中显示中文名，选中回调 kind；
 *  · `available=false` → 选项 disabled 且副标题是**原因**（不是 description）；
 *  · 能力位 `approval=false` 才挂「无审批」徽标；
 *  · 清单为空 → 说一句「将使用默认后端」，不留空白菜单。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  backends: [] as Array<{
    kind: string
    label: string
    description: string
    available: boolean
    reason: string
    capabilities: Record<string, boolean>
  }>,
  selectedAgentKind: '',
  selectAgentKind: vi.fn<(kind: string) => void>(),
}))

vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))

import { AgentBackendPicker } from './AgentBackendPicker'

function option(kind: string, label: string, available = true, reason = '', approval = true) {
  return {
    kind,
    label,
    description: `${label} 的说明`,
    available,
    reason,
    capabilities: { approval },
  }
}

beforeEach(() => {
  storeMock.backends = [option('pi', 'Pi'), option('dsh', 'DeepSeek Harness')]
  storeMock.selectedAgentKind = 'pi'
  storeMock.selectAgentKind.mockClear()
})

describe('AgentBackendPicker：新建会话可切换', () => {
  it('显示当前选择，点击后列出全部后端', () => {
    render(<AgentBackendPicker />)

    const trigger = screen.getByRole('button', { name: /后端：Pi/ })
    fireEvent.click(trigger)

    expect(screen.getByRole('listbox', { name: '可选 agent 后端' })).toBeTruthy()
    expect(screen.getByRole('option', { name: /Pi/ })).toBeTruthy()
    expect(screen.getByRole('option', { name: /DeepSeek Harness/ })).toBeTruthy()
  })

  it('选中后端时回调 kind 并收起列表', () => {
    render(<AgentBackendPicker />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    fireEvent.click(screen.getByRole('option', { name: /DeepSeek Harness/ }))

    expect(storeMock.selectAgentKind).toHaveBeenCalledWith('dsh')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('不可用的后端置灰，副标题显示原因而不是说明', () => {
    storeMock.backends = [
      option('pi', 'Pi'),
      option('dsh', 'DeepSeek Harness', false, '未安装 DeepSeek Harness SDK'),
    ]
    render(<AgentBackendPicker />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    const dsh = screen.getByRole('option', { name: /DeepSeek Harness/ }) as HTMLButtonElement
    expect(dsh.disabled).toBe(true)
    expect(dsh.textContent).toContain('未安装 DeepSeek Harness SDK')
    expect(dsh.textContent).not.toContain('DeepSeek Harness 的说明')
  })

  it('点不可用项不会触发选择（防止灰项被程序路径选中）', () => {
    storeMock.backends = [option('pi', 'Pi'), option('dsh', 'DeepSeek Harness', false, '未配置可用的 LLM 平台')]
    render(<AgentBackendPicker />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    fireEvent.click(screen.getByRole('option', { name: /DeepSeek Harness/ }))

    expect(storeMock.selectAgentKind).not.toHaveBeenCalled()
  })

  it('清单为空时说明会用默认后端（不显示空白菜单）', () => {
    storeMock.backends = []
    storeMock.selectedAgentKind = ''
    render(<AgentBackendPicker />)

    fireEvent.click(screen.getByRole('button', { name: '选择 agent 后端' }))

    expect(screen.getByText(/后端清单暂不可用，将使用默认后端/)).toBeTruthy()
  })

  it('能力位 approval=true 不挂「无审批」，false 才挂（openai-agents 默认 true）', () => {
    storeMock.backends = [
      option('pi', 'Pi'),
      option('openai-agents', 'OpenAI Agents'),
      option('dsh', 'DeepSeek Harness', true, '', false),
    ]
    render(<AgentBackendPicker />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    expect(screen.getByRole('option', { name: /Pi/ }).querySelector('[data-no-approval-badge]')).toBeNull()
    expect(
      screen.getByRole('option', { name: /OpenAI Agents/ }).querySelector('[data-no-approval-badge]'),
    ).toBeNull()
    expect(
      screen.getByRole('option', { name: /DeepSeek Harness/ }).querySelector('[data-no-approval-badge]'),
    ).toBeTruthy()
  })
})
