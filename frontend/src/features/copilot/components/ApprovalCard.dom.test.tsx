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
 *
 * 另锁 PIT-006（选词 Enter 不得拒批）与 `save_user_skill` 全文/已读解锁。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  // 模型记忆：切会话时装回本地选择、用服务端 llm_model 兜底（见 store/answers.ts）
  hydrateAnswerSelection: vi.fn(),
  seedAnswerModel: vi.fn(), decide: vi.fn() }))
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


/** 派发带指定 timeStamp 的事件：jsdom 的 Event.timeStamp 只读，只能盖成自有属性 */
function dispatchAt(target: HTMLElement, event: Event, timeStamp: number): void {
  Object.defineProperty(event, 'timeStamp', { value: timeStamp, configurable: true })
  act(() => {
    target.dispatchEvent(event)
  })
}

function keyDown(target: HTMLElement, key: string, timeStamp: number): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  dispatchAt(target, event, timeStamp)
  return event
}

/** 3KB 级正文（20 倍于 160 字预览）；末尾标记只在「一个字都没截断」时可见 */
const SKILL_BODY = `## 审查口径\n${'逐条比对法条与合同约定。'.repeat(260)}\n【正文结尾】`

function skillApproval(over: Partial<PendingApproval> = {}): PendingApproval {
  return approval({
    toolName: 'mcp__fachuan__save_user_skill',
    toolArgs: { name: 'contract-review', title: '合同审查', description: '逐条审合同', body: SKILL_BODY },
    message: '',
    ...over,
  })
}

function approveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: '同意' }) as HTMLButtonElement
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

describe('ApprovalCard：按栏归位（多答）', () => {
  it('卡上带 agent 时显示栏标签（与栏头同一套文案，不是原始 kind）', () => {
    const { container } = render(
      <ApprovalCard approval={approval({ agent: 'dsh', runId: 's-1:dsh:1' })} />,
    )
    const tag = container.querySelector('[data-testid="approval-agent"]')
    expect(tag?.textContent).toBe('DeepSeek Harness')
    expect(tag?.getAttribute('title')).toContain('这一栏')
    container.remove()
  })

  it('单栏 / 旧后端（agent 为空串）不渲染栏标签', () => {
    const { container } = render(<ApprovalCard approval={approval({ agent: '' })} />)
    expect(container.querySelector('[data-testid="approval-agent"]')).toBeNull()
    container.remove()
  })

  it('同名工具在两个栏同时挂起：两张卡共存，各自按 approvalId 决定', () => {
    render(
      <>
        <ApprovalCard approval={approval({ approvalId: 'a-pi', toolName: 'mcp__fachuan__delete_case', agent: 'pi' })} />
        <ApprovalCard approval={approval({ approvalId: 'a-dsh', toolName: 'mcp__fachuan__delete_case', agent: 'dsh' })} />
      </>,
    )
    expect(screen.getAllByTestId('approval-agent').map((el) => el.textContent)).toEqual([
      'Pi',
      'DeepSeek Harness',
    ])

    const approveButtons = screen.getAllByRole('button', { name: '同意' })
    expect(approveButtons).toHaveLength(2)
    fireEvent.click(approveButtons[0]!)
    fireEvent.click(approveButtons[1]!)
    expect(storeMock.decide).toHaveBeenNthCalledWith(1, 'a-pi', true)
    expect(storeMock.decide).toHaveBeenNthCalledWith(2, 'a-dsh', true)
  })
})

describe('ApprovalCard：拒绝理由框的 IME 守卫（PIT-006）', () => {
  it('compositionEnd 后 80ms 内的 Enter 不拒批，80ms 后的 Enter 才拒批', () => {
    render(<ApprovalCard approval={approval()} />)
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    const input = screen.getByPlaceholderText(/拒绝理由/)

    // 中文输入法选词：start → 打字 → end（WebKit 先派发 compositionend、再派发 keydown）
    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '金额不对' } })
    dispatchAt(input, new CompositionEvent('compositionend', { bubbles: true }), 1000)

    // 选词确认的 Enter（end 后 10ms）：不得下发决定，且默认行为被吞掉
    const trailing = keyDown(input, 'Enter', 1010)
    expect(storeMock.decide).not.toHaveBeenCalled()
    expect(trailing.defaultPrevented).toBe(true)

    // 律师事后真按的 Enter（end 后 81ms，出了尾随窗口）：正常拒批并带上理由
    keyDown(input, 'Enter', 1081)
    expect(storeMock.decide).toHaveBeenCalledWith('a1', false, '金额不对')
  })
})

describe('ApprovalCard：save_user_skill 全文展示与已读解锁', () => {
  it('渲染 3KB 正文全文（不是 160 字预览）；未勾「已阅读」时「同意」不可点', () => {
    const { container } = render(<ApprovalCard approval={skillApproval()} />)
    const body = container.querySelector('[data-testid="approval-skill-body"]')
    expect(SKILL_BODY.length).toBeGreaterThan(3000)
    // 逐字相等 = 一个字都没截断；末尾标记再断一次，失败时一眼看出截断位置
    expect(body?.textContent).toBe(SKILL_BODY)
    expect(body?.textContent).toContain('【正文结尾】')
    expect(container.textContent).toContain('合同审查')
    expect(container.textContent).toContain('/skill:contract-review')
    expect(container.textContent).toContain('保存后，此后每轮对话都会带着这段指令（个人作用域）')

    expect(approveButton().disabled).toBe(true)
    fireEvent.click(approveButton())
    expect(storeMock.decide).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText('已阅读上述指令全文'))
    expect(approveButton().disabled).toBe(false)
    fireEvent.click(approveButton())
    expect(storeMock.decide).toHaveBeenCalledWith('a1', true)
  })
})

describe('ApprovalCard：技能写工具（delete / submit）展示 key 与后果', () => {
  it('delete 说清不可恢复；submit 展示目标作用域与「审批通过前不生效」', () => {
    const del = render(
      <ApprovalCard approval={approval({ toolName: 'mcp__fachuan__delete_user_skill', toolArgs: { key: 'user:abc' } })} />,
    )
    expect(del.container.textContent).toContain('user:abc')
    expect(del.container.textContent).toContain('不可恢复')
    const sub = render(
      <ApprovalCard approval={approval({ toolName: 'mcp__fachuan__submit_skill_for_review', toolArgs: { key: 'user:abc', target_scope: 'firm' } })} />,
    )
    expect(sub.container.textContent).toContain('user:abc')
    expect(sub.container.textContent).toContain('所内（全所律师）')
    expect(sub.container.textContent).toContain('审批通过前不生效')
  })
})
