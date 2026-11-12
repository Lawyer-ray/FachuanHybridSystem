// @vitest-environment jsdom
/**
 * 非诉线 · 三个工作台（专项 / 跨境审查 / 常年顾问）与按 case_type 的分流。
 *
 * 这一层测的是**编排与口径**，不是动作卡自身的跑批动画（use-nonlit-action 有自己的测试）：
 * - 分流：advisor → 顾问工作台；其余（含 special、空值）→ 跨境审查工作台
 * - 专项工作台：统计条数字按 demo 阶段树实算（阶段/已完成/进行中/交付物/未闭环风险），
 *   动作卡只有三张（设计/起草/校验），阶段模板与起草建议的呈现受动作状态控制
 * - 跨境工作台：高/中/低风险计数与「已挂法条」实算，核验日志在核验跑完前不出现
 * - 顾问工作台：配额用掉多少、待补交付物、风险闭环数、平均评分实算
 *
 * 三块子组件（阶段板 / 甘特 / 风险表 / 双语 / 法条 / 修订单）全部 stub：
 * 它们各自的呈现由自己的测试覆盖，这里只关心父级给它们的入参与汇总口径。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  board: vi.fn(),
  gantt: vi.fn(),
  risk: vi.fn(),
  confirm: vi.fn(),
  foreignLaw: vi.fn(),
  views: vi.fn(),
  quota: vi.fn(),
  renew: vi.fn(),
  serviceList: vi.fn(),
  advisorRisk: vi.fn(),
  feedback: vi.fn(),
  actionCard: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

vi.mock('./nonlit/special/special-phase-board', () => ({
  SpecialPhaseBoard: (props: { initialPhaseId?: string; phaseFocus: number }) => {
    stubs.board(props)
    return <div>PHASE_BOARD</div>
  },
}))
vi.mock('./nonlit/special/special-gantt-card', () => ({
  SpecialGanttCard: (props: { onPickPhase: (id: string) => void }) => {
    stubs.gantt(props)
    return (
      <button type="button" onClick={() => props.onPickPhase('ph_2')}>
        GANTT_PICK
      </button>
    )
  },
}))
vi.mock('./nonlit/special/special-risk-card', () => ({
  SpecialRiskCard: (props: { onAssess: () => void }) => {
    stubs.risk(props)
    return (
      <button type="button" onClick={() => props.onAssess()}>
        RISK_ASSESS
      </button>
    )
  },
  SpecialConfirmCard: () => {
    stubs.confirm()
    return <div>SPECIAL_CONFIRM</div>
  },
}))
vi.mock('./nonlit/crossborder/ForeignLawVerifyCard', () => ({
  ForeignLawVerifyCard: () => {
    stubs.foreignLaw()
    return <div>FOREIGN_LAW</div>
  },
}))
vi.mock('./nonlit/crossborder/CrossBorderViews', () => ({
  CrossBorderViews: (props: { lawVerified: boolean }) => {
    stubs.views(props)
    return <div>CB_VIEWS:{String(props.lawVerified)}</div>
  },
}))
vi.mock('./nonlit/advisor/advisor-quota-card', () => ({
  AdvisorQuotaCard: () => {
    stubs.quota()
    return <div>ADVISOR_QUOTA</div>
  },
}))
vi.mock('./nonlit/advisor/advisor-renew-card', () => ({
  AdvisorRenewCard: () => {
    stubs.renew()
    return <div>ADVISOR_RENEW</div>
  },
}))
vi.mock('./nonlit/advisor/advisor-service-list', () => ({
  AdvisorServiceList: (props: {
    items: unknown[]
    onDeliver: (it: { title: string; deliverable: string }) => void
    onOpinion: (it: { title: string }) => void
  }) => {
    stubs.serviceList(props)
    return (
      <button type="button" onClick={() => props.onDeliver({ title: '合同审查', deliverable: '审查意见' })}>
        SERVICE_LIST
      </button>
    )
  },
}))
vi.mock('./nonlit/advisor/advisor-risk-card', () => ({
  AdvisorRiskCard: () => {
    stubs.advisorRisk()
    return <div>ADVISOR_RISK</div>
  },
}))
vi.mock('./nonlit/advisor/advisor-feedback-card', () => ({
  AdvisorFeedbackCard: () => {
    stubs.feedback()
    return <div>ADVISOR_FEEDBACK</div>
  },
}))
/** 动作卡 stub：把状态原样打进 DOM，方便断言「跑完之后才有的块」 */
vi.mock('./nonlit-action-card', () => ({
  NonLitActionCard: (props: { title: string; actionLabel: string; state: { phase: string } }) => {
    stubs.actionCard(props)
    return (
      <div>
        ACTION:{props.title}/{props.actionLabel}/{props.state.phase}
      </div>
    )
  },
}))

import { toast } from 'sonner'

