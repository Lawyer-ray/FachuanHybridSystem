// @vitest-environment jsdom
/**
 * 案件列表页单测（jsdom）。
 *
 * 这一页决定律师「今天先递哪几件」，所以三件不起眼但很关键的事必须钉住：
 * - **排序与筛选都在服务端**：一页只有 50 行，前端 filter / sort 只会作用于当前页
 *   （翻到第 2 页就冒出与关键词无关、或「已立案」排在「待立案」前面的行）。
 *   页面只把 `{page, pageSize, search, sort}` 交给 useCases，自己不再重排/重筛；
 * - **翻页**：点「下一页」要带 page=2；关键词一变页码必须回 1（否则新搜索结果
 *   从第 3 页开始看，看起来像「搜不到」）；
 * - **两种加载态**：首次是骨架（与真行同源），翻页保留旧列表（不闪白）。
 *
 * 另外覆盖三态、阶段中文映射（含历史中文存量）、案号与标的额的空值呈现，
 * 以及生成物里 id 可空（`id?: number | null`）时列表仍能渲染、点击不把空 id 交给上层。
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../hooks/use-cases', () => ({ useCases: vi.fn() }))

import { useCases } from '../hooks/use-cases'
import type { CaseRow as CaseRowData } from '../types'
import { CASE_ROW_SHELL, CaseRow } from './CaseRow'
import { CaseRowSkeleton } from './CaseRowSkeleton'
import { CaseListPage } from './CaseListPage'

const useCasesMock = vi.mocked(useCases)

function row(over: Partial<CaseRowData> & { name: string }): CaseRowData {
  return {
    id: 1,
    status: '在办',
    current_stage: 'first_trial',
    cause_of_action: '金融借款合同纠纷',
    target_amount: '820000.00',
    filing_number: null,
    ...over,
  }
}

/** useCases 的返回桩：AsyncState + reload */
function state(rows: CaseRowData[], over: Record<string, unknown>, total: number) {
  return { loading: false, error: null, data: { rows, total }, reload: vi.fn(), ...over } as never
}

/**
 * 打桩 useCases。
 *
 * `total` 与 rows 分开给：服务端分页下「本页行数」与「命中总数」不是一回事
 * （分页条按 total 算总页数，二者相等时只有一页、分页条不渲染）。
 */
function mockCases(rows: CaseRowData[], over: Record<string, unknown> = {}, total = rows.length) {
  useCasesMock.mockReturnValue(state(rows, over, total))
}

/** 页面最近一次发给 useCases 的查询（每次 render 都会调用，取最后一笔） */
function lastQuery() {
  const calls = useCasesMock.mock.calls
  const call = calls[calls.length - 1]
  if (!call) throw new Error('useCases 未被调用')
  return call[0]
}

function typeKeyword(value: string) {
  fireEvent.change(screen.getByPlaceholderText('搜案件名 / 案由'), { target: { value } })
}

/** 推过 300ms 搜索防抖窗口 */
function settleDebounce() {
  act(() => {
    vi.advanceTimersByTime(300)
  })
}

