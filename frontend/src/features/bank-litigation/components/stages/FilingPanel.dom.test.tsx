// @vitest-environment jsdom
/**
 * FilingPanel：⑥ 校验 —— 签字盖章齐不齐、金额对不对，齐了才通知律师去一张网。
 *
 * 这一步是送法院前的最后一关，所以口径必须钉死：
 * - 统计条的「盖章齐 / 签字齐 / 阻塞项」按签章核对表实算（章与签是两件事，
 *   任一不齐都算阻塞）
 * - 起诉条件判定三种结果（通过 / 提示 / 不通过）各有独立文案与语气
 * - 「一键修正」必须**先看 diff 再执行**：按钮只打开预览抽屉，确认后才跑
 * - 通知是两阶段的：发出 ≠ 送达，卡片拿到阻塞条数与阻塞原因
 *
 * 抽屉 / 通知卡 / 金额卡 / 动作卡全部 stub（各自有自己的测试），
 * 本文件只测编排与统计口径。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  action: vi.fn(),
  amount: vi.fn(),
  notify: vi.fn(),
  signDrawer: vi.fn(),
  diffDrawer: vi.fn(),
  stageAction: vi.fn(),
}))

vi.mock('../demo-data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../demo-data')>()
  return { ...actual, DEMO_SIGN_CHECKS: actual.DEMO_SIGN_CHECKS }
})

vi.mock('./StageActionCard', () => ({
  StageActionCard: (props: { title: string }) => {
    stubs.action(props)
    return <div>STAGE_ACTION:{props.title}</div>
  },
}))
vi.mock('./FilingAmountCard', () => ({
  FilingAmountCard: (props: Record<string, unknown>) => {
    stubs.amount(props)
    return <div>AMOUNT_CARD</div>
  },
}))
vi.mock('./FilingNotifyCard', () => ({
  FilingNotifyCard: (props: {
    blockedCount: number
    blockedNotes: string[]
    stage: string
    onSend: () => void
  }) => {
    stubs.notify(props)
    return (
      <button type="button" onClick={() => props.onSend()}>
        NOTIFY_CARD:{props.blockedCount}/{props.stage}
      </button>
    )
  },
}))
vi.mock('./FilingFixPreviewDrawer', () => ({
  FilingFixPreviewDrawer: (props: { open: boolean; running: boolean; onConfirm: () => void; onClose: () => void }) => {
    stubs.diffDrawer(props)
    if (!props.open) return null
    return (
      <div>
        <div>DIFF_DRAWER:{String(props.running)}</div>
        <button type="button" onClick={() => props.onConfirm()}>
          DIFF_CONFIRM
        </button>
        <button type="button" onClick={() => props.onClose()}>
          DIFF_CLOSE
        </button>
      </div>
    )
  },
}))
vi.mock('./FilingSignDrawer', () => ({
  SignDrawer: (props: { name: string | null; onClose: () => void }) => {
    stubs.signDrawer(props)
    if (!props.name) return null
    return (
      <div>
        <div>SIGN_DRAWER:{props.name}</div>
        <button type="button" onClick={() => props.onClose()}>
          SIGN_CLOSE
        </button>
      </div>
    )
  },
}))
/**
 * 用可控的假状态机替掉 useStageAction：真实跑批有毫秒级延时，
 * 这里只测「面板怎么用它的状态」，所以自己控制 phase / summary。
 */
const fakeState = vi.hoisted(() => ({ phase: 'idle' as string, summary: '' }))
vi.mock('./use-stage-action', () => ({
  useStageAction: (opts: { toSummary?: () => string }) => {
    stubs.stageAction(opts)
    // 形状必须与真实 hook 一致：`return { ...state, execute, reset, confirm }`
    // —— 状态字段是**平铺**的（面板直接读 autoFix.phase），不是挂在 state 下。
    return {
      phase: fakeState.phase,
      summary: opts.toSummary?.() ?? fakeState.summary,
      percent: 0,
      progress: '',
      log: [],
      retries: 0,
      confirmText: '',
      error: null,
      execute: vi.fn(() => Promise.resolve()),
      reset: vi.fn(),
      confirm: vi.fn(),
    }
  },
}))

