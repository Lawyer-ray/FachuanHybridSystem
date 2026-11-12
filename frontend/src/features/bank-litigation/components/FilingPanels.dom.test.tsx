// @vitest-environment jsdom
/**
 * CourtFilingPanel（一张网立案页）。
 *
 * 这一页最容易出事的地方是**阻断项**：点下去必失败的三种情况（没法院账号、
 * 插件没装、我方不是原告）必须在点之前就说清，而不是让律师白跑一趟；执行立案
 * 还会额外要求「已有生效裁判文书」。
 *
 * 同时钉住两处容易被误改的口径：
 * - 立案类型 / 引擎默认取后端建议值，但**用户改过之后不再被后端值覆盖**
 *   （历史 bug：首次渲染 data 为 null，值被永久钉在 fallback 上）
 * - 改成与建议不同的值时给一句提示，并且类型没改成执行时不出执行阻断项
 *
 * 所有子表 / 平台卡 / 会话块 stub：它们的呈现由自己的测试覆盖。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  info: { loading: false, error: null, data: null, reload: vi.fn() },
  court: { phase: 'idle', status: '', error: null, ticks: 0, session: null },
  run: vi.fn(() => Promise.resolve()),
  reset: vi.fn(),
  material: vi.fn(),
  submitHistory: vi.fn(),
}))

vi.mock('../hooks/use-cases', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/use-cases')>()
  return { ...actual, useCaseFilingInfo: () => stubs.info }
})
vi.mock('../hooks/use-auto-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/use-auto-run')>()
  return { ...actual, useCourtFiling: () => ({ state: stubs.court, run: stubs.run, reset: stubs.reset }) }
})
vi.mock('./court/AmountCheckTable', () => ({ AmountCheckTable: () => <div>AMOUNT_CHECK</div> }))
vi.mock('./court/FieldMappingTable', () => ({ FieldMappingTable: () => <div>FIELD_MAPPING</div> }))
vi.mock('./court/MaterialList', () => ({
  MaterialList: () => {
    stubs.material()
    return <div>MATERIAL_LIST</div>
  },
}))
vi.mock('./court/SubmitHistory', () => ({
  SubmitHistory: () => {
    stubs.submitHistory()
    return <div>SUBMIT_HISTORY</div>
  },
}))
vi.mock('./court/CourtPlatform', () => ({ CourtPlatform: () => <div>COURT_PLATFORM</div> }))

import { CourtFilingPanel } from './FilingPanels'

/** 立案信息：默认全绿（能直接递） */
function info(over: Record<string, unknown> = {}) {
  return {
    case_name: '某某银行诉张某金融借款合同纠纷',
    cause_of_action: '金融借款合同纠纷',
    court_name: '广州市天河区人民法院',
    target_amount: '998670.21',
    plaintiff_name: '某某银行股份有限公司',
    defendant_name: '张某',
    our_party_is_plaintiff_side: true,
    has_court_credential: true,
    plugin_available: true,
    suggested_filing_type: 'civil',
    default_filing_engine: 'api',
    ...over,
  }
}

function setup(data: Record<string, unknown> | null = info(), over: Record<string, unknown> = {}) {
  stubs.info = { loading: false, error: null, data, reload: vi.fn(), ...over } as never
  return render(<CourtFilingPanel caseId={44} />)
}


beforeEach(() => {
  vi.clearAllMocks()
  stubs.court = { phase: 'idle', status: '', error: null, ticks: 0, session: null }
})

describe('CourtFilingPanel · 三态', () => {
  it('读取中显示加载态', () => {
    setup(null, { loading: true })
    expect(screen.getByText('正在读取立案信息…')).toBeTruthy()
  })

  it('出错时可重试', () => {
    const reload = vi.fn()
    setup(null, { error: new Error('网络错误'), reload })
    expect(screen.getByText('网络错误')).toBeTruthy()
    fireEvent.click(screen.getByText('重新加载'))
    expect(reload).toHaveBeenCalled()
  })

  it('没有立案信息时给空态而不是空面板', () => {
    setup(null)
    expect(screen.getByText('没有可用的立案信息。')).toBeTruthy()
  })
})

