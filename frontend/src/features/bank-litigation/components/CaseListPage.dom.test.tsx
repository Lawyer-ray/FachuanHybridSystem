// @vitest-environment jsdom
/**
 * 案件列表页单测（jsdom）。
 *
 * 这一页决定律师「今天先递哪几件」，所以两件不起眼但很关键的事必须钉住：
 * - **排序**：待立案（无案号 + 在办）排前面，同档内新的在上（id 倒序）。
 *   排错序会让人从一张看起来「都差不多」的表里挑错案件去立案。
 * - **筛选**：案件名与案由都能命中；清空关键字恢复全量。
 *
 * 另外覆盖三态（loading / error / empty）、阶段中文映射（含历史中文存量）、
 * 案号与标的额的空值呈现。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../hooks/use-cases', () => ({ useCases: vi.fn() }))

import { useCases } from '../hooks/use-cases'
import type { CaseRow } from '../types'
import { CaseListPage } from './CaseListPage'

const useCasesMock = vi.mocked(useCases)

function row(over: Partial<CaseRow> & { id: number; name: string }): CaseRow {
  return {
    status: '在办',
    current_stage: 'first_trial',
    cause_of_action: '金融借款合同纠纷',
    target_amount: '820000.00',
    filing_number: null,
    contract_name: null,
    ...over,
  }
}

function mockCases(data: CaseRow[] | null, over: Record<string, unknown> = {}) {
  useCasesMock.mockReturnValue({
    loading: false,
    error: null,
    data,
    reload: vi.fn(),
    ...over,
  } as never)
}

/**
 * 表体里每个案件是一个 button；按出现顺序返回案件名。
 *
 * ⚠️ 页面上还有一个「刷新」按钮也在 role=button 里，所以先剔除它
 * （它内部没有标题那种 div > div 结构）。
 */
function renderedNames(): string[] {
  return screen
    .getAllByRole('button')
    .filter((b) => b.querySelector('div > div') !== null)
    .map((b) => b.querySelector('div > div')!.textContent ?? '')
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CaseListPage · 三态', () => {
  it('loading 时显示加载态', () => {
    mockCases(null, { loading: true })
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText('正在加载案件…')).toBeTruthy()
  })

  it('error 时显示错误并能重试', () => {
    const reload = vi.fn()
    mockCases(null, { error: new Error('案件服务 502'), reload })
    render(<CaseListPage onOpen={() => {}} />)

    expect(screen.getByText('案件服务 502')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('空列表提示「先受理一笔委托」，不显示表格', () => {
    mockCases([])
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText('还没有案件，先受理一笔委托。')).toBeTruthy()
    expect(screen.queryByPlaceholderText('搜案件名 / 案由')).toBeNull()
  })
})

describe('CaseListPage · 排序', () => {
  it('待立案（无案号 + 在办）优先，同档内按 id 倒序（新的在上）', () => {
    mockCases([
      row({ id: 1, name: '已立案旧案', filing_number: '（20XX）粤0106民初0001号' }),
      row({ id: 3, name: '待立案新案' }),
      row({ id: 2, name: '待立案次新' }),
      row({ id: 9, name: '已立案新案', filing_number: '（20XX）粤0106民初0009号' }),
    ])

    render(<CaseListPage onOpen={() => {}} />)
    expect(renderedNames()).toEqual(['待立案新案', '待立案次新', '已立案新案', '已立案旧案'])
  })

  it('已结案的案件即使没有案号也不排到待立案前面（不是在办就不催）', () => {
    mockCases([
      row({ id: 10, name: '已结案无案号', status: '已结案', filing_number: null }),
      row({ id: 1, name: '在办无案号', status: '在办', filing_number: null }),
    ])
    render(<CaseListPage onOpen={() => {}} />)
    expect(renderedNames()).toEqual(['在办无案号', '已结案无案号'])
  })
})

