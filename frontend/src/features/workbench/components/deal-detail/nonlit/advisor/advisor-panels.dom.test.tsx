// @vitest-environment jsdom
/**
 * 常年顾问工作台各卡的交互（录屏时要点得到的那些点）：
 * 类型 tabs 能筛事项、每条事项能展开看明细并做三个动作、风险能按类别筛并闭环、
 * 回访能展开原话、续签能跑完检测流程（含中途确认）。
 *
 * 复用既有 testing-library + vi.mock 范式（见 ProjectDetailPage.dom.test.tsx），
 * 不新增依赖：状态断言用 DOM 文本与元素数量。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const toastMock = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))

import { DEMO_NL3_RISKS, DEMO_NL3_SERVICE_ITEMS } from '../../demo-nonlit'
import { AdvisorFeedbackCard } from './advisor-feedback-card'
import { AdvisorQuotaCard } from './advisor-quota-card'
import { AdvisorRenewCard } from './advisor-renew-card'
import { AdvisorRiskCard } from './advisor-risk-card'
import { AdvisorServiceList } from './advisor-service-list'

describe('AdvisorQuotaCard', () => {
  it('画出服务期进度、12 个月柱与配额预警', () => {
    const { container } = render(<AdvisorQuotaCard />)
    expect(screen.getByText('服务配额')).toBeTruthy()
    expect(screen.getByText(/已用 96 天 \/ 共 365 天/)).toBeTruthy()
    // 12 个月柱：每根柱一个 title（含月份与工时）
    expect(container.querySelectorAll('[title*="h（超配额）"], [title*="h"]').length).toBeGreaterThanOrEqual(12)
    expect(screen.getByText(/配额预警：已用 93%/)).toBeTruthy()
  })
})

describe('AdvisorServiceList', () => {
  const renderList = () =>
    render(
      <AdvisorServiceList
        items={DEMO_NL3_SERVICE_ITEMS}
        onDeliver={() => toastMock.success('补传')}
        onOpinion={() => toastMock.success('转意见书')}
      />,
    )

  it('默认展示全部 16 条，tabs 带条数与工时小计', () => {
    renderList()
    expect(screen.getByText(`全部 ${DEMO_NL3_SERVICE_ITEMS.length}`)).toBeTruthy()
    expect(screen.getByText(/16 项 · 小计/)).toBeTruthy()
    expect(screen.getAllByText('合同审查 4').length).toBeGreaterThan(0)
  })

  it('点类型 tab 只留该类事项', () => {
    renderList()
    fireEvent.click(screen.getByText('合同审查 4').closest('button')!)
    expect(screen.getByText(/4 项 · 小计/)).toBeTruthy()
    expect(screen.queryByText('解答劳动合同到期不续签的经济补偿口径')).toBeNull()
    expect(screen.getByText('审阅《设备采购框架协议》并出具修改建议')).toBeTruthy()
  })

  it('展开一条看到「做了什么 / 交付物 / 耗时明细」与三个动作', () => {
    renderList()
    fireEvent.click(screen.getByText('审阅《设备采购框架协议》并出具修改建议').closest('button')!)
    expect(screen.getByText('具体做了什么')).toBeTruthy()
    expect(screen.getByText(/设备采购框架协议（修订稿）/)).toBeTruthy()
    expect(screen.getByText('耗时明细（合计 2.5h）')).toBeTruthy()
    expect(screen.getByText('标记完成')).toBeTruthy()
    expect(screen.getByText('补传交付物')).toBeTruthy()
    expect(screen.getByText('转成正式意见书')).toBeTruthy()
  })

  it('三个动作都能点，且改的是本地演示态', () => {
    renderList()
    const before = screen.queryAllByText('已出意见书').length
    fireEvent.click(screen.getByText('审阅《设备采购框架协议》并出具修改建议').closest('button')!)
    fireEvent.click(screen.getByText('转成正式意见书'))
    expect(toastMock.success).toHaveBeenCalled()
    // 这条原本没有意见书标记，点完多出一个「已出意见书」徽标
    expect(screen.queryAllByText('已出意见书').length).toBe(before + 1)

    // 未交付的那条：补传后它自己的徽标从「待补交付物」变成「已交付」
    const pending = screen.queryAllByText('待补交付物').length
    expect(pending).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('审阅《委托加工合同》并出具风险提示').closest('button')!)
    fireEvent.click(screen.getByText('补传交付物'))
    expect(screen.queryAllByText('待补交付物').length).toBe(pending - 1)
  })
})

describe('AdvisorRiskCard', () => {
  it('按类别筛选风险，未闭环的条数跟着变', () => {
    render(<AdvisorRiskCard />)
    expect(screen.getByText(`未闭环 ${DEMO_NL3_RISKS.length} 项 · 高等级 2 项`)).toBeTruthy()
    fireEvent.click(screen.getByText('合同到期 2').closest('button')!)
    expect(screen.getByText(/安全生产责任险保单/)).toBeTruthy()
    expect(screen.queryByText(/危废转移台账/)).toBeNull()
  })

  it('展开一条能看到影响与建议动作，并可标记已闭环', () => {
    render(<AdvisorRiskCard />)
    fireEvent.click(screen.getByText(/安全生产责任险保单/).closest('button')!)
    expect(screen.getByText(/保单断保期间发生事故/)).toBeTruthy()
    fireEvent.click(screen.getByText('标记已闭环'))
    expect(screen.getByText(/高等级 1 项/)).toBeTruthy()
    expect(screen.getAllByText('已闭环').length).toBe(1)
  })
})

describe('AdvisorFeedbackCard', () => {
  it('列出 5 次回访与平均分，点开看原话', () => {
    render(<AdvisorFeedbackCard />)
    expect(screen.getByText(/5 次 · 平均 4.2 分/)).toBeTruthy()
    expect(screen.getByText(/设备采购协议的修改建议很具体/)).toBeTruthy()
    // 默认展开的是第一条，点第二条换成它的原话
    fireEvent.click(screen.getAllByText('人事总监 李某某')[0]!.closest('button')!)
    expect(screen.getByText(/希望多给两页纸面材料/)).toBeTruthy()
  })
})

describe('AdvisorRenewCard', () => {
  it('给出信号、结论与可执行动作', () => {
    render(<AdvisorRenewCard />)
    expect(screen.getByText('续签提醒')).toBeTruthy()
    expect(screen.getByText('调价续签')).toBeTruthy()
    expect(screen.getByText('合同剩余天数')).toBeTruthy()
    expect(screen.getByText('269 天')).toBeTruthy()
    expect(screen.getByText(/建议上调配额后按/)).toBeTruthy()
  })

  it('点「检测并生成」跑到中途等人确认，确认后完成并给出续签函', async () => {
    render(<AdvisorRenewCard />)
    fireEvent.click(screen.getByText('检测并生成'))
    await waitFor(() => expect(screen.getByText('确认并继续')).toBeTruthy(), { timeout: 15000 })
    expect(screen.getByText('需要你确认')).toBeTruthy()
    fireEvent.click(screen.getByText('确认并继续'))
    await waitFor(() => expect(screen.getByText('已完成')).toBeTruthy(), { timeout: 15000 })
    expect(screen.getAllByText(/续签函草稿/).length).toBeGreaterThan(0)
  }, 40000)
})
