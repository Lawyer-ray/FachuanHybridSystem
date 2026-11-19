// @vitest-environment jsdom
/**
 * ErrorNotice 测试（jsdom，真 store）。
 *
 * 不变量：
 * - 无错误时不渲染占位
 * - 分类正确挂到 data-code（供排查与后续埋点）
 * - 多答错误带 agent 前缀时，正文与来源分开显示
 * - 「诊断」把时间/错误码/原文复制走
 * - 「关闭」只清展示（lastError 置空）
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clipboardMock = vi.hoisted(() => ({
  copyText: vi.fn<(text: string) => Promise<boolean>>(async () => true),
}))
vi.mock('@/lib/clipboard', () => clipboardMock)

import { useCopilot } from '../store'
import { ErrorNotice } from './ErrorNotice'

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.setState({ lastError: null })
})

describe('ErrorNotice', () => {
  it('没有错误时不渲染', () => {
    const { container } = render(<ErrorNotice />)
    expect(container.firstChild).toBeNull()
  })

  it('按文案分类并给出可操作建议', () => {
    useCopilot.setState({ lastError: '连接中断，请重试' })
    render(<ErrorNotice />)
    const notice = screen.getByTestId('error-notice')
    expect(notice.getAttribute('data-code')).toBe('network')
    expect(screen.getByText('连接中断，请重试')).toBeTruthy()
    expect(screen.getByText(/再发一次/)).toBeTruthy()
    expect(screen.getByText('可原样重发')).toBeTruthy()
  })

  it('多答错误带 agent 前缀：正文与来源分开显示', () => {
    useCopilot.setState({ lastError: 'dsh：连接中断，请重试' })
    render(<ErrorNotice />)
    expect(screen.getByText('连接中断，请重试')).toBeTruthy()
    expect(screen.getByText('dsh')).toBeTruthy()
  })

  it('降级提示是 info 且不标「可原样重发」', () => {
    useCopilot.setState({ lastError: '并发席位已满，本轮只跑了主后端' })
    render(<ErrorNotice />)
    expect(screen.getByTestId('error-notice').getAttribute('data-code')).toBe('capability')
    expect(screen.queryByText('可原样重发')).toBeNull()
  })

  it('「诊断」复制时间/错误码/原文', async () => {
    useCopilot.setState({ lastError: '连接中断，请重试' })
    render(<ErrorNotice />)
    fireEvent.click(screen.getByTitle(/复制时间/))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    const text = clipboardMock.copyText.mock.calls[0]![0]
    expect(text).toContain('错误码：network')
    expect(text).toContain('原文：连接中断，请重试')
    await waitFor(() => expect(screen.getByText('已复制')).toBeTruthy())
  })

  it('「关闭」把 lastError 清空（提示不再占屏）', () => {
    useCopilot.setState({ lastError: '连接中断，请重试' })
    render(<ErrorNotice />)
    fireEvent.click(screen.getByRole('button', { name: '关闭这条提示' }))
    expect(useCopilot.getState().lastError).toBeNull()
  })
})
