// @vitest-environment jsdom
/**
 * PendingList（未决槽清单）单测。
 *
 * 复制必须走 `lib/clipboard` 的 copyText：内网 http 部署下 navigator.clipboard
 * 是 undefined，直接调会在点击时报错且没有任何反馈（见 use-copy-feedback 注释）。
 * 复制成功/失败要给不同提示——复制失败却提示「已复制」，律师会拿着空剪贴板去
 * 补写，然后对不上槽位。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const copyTextMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/clipboard', () => ({ copyText: copyTextMock }))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

import { toast } from 'sonner'

import { PendingList } from './PendingList'

beforeEach(() => {
  copyTextMock.mockReset()
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('PendingList', () => {
  it('逐条列出未决槽名', () => {
    render(<PendingList pending={['court_name', 'judge_name']} />)
    expect(screen.getByText('court_name')).toBeTruthy()
    expect(screen.getByText('judge_name')).toBeTruthy()
  })

  it('复制槽名走 copyText 并提示已复制', async () => {
    copyTextMock.mockResolvedValue(true)
    render(<PendingList pending={['court_name']} />)
    fireEvent.click(screen.getByRole('button', { name: '复制槽名 court_name' }))
    await vi.waitFor(() => expect(copyTextMock).toHaveBeenCalledWith('court_name'))
    await vi.waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledWith('已复制槽名：court_name'))
  })

  it('复制失败不谎报成功', async () => {
    copyTextMock.mockResolvedValue(false)
    render(<PendingList pending={['court_name']} />)
    fireEvent.click(screen.getByRole('button', { name: '复制槽名 court_name' }))
    await vi.waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled())
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled()
  })

  it('给了 onLocate 才渲染「定位」，点了把槽名回传', () => {
    const onLocate = vi.fn()
    render(<PendingList pending={['court_name']} onLocate={onLocate} />)
    fireEvent.click(screen.getByRole('button', { name: '定位 court_name' }))
    expect(onLocate).toHaveBeenCalledWith('court_name')
  })
})
