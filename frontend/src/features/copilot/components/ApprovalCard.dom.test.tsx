// @vitest-environment jsdom
/**
 * ApprovalCard 测试（jsdom）。
 *
 * 高危工具调用审批卡：300 秒不决定由服务端按拒绝处理（fail-closed），
 * 卡上带倒计时。关键不变量：
 * - 倒计时按 receivedAt 计算剩余秒数，到 0 后显示「已超时（按拒绝处理）」
 * - 已决态显示「已同意 / 已拒绝」且隐藏按钮（不能再改）
 * - 未决且未超时才显示同意/拒绝按钮，并各自下发对应布尔
 * - 参数预览为空时不渲染预览行
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({ decide: vi.fn() }))
vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))

import { ApprovalCard } from './ApprovalCard'
import type { PendingApproval } from '../types'

function approval(over: Partial<PendingApproval> = {}): PendingApproval {
  return {
    approvalId: 'a1',
    toolName: 'delete_file',
    toolArgs: { path: '/tmp/x.pdf' },
    message: '将删除 3 个文件',
    receivedAt: Date.now(),
    decided: null,
    ...over,
  } as PendingApproval
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ApprovalCard：倒计时', () => {
  it('初始显示剩余时间（5:00 附近）', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    // 刚收到 → 约 5:00
    expect(container.textContent).toMatch(/4:5\d|5:00/)
    container.remove()
  })

  it('过 60 秒后倒计时减少', () => {
    const receivedAt = Date.now()
    const { container } = render(<ApprovalCard approval={approval({ receivedAt })} />)

    act(() => {
      vi.advanceTimersByTime(60_000)
      // interval 每秒触发一次；推进后剩余约 4:00
    })
    expect(container.textContent).toMatch(/3:5\d|4:00/)
    container.remove()
  })

  it('超过 300 秒显示已超时（按拒绝处理）', () => {
    const receivedAt = Date.now()
    const { container } = render(<ApprovalCard approval={approval({ receivedAt })} />)

    act(() => {
      vi.advanceTimersByTime(301_000)
    })
    expect(container.textContent).toContain('已超时（按拒绝处理）')
    container.remove()
  })
})

describe('ApprovalCard：已决态', () => {
  it('已同意：显示「已同意」且无按钮', () => {
    const { container } = render(<ApprovalCard approval={approval({ decided: 'approved' })} />)
    expect(container.textContent).toContain('已同意')
    expect(screen.queryByRole('button', { name: '同意' })).toBeNull()
    expect(screen.queryByRole('button', { name: '拒绝' })).toBeNull()
    container.remove()
  })

  it('已拒绝：显示「已拒绝」且无按钮', () => {
    const { container } = render(<ApprovalCard approval={approval({ decided: 'rejected' })} />)
    expect(container.textContent).toContain('已拒绝')
    expect(screen.queryByRole('button', { name: '同意' })).toBeNull()
    container.remove()
  })

  it('已决态不再启动倒计时（剩余时间文案被已决态覆盖）', () => {
    const { container } = render(<ApprovalCard approval={approval({ decided: 'approved' })} />)
    act(() => {
      vi.advanceTimersByTime(400_000)
    })
    expect(container.textContent).not.toContain('已超时')
    expect(container.textContent).toContain('已同意')
    container.remove()
  })
})

describe('ApprovalCard：决定', () => {
  it('点同意下发 approved=true', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    fireEvent.click(screen.getByRole('button', { name: '同意' }))
    expect(storeMock.decide).toHaveBeenCalledWith('a1', true)
    container.remove()
  })

  it('点拒绝：第一步展开理由输入，第二步确认提交（P1-5 附理由）', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    // 第一步：展开理由输入（不提交决定）
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    expect(storeMock.decide).not.toHaveBeenCalled()
    expect(screen.getByPlaceholderText(/拒绝理由/)).toBeTruthy()
    // 第二步：确认拒绝
    fireEvent.click(screen.getByRole('button', { name: '确认拒绝' }))
    expect(storeMock.decide).toHaveBeenCalledWith('a1', false, '')
    container.remove()
  })

  it('填拒绝理由后随确认一起提交', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    fireEvent.change(screen.getByPlaceholderText(/拒绝理由/), { target: { value: '金额不对' } })
    fireEvent.click(screen.getByRole('button', { name: '确认拒绝' }))
    expect(storeMock.decide).toHaveBeenCalledWith('a1', false, '金额不对')
    container.remove()
  })

  it('超时后不再显示决定按钮（只能等 fail-closed）', () => {
    const receivedAt = Date.now()
    const { container } = render(<ApprovalCard approval={approval({ receivedAt })} />)

    act(() => {
      vi.advanceTimersByTime(301_000)
    })
    expect(screen.queryByRole('button', { name: '同意' })).toBeNull()
    expect(screen.queryByRole('button', { name: '拒绝' })).toBeNull()
    container.remove()
  })
})

describe('ApprovalCard：内容展示', () => {
  it('显示工具简称与消息正文', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    expect(container.textContent).toContain('需要确认')
    expect(container.textContent).toContain('将删除 3 个文件')
    container.remove()
  })

  it('有参数时渲染参数预览', () => {
    const { container } = render(<ApprovalCard approval={approval()} />)
    expect(container.textContent).toContain('/tmp/x.pdf')
    container.remove()
  })

  it('参数为空时不渲染预览行', () => {
    const { container } = render(<ApprovalCard approval={approval({ toolArgs: {} })} />)
    expect(container.textContent).not.toContain('/tmp/x.pdf')
    container.remove()
  })
})

describe('ApprovalCard：风险分级（P0-3）', () => {
  it('紧急级：首次点击只解锁，再次点击才真正同意', () => {
    const { container } = render(
      <ApprovalCard approval={approval({ riskLevel: 'critical', needsSecondConfirmation: true })} />,
    )
    expect(container.textContent).toContain('紧急')

    const btn = screen.getByRole('button', { name: '同意' })
    fireEvent.click(btn)
    // 首击不提交，只变成「再次确认执行」
    expect(storeMock.decide).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '再次确认执行' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '再次确认执行' }))
    expect(storeMock.decide).toHaveBeenCalledWith('a1', true)
    container.remove()
  })

  it('紧急级二次确认解锁后 8 秒不动作自动收回', () => {
    const { container } = render(
      <ApprovalCard approval={approval({ riskLevel: 'critical' })} />,
    )
    fireEvent.click(screen.getByRole('button', { name: '同意' }))
    expect(screen.getByRole('button', { name: '再次确认执行' })).toBeTruthy()

    act(() => {
      vi.advanceTimersByTime(8100)
    })
    // 收回后回到「同意」初始态，且未提交
    expect(screen.getByRole('button', { name: '同意' })).toBeTruthy()
    expect(storeMock.decide).not.toHaveBeenCalled()
    container.remove()
  })

  it('紧急级倒计时按 900 秒口径（15:00 附近）', () => {
    const { container } = render(<ApprovalCard approval={approval({ riskLevel: 'critical' })} />)
    expect(container.textContent).toMatch(/14:5\d|15:00/)
    container.remove()
  })

  it('离线待审：显示「后台任务」标记与等待确认文案，倒计时按 7200 秒口径', () => {
    const { container } = render(
      <ApprovalCard approval={approval({ offline: true, riskLevel: 'high', message: '', receivedAt: Date.now() - 60_000 })} />,
    )
    expect(container.textContent).toContain('后台任务')
    expect(container.textContent).toContain('等待你确认')
    // 7200s - 60s ≈ 119:00（格式 m:ss，分钟数不补零）
    expect(container.textContent).toMatch(/118:5\d|119:00/)
    container.remove()
  })
})