import {
  DEMO_FILING_CHECKS,
  DEMO_FILING_FIXES,
  DEMO_SIGN_CHECKS,
  DEMO_X3_FIX_DIFF,
} from '../demo-data'
import { FilingPanel } from './FilingPanel'

const SEAL_OK = DEMO_SIGN_CHECKS.filter((d) => d.sealOk).length
const SIGN_OK = DEMO_SIGN_CHECKS.filter((d) => d.signOk).length
const BLOCKED = DEMO_SIGN_CHECKS.filter((d) => !d.sealOk || !d.signOk)

beforeEach(() => {
  vi.clearAllMocks()
  fakeState.phase = 'idle'
})

describe('FilingPanel · 统计口径', () => {
  it('盖章齐 / 签字齐 / 阻塞项按签章核对表实算（章与签分开数）', () => {
    render(<FilingPanel />)
    expect(screen.getByText(`${DEMO_SIGN_CHECKS.length} 份`)).toBeTruthy()
    // 盖章齐与签字齐可能同值（本例都是 5/6），逐格数条数而不是按唯一文本查
    expect(screen.getAllByText(`${SEAL_OK}/${DEMO_SIGN_CHECKS.length}`).length).toBeGreaterThan(0)
    expect(screen.getAllByText(`${SIGN_OK}/${DEMO_SIGN_CHECKS.length}`).length).toBeGreaterThan(0)
    expect(screen.getByText(`${BLOCKED.length} 份`)).toBeTruthy()
  })

  it('任一不齐都算阻塞（章齐签不齐也是阻塞）', () => {
    const onlySignMissing = DEMO_SIGN_CHECKS.filter((d) => d.sealOk && !d.signOk)
    expect(onlySignMissing.length).toBeGreaterThan(0)
    expect(BLOCKED).toEqual(expect.arrayContaining(onlySignMissing))
  })

  it('签章核对表逐份列出「需盖 / 需签」，需签为破折号时不出该行', () => {
    render(<FilingPanel />)
    const noSign = DEMO_SIGN_CHECKS.filter((d) => d.needSign === '—')
    const withSign = DEMO_SIGN_CHECKS.filter((d) => d.needSign !== '—')
    expect(screen.getAllByText(/^需签：/)).toHaveLength(withSign.length)
    expect(screen.getAllByText(/^需盖：/)).toHaveLength(DEMO_SIGN_CHECKS.length)
    for (const d of noSign) expect(screen.getByText(d.docName)).toBeTruthy()
  })

  it('章 / 签两枚独立徽标逐份给出 ✓ / ✗（章不对签对要看得出是哪一样）', () => {
    render(<FilingPanel />)
    // 6 份文书各一枚「章」徽标 + 一枚「签」徽标
    const sealOk = DEMO_SIGN_CHECKS.filter((d) => d.sealOk).length
    expect(screen.getAllByText('章✓')).toHaveLength(sealOk)
    expect(screen.getAllByText('章✗')).toHaveLength(DEMO_SIGN_CHECKS.length - sealOk)
    expect(screen.getAllByText('签✓')).toHaveLength(SIGN_OK)
    expect(screen.getAllByText('签✗')).toHaveLength(DEMO_SIGN_CHECKS.length - SIGN_OK)
  })
})

describe('FilingPanel · 起诉条件判定', () => {
  it('三种结果各给独立文案（通过 / 提示 / 不通过）', () => {
    render(<FilingPanel />)
    const pass = DEMO_FILING_CHECKS.filter((c) => c.result === 'pass').length
    const warn = DEMO_FILING_CHECKS.filter((c) => c.result === 'warn').length
    const fail = DEMO_FILING_CHECKS.filter((c) => c.result === 'fail').length
    expect(pass + warn + fail).toBe(DEMO_FILING_CHECKS.length)
    expect(screen.getAllByText('通过')).toHaveLength(pass)
    expect(screen.getAllByText('提示')).toHaveLength(warn)
    expect(screen.getAllByText('不通过')).toHaveLength(fail)
  })

  it('每条判定都写出核对项与实测值', () => {
    render(<FilingPanel />)
    for (const c of DEMO_FILING_CHECKS) {
      expect(screen.getByText(c.check)).toBeTruthy()
      expect(screen.getByText(c.value)).toBeTruthy()
    }
  })
})