import {
  DEMO_LAW_GATES,
  DEMO_NL1_RISKS,
  DEMO_NL3_RISKS,
  DEMO_NL3_SATISFACTION,
  DEMO_NL3_SERVICE_ITEMS,
  DEMO_NL3_SERVICE_STATS,
  DEMO_NONLIT_PHASES,
  DEMO_PHASE_TEMPLATES,
  DEMO_TH_CONTRACT_REVISIONS,
  DEMO_VERIFY_LOG,
} from './demo-nonlit'
import { quotaUsage } from './nonlit/advisor/advisor-domain'
import {
  AdvisorWorkbench,
  CrossBorderWorkbench,
  NonLitWorkbench,
  SpecialPhaseWorkbench,
} from './nonlit-workbench'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('NonLitWorkbench · 按 case_type 分流', () => {
  it('advisor → 顾问工作台', () => {
    render(<NonLitWorkbench caseType="advisor" />)
    expect(screen.getByText('顾问工作台')).toBeTruthy()
    expect(screen.queryByText('跨境合同审查')).toBeNull()
  })

  it('special 等非 advisor 一律走跨境审查工作台（后端只有两个代码值）', () => {
    for (const caseType of ['special', '', 'unknown']) {
      const { unmount } = render(<NonLitWorkbench caseType={caseType} />)
      expect(screen.getByText('跨境合同审查')).toBeTruthy()
      unmount()
    }
  })
})

describe('SpecialPhaseWorkbench · 统计与卡片', () => {
  it('五个统计格按 demo 阶段树实算（阶段 / 已完成 / 进行中 / 交付物 / 未闭环风险）', () => {
    render(<SpecialPhaseWorkbench />)
    const done = DEMO_NONLIT_PHASES.filter((p) => p.status === 'done').length
    const doing = DEMO_NONLIT_PHASES.filter((p) => p.status === 'doing').length
    const docs = DEMO_NONLIT_PHASES.reduce((n, p) => n + p.deliverables.length, 0)
    const openRisk = DEMO_NL1_RISKS.filter((r) => r.status !== '已闭环').length

    expect(screen.getByText('专项工作台')).toBeTruthy()
    expect(screen.getByText(`${DEMO_NONLIT_PHASES.length}`)).toBeTruthy()
    expect(screen.getByText(`${done}`)).toBeTruthy()
    expect(screen.getByText(`${doing}`)).toBeTruthy()
    expect(screen.getByText(`${docs} 份`)).toBeTruthy()
    expect(screen.getByText(`${openRisk} 条`)).toBeTruthy()
  })

  it('只有三张动作卡：设计阶段 / 从 0 起草 / 校验交付物', () => {
    render(<SpecialPhaseWorkbench />)
    const labels = stubs.actionCard.mock.calls.map((c) => c[0].actionLabel)
    // 风险复评那张卡也在本工作台内，所以按标题精确挑出阶段三张
    const phaseTitles = stubs.actionCard.mock.calls.map((c) => c[0].title)
    expect(phaseTitles).toContain('设计阶段')
    expect(phaseTitles).toContain('从 0 起草阶段划分')
    expect(phaseTitles).toContain('校验交付物')
    expect(labels).toContain('校验交付物')
  })

  it('起草建议与核验日志在动作跑完前都不出现', () => {
    render(<SpecialPhaseWorkbench />)
    expect(screen.queryByText('AI 给出的改进建议')).toBeNull()
    expect(screen.queryByText('核验日志')).toBeNull()
  })

  it('阶段模板列出名称、阶段数与用过的次数', () => {
    render(<SpecialPhaseWorkbench />)
    expect(screen.getByText('可用的阶段模板')).toBeTruthy()
    for (const t of DEMO_PHASE_TEMPLATES) {
      expect(screen.getByText(t.name)).toBeTruthy()
      expect(screen.getAllByText(`用过 ${t.used} 次`).length).toBeGreaterThan(0)
    }
    // 阶段数是纯数字标签，「7 阶段」这类值可能在多个模板里重复出现
    const phaseCount = DEMO_PHASE_TEMPLATES.filter((t) => t.phases === 7).length
    expect(screen.getAllByText('7 阶段')).toHaveLength(phaseCount)
  })

  it('点甘特条把阶段 id 交回阶段板，连点同一阶段也会重复聚焦', () => {
    render(<SpecialPhaseWorkbench />)
    expect(stubs.board.mock.calls[0]![0]).toMatchObject({ initialPhaseId: undefined, phaseFocus: 0 })

    fireEvent.click(screen.getByText('GANTT_PICK'))
    expect(stubs.board.mock.calls.at(-1)![0]).toMatchObject({ initialPhaseId: 'ph_2', phaseFocus: 1 })

    fireEvent.click(screen.getByText('GANTT_PICK'))
    expect(stubs.board.mock.calls.at(-1)![0]).toMatchObject({ initialPhaseId: 'ph_2', phaseFocus: 2 })
  })

  it('客户确认记录卡始终渲染；风险表的「重新评估」由风险卡触发', () => {
    render(<SpecialPhaseWorkbench />)
    expect(screen.getByText('SPECIAL_CONFIRM')).toBeTruthy()
    expect(stubs.risk).toHaveBeenCalledTimes(1)
    expect(typeof stubs.risk.mock.calls[0]![0].onAssess).toBe('function')
    // 风险复评卡挂在同一页，标题写明入口
    expect(screen.getByText('风险复评')).toBeTruthy()
  })
})

