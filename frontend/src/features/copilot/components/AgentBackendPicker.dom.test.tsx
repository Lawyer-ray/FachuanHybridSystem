// @vitest-environment jsdom
/**
 * AgentBackendPicker（jsdom）：切换语义与不可用置灰。
 *
 * 这个控件唯一的复杂度就是「什么时候能改」，所以断言全落在它上面：
 *  · 没有当前会话 → 下拉可点，选项中显示中文名，选中回调 kind；
 *  · 已有会话 → 标签只读，点开的是一句解释（不是选项列表），绝不调 select；
 *  · `available=false` → 选项 disabled 且副标题是**原因**（不是 description）；
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
    render(<AgentBackendPicker currentKind={null} />)

    const trigger = screen.getByRole('button', { name: /后端：Pi/ })
    fireEvent.click(trigger)

    expect(screen.getByRole('listbox', { name: '可选 agent 后端' })).toBeTruthy()
    expect(screen.getByRole('option', { name: /Pi/ })).toBeTruthy()
    expect(screen.getByRole('option', { name: /DeepSeek Harness/ })).toBeTruthy()
  })

  it('选中后端时回调 kind 并收起列表', () => {
    render(<AgentBackendPicker currentKind={null} />)
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
    render(<AgentBackendPicker currentKind={null} />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    const dsh = screen.getByRole('option', { name: /DeepSeek Harness/ }) as HTMLButtonElement
    expect(dsh.disabled).toBe(true)
    expect(dsh.textContent).toContain('未安装 DeepSeek Harness SDK')
    expect(dsh.textContent).not.toContain('DeepSeek Harness 的说明')
  })

  it('点不可用项不会触发选择（防止灰项被程序路径选中）', () => {
    storeMock.backends = [option('pi', 'Pi'), option('dsh', 'DeepSeek Harness', false, '未配置可用的 LLM 平台')]
    render(<AgentBackendPicker currentKind={null} />)
    fireEvent.click(screen.getByRole('button', { name: /后端：Pi/ }))

    fireEvent.click(screen.getByRole('option', { name: /DeepSeek Harness/ }))

    expect(storeMock.selectAgentKind).not.toHaveBeenCalled()
  })

  it('清单为空时说明会用默认后端（不显示空白菜单）', () => {
    storeMock.backends = []
    storeMock.selectedAgentKind = ''
    render(<AgentBackendPicker currentKind={null} />)

    fireEvent.click(screen.getByRole('button', { name: '选择 agent 后端' }))

    expect(screen.getByText(/后端清单暂不可用，将使用默认后端/)).toBeTruthy()
  })

  it('能力位 approval=true 不挂「无审批」，false 才挂（openai-agents 默认 true）', () => {
    storeMock.backends = [
      option('pi', 'Pi'),
      option('openai-agents', 'OpenAI Agents'),
      option('dsh', 'DeepSeek Harness', true, '', false),
    ]
    render(<AgentBackendPicker currentKind={null} />)
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

describe('AgentBackendPicker：已有会话只读', () => {
  it('显示会话自己的后端名（不是 selectedAgentKind），带不可更换的可访问名', () => {
    storeMock.selectedAgentKind = 'dsh' // 新会话偏好已改成 dsh
    render(<AgentBackendPicker currentKind="pi" />)

    expect(screen.getByRole('button', { name: /本会话使用 Pi，不可更换/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /点击更换/ })).toBeNull()
  })

  it('点击展开的是解释，不是选项列表；不回调选择', () => {
    render(<AgentBackendPicker currentKind="dsh" />)

    fireEvent.click(screen.getByRole('button', { name: /本会话使用 DeepSeek Harness/ }))

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(screen.getByRole('status').textContent).toContain('中途更换会丢失上下文')
    expect(storeMock.selectAgentKind).not.toHaveBeenCalled()
  })

  it('后端清单没拉到时仍显示 kind 原文（不显示空白）', () => {
    storeMock.backends = []
    render(<AgentBackendPicker currentKind="dsh" />)

    expect(screen.getByRole('button', { name: /本会话使用 dsh/ })).toBeTruthy()
  })
})