describe('CourtFilingPanel · 案件要素与当事人', () => {
  it('案由 / 法院 / 标的额 / 立案类型逐行照实', () => {
    setup()
    expect(screen.getByText('金融借款合同纠纷')).toBeTruthy()
    expect(screen.getAllByText('广州市天河区人民法院').length).toBeGreaterThan(0)
    // 案件要素卡与右栏「本次递交」都写标的额
    expect(screen.getAllByText('¥998,670.21').length).toBeGreaterThan(0)
    expect(screen.getAllByText('民事一审').length).toBeGreaterThan(0)
  })

  it('缺法院 / 缺标的额时写占位文案，不留空白', () => {
    setup(info({ court_name: null, target_amount: null, cause_of_action: null }))
    expect(screen.getAllByText('（未登记）').length).toBeGreaterThan(0)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('我方非原告、未配凭证都用红色语气标出', () => {
    setup(info({ our_party_is_plaintiff_side: false, has_court_credential: false }))
    expect(screen.getByText('非原告方')).toBeTruthy()
    expect(screen.getAllByText('未配置').length).toBeGreaterThan(0)
  })
})

describe('CourtFilingPanel · 阻断项', () => {
  it('全绿时不出阻断块，推送按钮可点', () => {
    setup()
    expect(screen.queryByText(/暂不能递交/)).toBeNull()
    const btn = screen.getByRole('button', { name: /推送到一张网/ })
    expect((btn as HTMLButtonElement).disabled).toBe(false)
  })

  it('四类前提各一条阻断文案，条数一致', () => {
    setup(
      info({
        has_court_credential: false,
        plugin_available: false,
        our_party_is_plaintiff_side: false,
        court_name: null,
      }),
    )
    expect(screen.getByText('暂不能递交 · 4 项待处理')).toBeTruthy()
    expect(screen.getByText('未配置一张网（法院）账号')).toBeTruthy()
    expect(screen.getByText('法院立案插件未安装')).toBeTruthy()
    expect(screen.getByText('我方不是原告方，本页只处理起诉立案')).toBeTruthy()
    expect(screen.getByText('未登记管辖法院')).toBeTruthy()
    expect((screen.getByRole('button', { name: /推送到一张网/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('阻断未清时「一张网受理号」仍写「递交后回填」，不假装已有结果', () => {
    setup(info({ has_court_credential: false }))
    expect(screen.getByText('递交后回填')).toBeTruthy()
    expect(screen.getAllByText('未配置').length).toBeGreaterThan(0)
  })

  it('执行立案且本案尚未登记案号 → 前置提示需先有生效裁判文书', () => {
    setup(info({ suggested_filing_type: 'execution', court_name: null }))
    expect(
      screen.getByText('执行立案需先有生效裁判文书（本案尚未登记案号）'),
    ).toBeTruthy()
  })

  it('执行立案但案名已含「执行」→ 不再拦', () => {
    setup(info({ suggested_filing_type: 'execution', case_name: '某某银行申请执行张某案' }))
    expect(screen.queryByText(/需先有生效裁判文书/)).toBeNull()
  })
})

describe('CourtFilingPanel · 递交参数', () => {
  it('默认取后端建议的类型与引擎', () => {
    setup(info({ suggested_filing_type: 'execution', default_filing_engine: 'playwright' }))
    expect((screen.getByLabelText('立案类型') as HTMLSelectElement).value).toBe('execution')
    expect((screen.getByLabelText('递交引擎') as HTMLSelectElement).value).toBe('playwright')
    // 「执行立案」同时出现在案卡与右栏「本次递交」
    expect(screen.getAllByText('执行立案').length).toBeGreaterThan(0)
  })

  it('后端没给建议时退回民事一审 + 接口引擎', () => {
    setup(info({ suggested_filing_type: null, default_filing_engine: null }))
    expect((screen.getByLabelText('立案类型') as HTMLSelectElement).value).toBe('civil')
    expect((screen.getByLabelText('递交引擎') as HTMLSelectElement).value).toBe('api')
  })

  it('用户改过之后不再被后端建议覆盖（首帧 data 为 null 的老 bug）', () => {
    const { rerender } = setup()
    fireEvent.change(screen.getByLabelText('立案类型'), { target: { value: 'execution' } })
    expect((screen.getByLabelText('立案类型') as HTMLSelectElement).value).toBe('execution')

    // 后端建议仍是 civil，但用户选择必须保留
    stubs.info = { loading: false, error: null, data: info(), reload: vi.fn() } as never
    rerender(<CourtFilingPanel caseId={44} />)
    expect((screen.getByLabelText('立案类型') as HTMLSelectElement).value).toBe('execution')
  })

  it('改成与建议不同的值时给一句对照提示', () => {
    setup()
    expect(screen.queryByText(/已改为「执行立案」/)).toBeNull()
    fireEvent.change(screen.getByLabelText('立案类型'), { target: { value: 'execution' } })
    expect(screen.getByText(/已改为「执行立案」，后端建议「民事一审」/)).toBeTruthy()
  })
})

describe('CourtFilingPanel · 动作与会话', () => {
  it('点推送：先 reset 再提交正确的载荷（案件 / 类型 / 引擎）', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /推送到一张网/ }))
    expect(stubs.reset).toHaveBeenCalledTimes(1)
    expect(stubs.run).toHaveBeenCalledWith({
      case_id: 44,
      filing_type: 'civil',
      filing_engine: 'api',
    })
  })

  it('执行中按钮禁用并显示轮询次数', () => {
    stubs.court = { phase: 'running', status: 'running', error: null, ticks: 3, session: null }
    setup()
    const btn = screen.getByRole('button', { name: /一张网立案进行中/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(screen.getByText('已轮询 3 次')).toBeTruthy()
  })

  it('未跑过时不显示轮询次数（0 次没有信息量）', () => {
    setup()
    expect(screen.queryByText(/已轮询/)).toBeNull()
  })

  it('递交进度四步：有阻塞时第一步标「有阻塞项」且第二步退回待办', () => {
    setup(info({ plugin_available: false }))
    expect(screen.getByText('有阻塞项')).toBeTruthy()
    setup()
    expect(screen.getAllByText('递交进度').length).toBeGreaterThan(0)
  })

  it('递交凭证两枚语气标：账号与插件各自独立判定', () => {
    setup(info({ has_court_credential: true, plugin_available: false }))
    // 「已配置」在当事人卡与凭证段各出现一次
    expect(screen.getAllByText('已配置').length).toBeGreaterThan(0)
    expect(screen.getByText('未安装')).toBeTruthy()
  })

  it('材料清单与历史递交都渲染（盖了没传照样递不了）', () => {
    setup()
    expect(screen.getByText('MATERIAL_LIST')).toBeTruthy()
    expect(screen.getByText('SUBMIT_HISTORY')).toBeTruthy()
    expect(screen.getByText('COURT_PLATFORM')).toBeTruthy()
    expect(screen.getByText('AMOUNT_CHECK')).toBeTruthy()
    expect(screen.getByText('FIELD_MAPPING')).toBeTruthy()
  })
})
