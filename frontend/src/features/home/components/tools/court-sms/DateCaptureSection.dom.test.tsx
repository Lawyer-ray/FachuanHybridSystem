// @vitest-environment jsdom
/**
 * DateCaptureSection 的渲染测试（jsdom）。
 *
 * 关注点（都是真实会误导律师的分支）：
 * - 识别中 → 显示"识别中"，不给「确认日期」按钮
 * - 有待确认日期 → 出「确认日期」入口（点击回调带上正确的 taskId）
 * - 识别为空 → 明确说"没识别到"，不是错误态，也不出确认按钮
 * - 识别失败 → 出「重新识别」并展示失败原因
 * - 什么都没送成（无文书/未绑定案件） → 只显示一句原因
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DateCaptureSection } from './DateCaptureSection'
import type { CaptureTask, UseDateCaptureResult } from './use-date-capture'

function task(over: Partial<CaptureTask> = {}): CaptureTask {
  return {
    task_id: 11,
    document_path: '/tmp/传票.pdf',
    document_name: '传票.pdf',
    status: 'success',
    error_message: '',
    classification_hint: '',
    document_type: 'other',
    case_number: '',
    candidate_count: 0,
    pending_count: 0,
    confirmed_count: 0,
    skipped_count: 0,
    date_confirmation_status: 'none',
    ...over,
  }
}

function capture(over: Partial<UseDateCaptureResult> = {}): UseDateCaptureResult {
  return {
    started: true,
    reason: null,
    tasks: [],
    running: false,
    pendingCount: 0,
    confirmedCount: 0,
    start: vi.fn(async () => {}),
    restart: vi.fn(async () => {}),
    refresh: vi.fn(async () => {}),
    stop: vi.fn(),
    reset: vi.fn(),
    ...over,
  }
}

const noop = () => {}

describe('DateCaptureSection', () => {
  it('未发起过时什么都不渲染', () => {
    const { container } = render(
      <DateCaptureSection capture={capture({ started: false })} onOpenTask={noop} onRetry={noop} />,
    )
    expect(container.childElementCount).toBe(0)
  })

  it('没有文书时只给一句原因，不出任何按钮', () => {
    render(
      <DateCaptureSection
        capture={capture({ tasks: [], reason: '该短信没有可识别的文书（通知类短信，或文书尚未下载成功）' })}
        onOpenTask={noop}
        onRetry={noop}
      />,
    )
    expect(screen.getByText(/没有可识别的文书/)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('识别中：显示文书行 + 识别中，不给确认入口', () => {
    render(
      <DateCaptureSection
        capture={capture({ tasks: [task({ status: 'processing' })], running: true })}
        onOpenTask={noop}
        onRetry={noop}
      />,
    )
    expect(screen.getByText('传票.pdf')).toBeTruthy()
    expect(screen.getByText('识别中')).toBeTruthy()
    expect(screen.queryByText('确认日期')).toBeNull()
  })

  it('有待确认日期：出「确认日期」并回传正确 taskId', () => {
    const onOpenTask = vi.fn()
    render(
      <DateCaptureSection
        capture={capture({ tasks: [task({ task_id: 42, pending_count: 3 })], pendingCount: 3 })}
        onOpenTask={onOpenTask}
        onRetry={noop}
      />,
    )
    const btn = screen.getByRole('button', { name: /确认日期/ })
    fireEvent.click(btn)
    expect(onOpenTask).toHaveBeenCalledWith(42)
  })

  it('识别为空：说明没日期，不当作错误、不给确认入口', () => {
    render(
      <DateCaptureSection
        capture={capture({ tasks: [task({ candidate_count: 0, pending_count: 0 })] })}
        onOpenTask={noop}
        onRetry={noop}
      />,
    )
    expect(screen.getByText('未识别到关键日期')).toBeTruthy()
    expect(screen.getByText(/没识别到关键日期/)).toBeTruthy()
    expect(screen.queryByText('确认日期')).toBeNull()
    // 空结果允许「再识别一次」
    expect(screen.getByRole('button', { name: /再识别一次/ })).toBeTruthy()
  })

  it('识别失败：展示原因并给「重新识别」', () => {
    const onRetry = vi.fn()
    render(
      <DateCaptureSection
        capture={capture({ tasks: [task({ status: 'failed', error_message: '无法从文书中提取文字' })] })}
        onOpenTask={noop}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText(/无法从文书中提取文字/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /重新识别失败的文书/ }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
