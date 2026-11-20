// @vitest-environment jsdom
/**
 * ErrorNotice 测试（jsdom，真 store）。
 *
 * 不变量：
 * - 无错误不渲染占位；关闭后不再占屏
 * - code 决定动作按钮；**没有对应动作时按钮根本不存在**（不是禁用空壳）
 * - `detail.retry_after` 变成倒计时按钮，到点才可点；点了也不重发（只放行提示）
 * - 旧后端（无 code）仍按文案分类
 * - a11y：error → role="alert"，warn/info → role="status"
 * - 「诊断」把时间/错误码/后端详情/原文复制走
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clipboardMock = vi.hoisted(() => ({
  copyText: vi.fn<(text: string) => Promise<boolean>>(async () => true),
}))
vi.mock('@/lib/clipboard', () => clipboardMock)

import type { AgentBackendOption } from '../backend-types'
import { encodeError } from '../domain'
import { useCopilot } from '../store'
import { ErrorNotice } from './ErrorNotice'

function backend(kind: string, label: string, available = true): AgentBackendOption {
  return {
    kind,
    label,
    description: '',
    available,
    reason: available ? '' : '未配置可用的 LLM 平台',
    capabilities: {},
  }
}

const original = {
  compactContext: useCopilot.getState().compactContext,
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.setState({
    lastError: null,
    backends: [],
    selectedAgentKind: '',
    compactContext: original.compactContext,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ErrorNotice：渲染与分级', () => {
  it('没有错误时不渲染', () => {
    const { container } = render(<ErrorNotice />)
    expect(container.firstChild).toBeNull()
  })

  it('旧后端（无 code）按文案分类，仍是 error 级 alert', () => {
    useCopilot.setState({ lastError: '连接中断，请重试' })
    render(<ErrorNotice />)
    const notice = screen.getByTestId('error-notice')
    expect(notice.getAttribute('data-code')).toBe('backend_unavailable')
    expect(notice.getAttribute('role')).toBe('alert')
    expect(screen.getByText('连接中断，请重试')).toBeTruthy()
    expect(screen.getByText('可原样重发')).toBeTruthy()
  })

  it('warn 用 role="status"（不打断读屏），info 也是 status；无对应动作就没有按钮', () => {
    useCopilot.setState({ lastError: '当前使用人数较多，请稍后再试' })
    const { unmount } = render(<ErrorNotice />)
    expect(screen.getByTestId('error-notice').getAttribute('role')).toBe('status')
    unmount()

    useCopilot.setState({ lastError: '会话还没有对话历史，无需压缩' })
    render(<ErrorNotice />)
    expect(screen.getByTestId('error-notice').getAttribute('role')).toBe('status')
    // info 级「无需压缩」不该有任何动作按钮（点了只会再触发一次同样的提示）
    expect(screen.queryByRole('button', { name: /重试|换个后端|压缩上下文/ })).toBeNull()
  })

  it('多答前缀：正文与来源分开显示', () => {
    useCopilot.setState({ lastError: 'dsh：连接中断，请重试' })
    render(<ErrorNotice />)
    expect(screen.getByText('连接中断，请重试')).toBeTruthy()
    expect(screen.getByText('dsh')).toBeTruthy()
  })

  it('「关闭」把 lastError 清空，提示不再渲染', () => {
    useCopilot.setState({ lastError: '连接中断，请重试' })
    const { container } = render(<ErrorNotice />)
    fireEvent.click(screen.getByRole('button', { name: '关闭这条提示' }))
    expect(useCopilot.getState().lastError).toBeNull()
    expect(container.firstChild).toBeNull()
  })
})

describe('ErrorNotice：限流倒计时', () => {
  it('有 retry_after 时出现倒计时重试按钮，到点才可点', () => {
    vi.useFakeTimers()
    useCopilot.setState({
      lastError: encodeError({
        code: 'rate_limited',
        message: '当前使用人数较多',
        scope: 'agent',
        detail: { retry_after: 3, backend: 'pi' },
      }),
    })
    render(<ErrorNotice />)

    const counting = screen.getByRole('button', { name: /等 3 秒后重试/ }) as HTMLButtonElement
    expect(counting.disabled).toBe(true)

    // 逐秒推进：每一拍只有上一拍的状态提交后才会排下一个 timeout
    for (let i = 0; i < 3; i++) act(() => void vi.advanceTimersByTime(1000))

    const ready = screen.getByRole('button', { name: /^重试$/ }) as HTMLButtonElement
    expect(ready.disabled).toBe(false)
    // 点「重试」只放行提示，绝不代为重发（send() 会二次注入业务锚点）
    fireEvent.click(ready)
    expect(useCopilot.getState().lastError).toBeNull()
  })

  it('没有 retry_after 就只给「稍后重试」，不编秒数', () => {
    useCopilot.setState({ lastError: '当前使用人数较多，请稍后再试' })
    render(<ErrorNotice />)
    const btn = screen.getByRole('button', { name: /稍后重试/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
  })
})

describe('ErrorNotice：code → 动作', () => {
  it('capability_unsupported：有别的可用后端才给「换个后端」，点了切到那个后端', () => {
    useCopilot.setState({
      backends: [backend('pi', 'Pi'), backend('dsh', 'DeepSeek Harness')],
      selectedAgentKind: 'pi',
      lastError: encodeError({ code: 'capability_unsupported', message: '不支持插话', scope: 'pi' }),
    })
    render(<ErrorNotice />)
    fireEvent.click(screen.getByRole('button', { name: /换个后端/ }))
    expect(useCopilot.getState().selectedAgentKind).toBe('dsh')
    expect(useCopilot.getState().lastError).toBeNull()
  })

  it('capability_unsupported：没有别的可用后端时按钮不存在（不留禁用空壳）', () => {
    useCopilot.setState({
      backends: [backend('pi', 'Pi'), backend('dsh', 'DeepSeek Harness', false)],
      selectedAgentKind: 'pi',
      lastError: encodeError({ code: 'capability_unsupported', message: '不支持插话' }),
    })
    render(<ErrorNotice />)
    expect(screen.queryByRole('button', { name: /换个后端/ })).toBeNull()
    // 提示本身还在（不能连诊断/关闭一起没了）
    expect(screen.getByTestId('error-notice')).toBeTruthy()
  })

  it('context_exceeded：给「压缩上下文」并调 store 的 compactContext', () => {
    const compactContext = vi.fn(async () => {})
    useCopilot.setState({
      compactContext,
      lastError: encodeError({ code: 'context_exceeded', message: '上下文超出窗口', detail: { used: 99000 } }),
    })
    render(<ErrorNotice />)
    fireEvent.click(screen.getByRole('button', { name: /压缩上下文/ }))
    expect(compactContext).toHaveBeenCalledTimes(1)
  })

  it('其余 code 一律不给动作按钮', () => {
    for (const code of ['quota_exhausted', 'backend_unavailable', 'upstream_timeout', 'tool_args_invalid']) {
      useCopilot.setState({ lastError: encodeError({ code, message: '出错了' }) })
      const { unmount } = render(<ErrorNotice />)
      expect(screen.queryByRole('button', { name: /重试|换个后端|压缩上下文/ })).toBeNull()
      unmount()
    }
  })
})

describe('ErrorNotice：诊断与合并计数', () => {
  it('「诊断」复制时间/错误码/后端详情/原文', async () => {
    useCopilot.setState({
      lastError: encodeError({
        code: 'rate_limited',
        message: '当前使用人数较多',
        scope: 'agent',
        detail: { retry_after: 12, backend: 'pi', model: 'gpt-5' },
      }),
    })
    render(<ErrorNotice />)
    fireEvent.click(screen.getByTitle(/复制时间/))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    const text = clipboardMock.copyText.mock.calls[0]![0]
    expect(text).toContain('错误码：rate_limited')
    expect(text).toContain('范围：agent')
    expect(text).toContain('详情：backend=pi | model=gpt-5 | retry_after=12')
    expect(text).toContain('原文：当前使用人数较多')
    await waitFor(() => expect(screen.getByText('已复制')).toBeTruthy())
  })

  it('同 code 连续两次失败：显示「同类错误 ×2」', () => {
    useCopilot.setState({ lastError: encodeError({ code: 'rate_limited', message: '当前使用人数较多' }) })
    render(<ErrorNotice />)
    expect(screen.queryByText(/同类错误/)).toBeNull()

    act(() => {
      useCopilot.setState({ lastError: encodeError({ code: 'rate_limited', message: '又在排队了' }) })
    })
    expect(screen.getByText('同类错误 ×2')).toBeTruthy()
    // 文案取最新的一条
    expect(screen.getByText('又在排队了')).toBeTruthy()
  })
})