describe('CaseListPage · 筛选', () => {
  const data = [
    row({ id: 1, name: '某某银行诉谭某某', cause_of_action: '金融借款合同纠纷' }),
    row({ id: 2, name: '某某银行诉吴某某', cause_of_action: '买卖合同纠纷' }),
  ]

  it('按案件名筛', () => {
    mockCases(data)
    render(<CaseListPage onOpen={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('搜案件名 / 案由'), { target: { value: '谭某某' } })

    expect(renderedNames()).toEqual(['某某银行诉谭某某'])
    expect(screen.getByText('共 1 件')).toBeTruthy()
  })

  it('按案由筛也能命中', () => {
    mockCases(data)
    render(<CaseListPage onOpen={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('搜案件名 / 案由'), { target: { value: '买卖' } })

    expect(renderedNames()).toEqual(['某某银行诉吴某某'])
  })

  it('清空关键字恢复全量', () => {
    mockCases(data)
    render(<CaseListPage onOpen={() => {}} />)
    const input = screen.getByPlaceholderText('搜案件名 / 案由')

    fireEvent.change(input, { target: { value: '谭某某' } })
    expect(screen.getByText('共 1 件')).toBeTruthy()

    fireEvent.change(input, { target: { value: '' } })
    expect(screen.getByText('共 2 件')).toBeTruthy()
  })

  it('纯空格不当关键字（否则会筛出空列表，看着像没有案件）', () => {
    mockCases(data)
    render(<CaseListPage onOpen={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('搜案件名 / 案由'), { target: { value: '   ' } })
    expect(screen.getByText('共 2 件')).toBeTruthy()
  })

  it('筛不到时显示空态（而不是空表壳）', () => {
    mockCases(data)
    render(<CaseListPage onOpen={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('搜案件名 / 案由'), { target: { value: '不存在的案件' } })
    expect(screen.getByText('还没有案件，先受理一笔委托。')).toBeTruthy()
  })
})

describe('CaseListPage · 行内容', () => {
  it('阶段做了中文映射（含历史存量的中文值），未知阶段原样显示', () => {
    mockCases([
      row({ id: 1, name: 'A', current_stage: 'first_trial' }),
      row({ id: 2, name: 'B', current_stage: 'rehearing_second' }),
      row({ id: 3, name: 'C', current_stage: '一审' }),
      row({ id: 4, name: 'D', current_stage: 'weird_stage' }),
      row({ id: 5, name: 'E', current_stage: null }),
    ])
    render(<CaseListPage onOpen={() => {}} />)

    // 行顺序受排序影响，所以按案件名定位行，再在行内断言阶段文案
    const rowOf = (name: string) => screen.getByRole('button', { name: new RegExp(name) })

    // first_trial → 一审；rehearing_second → 再审二审；
    // '一审'（历史中文存量）原样；未知阶段原样；空阶段 → 破折号
    expect(within(rowOf('A')).getByText('一审')).toBeTruthy()
    expect(within(rowOf('B')).getByText('再审二审')).toBeTruthy()
    expect(within(rowOf('C')).getByText('一审')).toBeTruthy()
    expect(within(rowOf('D')).getByText('weird_stage')).toBeTruthy()
    expect(within(rowOf('E')).getByText('—')).toBeTruthy()
  })

  it('案号为空显示「（无）」，标的额为空显示破折号', () => {
    mockCases([row({ id: 1, name: 'A', filing_number: null, target_amount: null })])
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText('（无）')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('标的额走千分位字符串切分（不经浮点）', () => {
    mockCases([row({ id: 1, name: 'A', target_amount: '998670.21' })])
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText('¥998,670.21')).toBeTruthy()
  })

  it('案由为空写「（未填案由）」，有合同时拼在案由后面', () => {
    mockCases([
      row({ id: 2, name: 'A', cause_of_action: null }),
      row({ id: 1, name: 'B', cause_of_action: '买卖合同纠纷', contract_name: '某某买卖合同' }),
    ])
    render(<CaseListPage onOpen={() => {}} />)

    expect(screen.getByText('（未填案由）')).toBeTruthy()
    expect(screen.getByText('买卖合同纠纷 · 某某买卖合同')).toBeTruthy()
  })

  it('点一行把 caseId 交给上层', () => {
    const onOpen = vi.fn()
    mockCases([row({ id: 406, name: '某某银行诉谭某某' })])
    render(<CaseListPage onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /某某银行诉谭某某/ }))
    expect(onOpen).toHaveBeenCalledWith(406)
  })

  it('刷新按钮触发 reload（列表是手动刷新的，没有轮询）', () => {
    const reload = vi.fn()
    mockCases([row({ id: 1, name: 'A' })], { reload })
    render(<CaseListPage onOpen={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: /刷新/ }))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('底部提醒「标的额以利息计算表为准」（两处不一致时以计算表为准）', () => {
    mockCases([row({ id: 1, name: 'A' })])
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText(/实际诉请金额以利息计算表为准/)).toBeTruthy()
  })
})