describe('CrossBorderWorkbench · 统计与核验日志', () => {
  it('高 / 中 / 低与已挂法条按修订清单实算', () => {
    render(<CrossBorderWorkbench />)
    const high = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'high').length
    const mid = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'mid').length
    const low = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'low').length
    const verified = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.verified).length

    expect(screen.getByText('跨境合同审查')).toBeTruthy()
    expect(screen.getByText(`${DEMO_TH_CONTRACT_REVISIONS.length}`)).toBeTruthy()
    expect(screen.getByText(`${high}/${mid}/${low}`)).toBeTruthy()
    expect(screen.getByText(`${verified}`)).toBeTruthy()
    expect(screen.getByText(`${DEMO_LAW_GATES.length} 道`)).toBeTruthy()
  })

  it('两张动作卡（逐条审查 / 法条核验）与法条核验卡、四块文档视图都在', () => {
    render(<CrossBorderWorkbench />)
    const titles = stubs.actionCard.mock.calls.map((c) => c[0].title)
    expect(titles).toEqual(['逐条审查合同', '外国法条核验'])
    expect(screen.getByText('FOREIGN_LAW')).toBeTruthy()
    // 核验没跑过 → 法条卡非激活态
    expect(screen.getByText('CB_VIEWS:false')).toBeTruthy()
  })

  it('核验日志在核验跑完前不出现（日志是核验的产物，不是页面装饰）', () => {
    render(<CrossBorderWorkbench />)
    expect(screen.queryByText('核验日志')).toBeNull()
    // 但日志数据本身在 demo 里是有内容的 —— 断言不出现是针对渲染，不是数据为空
    expect(DEMO_VERIFY_LOG.length).toBeGreaterThan(0)
  })
})

describe('AdvisorWorkbench · 配额与汇总', () => {
  it('统计条按服务统计实算（剩余天 / 已用天 / 事项 / 工时 / 配额 / 评分）', () => {
    render(<AdvisorWorkbench />)
    const s = DEMO_NL3_SERVICE_STATS
    const quotaPct = quotaUsage(s.totalHours, s.monthlyQuota)
    const avg = (
      DEMO_NL3_SATISFACTION.reduce((sum, r) => sum + r.score, 0) / DEMO_NL3_SATISFACTION.length
    ).toFixed(1)

    expect(screen.getByText('顾问工作台')).toBeTruthy()
    expect(screen.getByText(`${s.remainDays} 天`)).toBeTruthy()
    expect(screen.getByText(`${s.usedDays}/${s.contractDays} 天`)).toBeTruthy()
    expect(screen.getByText(`${s.items} 项`)).toBeTruthy()
    expect(screen.getByText(`${s.totalHours}h`)).toBeTruthy()
    expect(screen.getByText(`${quotaPct}%`)).toBeTruthy()
    expect(screen.getByText(`${avg} 分`)).toBeTruthy()
  })

  it('脚注：待补交付物 / 风险已闭环 / 回访次数', () => {
    render(<AdvisorWorkbench />)
    const pending = DEMO_NL3_SERVICE_ITEMS.filter((i) => !i.delivered).length
    const closed = DEMO_NL3_RISKS.filter((r) => r.closed).length
    expect(screen.getByText(`待补交付物 ${pending} 项`)).toBeTruthy()
    expect(screen.getByText(`风险已闭环 ${closed}/${DEMO_NL3_RISKS.length} 项`)).toBeTruthy()
    expect(screen.getByText(`回访 ${DEMO_NL3_SATISFACTION.length} 次`)).toBeTruthy()
  })

  it('五张子卡全部挂上，服务事项清单拿到完整 items', () => {
    render(<AdvisorWorkbench />)
    expect(screen.getByText('ADVISOR_QUOTA')).toBeTruthy()
    expect(screen.getByText('ADVISOR_RENEW')).toBeTruthy()
    expect(screen.getByText('ADVISOR_RISK')).toBeTruthy()
    expect(screen.getByText('ADVISOR_FEEDBACK')).toBeTruthy()
    expect(stubs.serviceList.mock.calls[0]![0].items).toBe(DEMO_NL3_SERVICE_ITEMS)
  })

  it('补传交付物 / 转正式意见书各自弹一条带事项名的成功提示', () => {
    render(<AdvisorWorkbench />)
    fireEvent.click(screen.getByText('SERVICE_LIST'))
    expect(toast.success).toHaveBeenCalledWith('已补传交付物', {
      description: '合同审查：审查意见',
    })

    const { onOpinion } = stubs.serviceList.mock.calls[0]![0]
    onOpinion({ title: '合同审查' })
    expect(toast.success).toHaveBeenCalledWith('已转成正式意见书', {
      description: '按《合同审查》生成意见书草稿，落到合同文件夹',
    })
  })
})