describe('FilingPanel · 一键修正必须先看 diff', () => {
  it('点按钮只打开 diff 预览，不直接执行', () => {
    render(<FilingPanel />)
    expect(stubs.diffDrawer.mock.calls.at(-1)![0]).toMatchObject({ open: false })
    fireEvent.click(screen.getByText('一键修正可自动项'))
    expect(stubs.diffDrawer.mock.calls.at(-1)![0]).toMatchObject({ open: true, running: false })
  })

  it('预览抽屉确认后关闭并开始跑；关掉则不跑', () => {
    render(<FilingPanel />)
    fireEvent.click(screen.getByText('一键修正可自动项'))
    fireEvent.click(screen.getByText('DIFF_CONFIRM'))
    expect(stubs.diffDrawer.mock.calls.at(-1)![0]).toMatchObject({ open: false })

    // 再开再关：同样关闭，不留下悬空抽屉
    fireEvent.click(screen.getByText('一键修正可自动项'))
    fireEvent.click(screen.getByText('DIFF_CLOSE'))
    expect(stubs.diffDrawer.mock.calls.at(-1)![0]).toMatchObject({ open: false })
  })

  it('修正跑完后按钮改文案，且「已修正」标记只打在可自动的项上', () => {
    fakeState.phase = 'done'
    render(<FilingPanel />)
    // 三次 useStageAction 调用共享同一个假状态（phase 由测试控制）
    expect(stubs.stageAction).toHaveBeenCalledTimes(3)
    const auto = DEMO_FILING_FIXES.filter((f) => f.auto).length
    const manual = DEMO_FILING_FIXES.length - auto

    const btn = screen.getByRole('button', { name: /再看 diff/ })
    expect(btn.textContent).toContain('已修正 · 再看 diff')
    expect(screen.queryByRole('button', { name: '一键修正可自动项' })).toBeNull()
    // 「已修正」蓝标只打在可自动的项上；「系统自动 / 需人工」是数据里的责任人列
    expect(screen.getAllByText('已修正')).toHaveLength(auto)
    expect(screen.getAllByText('系统自动')).toHaveLength(auto)
    expect(screen.getAllByText('需人工')).toHaveLength(manual)
  })

  it('还没修正时按钮是「一键修正可自动项」，也没有「已修正」标记', () => {
    render(<FilingPanel />)
    expect(screen.getByText('一键修正可自动项')).toBeTruthy()
    expect(screen.queryByText('已修正')).toBeNull()
  })

  it('diff 项数与自动修正项数都来自 demo（页脚与右栏口径一致）', () => {
    const { container } = render(<FilingPanel />)
    expect(container.textContent).toContain(`${DEMO_X3_FIX_DIFF.length} 项字段变更，先看 diff 才执行`)
    expect(container.textContent).toContain(
      `${DEMO_X3_FIX_DIFF.length} 项自动修正必须经律师确认 diff 后才执行`,
    )
  })
})

describe('FilingPanel · 签章抽屉与通知', () => {
  it('点某份文书打开该文书的签章抽屉，可关闭', () => {
    render(<FilingPanel />)
    const doc = DEMO_SIGN_CHECKS[0]!
    fireEvent.click(screen.getByText(doc.docName))
    expect(screen.getByText(`SIGN_DRAWER:${doc.docName}`)).toBeTruthy()

    fireEvent.click(screen.getByText('SIGN_CLOSE'))
    expect(screen.queryByText(`SIGN_DRAWER:${doc.docName}`)).toBeNull()
  })

  it('通知卡拿到阻塞条数与阻塞原因（通知里要写清补什么）', () => {
    render(<FilingPanel />)
    const props = stubs.notify.mock.calls.at(-1)![0]
    expect(props.blockedCount).toBe(BLOCKED.length)
    expect(props.blockedNotes).toEqual(BLOCKED.map((d) => d.note))
    expect(props.stage).toBe('idle')
  })

  it('发出后进入 sending（发出 ≠ 送达，两阶段）', () => {
    render(<FilingPanel />)
    fireEvent.click(screen.getByText(`NOTIFY_CARD:${BLOCKED.length}/idle`))
    expect(stubs.notify.mock.calls.at(-1)![0].stage).toBe('sending')
  })
})