/**
 * 表体里每个案件是一个 button；按出现顺序返回案件名。
 *
 * ⚠️ 页面上的按钮不止这些（刷新 / 翻页也在 role=button 里），所以先剔除它们
 * （案件行内部有标题那种 div > div 结构）。
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

afterEach(() => {
  vi.useRealTimers()
})

describe('CaseListPage · 三态', () => {
  it('首次加载显示与真行同源的骨架（8 行），不退回转圈', () => {
    // SkeletonStatus 默认有 300ms 延迟门控，用假定时器推过去（真等待会让用例慢 300ms）
    vi.useFakeTimers()
    mockCases([], { loading: true, data: null })
    render(<CaseListPage onOpen={() => {}} />)

    settleDebounce()

    expect(screen.getByText('正在加载案件…')).toBeTruthy()
    expect(document.querySelectorAll('[data-skeleton-row="case"]')).toHaveLength(8)
  })

  it('骨架自带真实表头（同源），数据到位时不会因为表头突然出现而整体位移', () => {
    vi.useFakeTimers()
    useCasesMock.mockReturnValue({ loading: true, error: null, data: null, reload: vi.fn() } as never)
    render(<CaseListPage onOpen={() => {}} />)
    // SkeletonStatus 默认 300ms 门控：推过去才有骨架可看（快请求本就不该看见它）
    act(() => {
      vi.advanceTimersByTime(300)
    })

    // 表头由真组件 CaseListHeader 渲染（与列表同一份 CASE_ROW_COLUMNS），不是另抄一套
    for (const label of ['案件', '阶段', '状态', '案号', '标的额']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(document.querySelectorAll('[data-skeleton-row="case"]')).toHaveLength(8)
  })

  it('error 时显示错误并能重试', () => {
    const reload = vi.fn()
    mockCases([], { data: null, error: new Error('案件服务 502'), reload })
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

describe('CaseListPage · 服务端排序', () => {
  it('行序原样呈现：待立案优先由后端排好，前端不再重排', () => {
    // 后端 sort=filable_first：待立案（无案号 + 在办）在前，组内 id 倒序
    mockCases([
      row({ id: 3, name: '待立案新案' }),
      row({ id: 2, name: '待立案次新' }),
      row({ id: 9, name: '已立案新案', filing_number: '（20XX）粤0106民初0009号' }),
      row({ id: 1, name: '已立案旧案', filing_number: '（20XX）粤0106民初0001号' }),
    ])

    render(<CaseListPage onOpen={() => {}} />)
    expect(renderedNames()).toEqual(['待立案新案', '待立案次新', '已立案新案', '已立案旧案'])
  })

  it('即使回包顺序与「待立案优先」相反也不重排（排序在后端，前端重排只会打乱分页）', () => {
    mockCases([
      row({ id: 10, name: '已结案无案号', status: '已结案', filing_number: null }),
      row({ id: 1, name: '在办无案号', status: '在办', filing_number: null }),
    ])
    render(<CaseListPage onOpen={() => {}} />)
    expect(renderedNames()).toEqual(['已结案无案号', '在办无案号'])
    expect(lastQuery().sort).toBe('filable_first')
  })
})

describe('CaseListPage · 服务端搜索', () => {
  it('关键词停 300ms 才下推（逐键不请求），并带上「待立案优先」排序', () => {
    vi.useFakeTimers()
    mockCases([row({ id: 1, name: '某某银行诉谭某某' })])
    render(<CaseListPage onOpen={() => {}} />)

    typeKeyword('谭')
    // 防抖窗口内：请求参数仍是空关键词
    expect(lastQuery().search).toBe('')

    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(lastQuery().search).toBe('')

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(lastQuery()).toMatchObject({ search: '谭', page: 1, pageSize: 50, sort: 'filable_first' })
  })

  it('纯空格不当关键词（否则会搜出空列表，看着像没有案件）', () => {
    vi.useFakeTimers()
    mockCases([row({ id: 1, name: 'A' }), row({ id: 2, name: 'B' })])
    render(<CaseListPage onOpen={() => {}} />)

    typeKeyword('   ')
    settleDebounce()

    expect(lastQuery().search).toBe('')
    expect(screen.getByText('共 2 件')).toBeTruthy()
  })

  it('搜到东西时「共 N 件」用服务端总数（不是本页行数）', () => {
    mockCases([row({ id: 1, name: 'A' })], {}, 137)
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.getByText('共 137 件')).toBeTruthy()
  })

  it('有关键词的空态：文案带关键词，清除按钮把关键词与页码一起清掉', () => {
    vi.useFakeTimers()
    // 像后端一样随参数变化：有关键词就没有命中，没关键词才有数据
    useCasesMock.mockImplementation((q) =>
      state(q.search ? [] : [row({ id: 1, name: '某某银行诉谭某某' })], {}, q.search ? 0 : 1),
    )
    render(<CaseListPage onOpen={() => {}} />)

    typeKeyword('不存在的案件')
    settleDebounce()

    expect(screen.getByText('没有匹配「不存在的案件」的案件')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '清除关键词' }))
    expect(lastQuery()).toMatchObject({ search: '', page: 1 })
    expect(screen.getByText('某某银行诉谭某某')).toBeTruthy()
  })
})

describe('CaseListPage · 分页', () => {
  it('点「下一页」按第 2 页取数', () => {
    mockCases([row({ id: 1, name: 'A' })], {}, 137)
    render(<CaseListPage onOpen={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    expect(lastQuery()).toMatchObject({ page: 2, pageSize: 50 })
  })

  it('页码与总数写在分页条里，两端到头时对应按钮禁用', () => {
    mockCases([row({ id: 1, name: 'A' })], {}, 137)
    render(<CaseListPage onOpen={() => {}} />)

    const nav = screen.getByRole('navigation', { name: '分页' })
    expect(within(nav).getByText('第 1 / 3 页 · 共 137 个')).toBeTruthy()
    // 原生 disabled：点不动，也不进 Tab 序列
    expect(nav.contains(screen.getByRole('button', { name: '‹ 上一页' }))).toBe(true)
    expect(screen.getByRole('button', { name: '‹ 上一页' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '下一页 ›' }).hasAttribute('disabled')).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    expect(within(nav).getByText('第 2 / 3 页 · 共 137 个')).toBeTruthy()
  })

  it('关键词一变页码回 1（否则新结果从第 3 页开始看，像搜不到）', () => {
    vi.useFakeTimers()
    mockCases([row({ id: 1, name: 'A' })], {}, 137)
    render(<CaseListPage onOpen={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    expect(lastQuery().page).toBe(3)

    typeKeyword('谭某某')
    settleDebounce()
    expect(lastQuery()).toMatchObject({ search: '谭某某', page: 1 })
  })

  it('一页装得下时不渲染分页条', () => {
    mockCases([row({ id: 1, name: 'A' })], {}, 50)
    render(<CaseListPage onOpen={() => {}} />)
    expect(screen.queryByRole('navigation', { name: '分页' })).toBeNull()
  })

  it('翻页请求在飞时保留旧列表（不闪白），只标 aria-busy + 降透明度并禁用翻页', () => {
    mockCases([row({ id: 1, name: 'A' })], { loading: true }, 137)
    render(<CaseListPage onOpen={() => {}} />)

    // 旧行还在
    expect(screen.getByText('A')).toBeTruthy()
    // 不退回骨架
    expect(screen.queryByText('正在加载案件…')).toBeNull()
    const card = screen.getByText('A').closest('[aria-busy]')
    expect(card?.getAttribute('aria-busy')).toBe('true')
    expect(card?.className).toContain('opacity-60')
    // 请求在飞时两端都禁用，防连点翻过头
    expect(screen.getByRole('button', { name: '下一页 ›' }).hasAttribute('disabled')).toBe(true)
  })

  it('总数变小导致当前页越界时回夹到最后一页，而不是掉进「还没有案件」', () => {
    // 场景：用户在第 1 页（此刻服务端 137 件 = 3 页），期间别人删了大半数据，
    // 下一次取值只回来 50 件（1 页）。点「下一页」这个动作本身合法（按钮按旧 total 判定为可用），
    // 但落地后 page=2 > totalPages=1，必须回夹。
    mockCases([row({ id: 1, name: 'A' })], {}, 137)
    render(<CaseListPage onOpen={() => {}} />)

    // 数据在这一次 render 与下一次之间变小
    mockCases([row({ id: 9, name: 'B' })], {}, 50)
    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))

    // 回夹到第 1 页；页面仍在「有数据」而不是空态
    expect(lastQuery().page).toBe(1)
    expect(screen.queryByText('还没有案件，先受理一笔委托。')).toBeNull()
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

  it('案由为空写「（未填案由）」', () => {
    mockCases([row({ id: 2, name: 'A', cause_of_action: null })])
    render(<CaseListPage onOpen={() => {}} />)

    expect(screen.getByText('（未填案由）')).toBeTruthy()
  })

  it('后端返回 id 为 null 时不崩：照常渲染，点击不把空 id 交给上层', () => {
    const onOpen = vi.fn()
    mockCases([row({ id: null, name: '缺 id 的脏数据' })])
    render(<CaseListPage onOpen={onOpen} />)

    expect(screen.getByText('缺 id 的脏数据')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /缺 id 的脏数据/ }))
    expect(onOpen).not.toHaveBeenCalled()
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

describe('CaseListPage · 骨架与真行同源', () => {
  it('骨架行与真行共用 CASE_ROW_SHELL（各改各的会让数据到位时整页跳一下）', () => {
    const { container } = render(
      <>
        <CaseRow c={row({ id: 1, name: '真行' })} onOpen={() => {}} />
        <CaseRowSkeleton count={1} />
      </>,
    )
    const real = container.querySelector('button')!
    const skeleton = container.querySelector('[data-skeleton-row="case"]')!

    expect(real.className).toContain(CASE_ROW_SHELL)
    expect(skeleton.className).toBe(CASE_ROW_SHELL)
  })
})
