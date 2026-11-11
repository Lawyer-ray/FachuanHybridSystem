// @vitest-environment jsdom
/**
 * NonLitDetailPage：非诉项目详情页（页面级编排）。
 *
 * 这一层最难也最该被钉住的是**非诉内部的三种工作脊椎**怎么分流，
 * 因为判错会让泰国租赁审查落到「设计阶段 / 校验交付物」卡上，律师看不到逐条审查：
 * - case_type=advisor          → 常法顾问工作台；左栏是**服务事项流**，右栏带文件夹
 * - case_type=special          → 专项工作台；左栏是**阶段与交付物表**，右栏是阶段目录
 * - case_type=special + 合同名含「合同审查」→ 跨境工作台（后端只有两个 code，
 *   跨境只能靠合同名区分）
 * - 其它未知 case_type         → 兜底跨境
 *
 * 另外覆盖三态（非法 id → 重定向 /projects、加载中、加载失败可重试）、
 * 周期轴标题（常法=服务期、专项=项目周期 + 阶段图例）与「下一程序」块。
 *
 * 编排层之外的一切（布局、右栏、各工作台）全部 stub：它们各有自己的测试。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  params: { id: '318' } as { id: string | undefined },
  page: {} as Record<string, unknown>,
  special: { tree: [] as unknown[], saving: false, isLoading: false, stagesError: null, setTreeLocal: vi.fn(), saveStages: vi.fn() },
  svc: { items: [] as unknown[], sourceSubpath: '3-办案', candidates: [] as unknown[], isLoading: false },
  netWidth: 1440,
  docked: true,
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
  termBar: vi.fn(),
  layout: vi.fn(),
  rail: vi.fn(),
  folders: vi.fn(),
  svcStream: vi.fn(),
  phaseList: vi.fn(),
  header: vi.fn(),
  listFolderEntries: vi.fn(),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useParams: () => h.params }
})

vi.mock('sonner', () => ({ toast: h.toast }))

vi.mock('./use-deal-detail-page', () => ({
  useDealDetailPage: () => h.page,
  soonToast: (what: string) => h.toast.info(what + '正在开发中'),
  useDealCopilotContext: vi.fn(),
}))
vi.mock('./use-service-items', () => ({ useServiceItems: () => h.svc }))
vi.mock('./use-special-phases', () => ({ useSpecialPhases: () => h.special }))
vi.mock('./use-net-width', () => ({
  useNetWidth: () => h.netWidth,
  useDockedViewport: () => h.docked,
}))
vi.mock('./refetch-contract', () => ({ refetchContractAndCases: vi.fn() }))
vi.mock('../../api', () => ({ listFolderEntries: h.listFolderEntries }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }) }))

/* ---- 展示层全部 stub：本文件测接线，不测呈现 ---- */
vi.mock('./DetailHeader', () => ({
  DetailHeader: (props: { deal: { client: string } }) => {
    h.header(props)
    return <div>HEADER:{props.deal.client}</div>
  },
}))
vi.mock('./TermBar', () => ({
  TermBar: (props: Record<string, unknown>) => {
    h.termBar(props)
    return <div>TERMBAR:{typeof props.title === 'string' ? props.title : '服务期'}</div>
  },
}))
vi.mock('./DealDocLayout', () => ({
  DOC_SIDE_BY_SIDE_MIN: 1100,
  DealDocLayout: (props: {
    picked: unknown
    docSideBySide: boolean
    focusDoc: boolean
    aside: unknown
    rail: unknown
    children: React.ReactNode
  }) => {
    h.layout(props)
    return (
      <div>
        LAYOUT:picked={String(props.picked !== null)}/side={String(props.docSideBySide)}/focus={String(props.focusDoc)}
        <div>ASIDE:{JSON.stringify(Boolean(props.aside))}</div>
        <div>RAIL:{JSON.stringify(Boolean(props.rail))}</div>
        {props.aside as React.ReactNode}
        {props.rail as React.ReactNode}
        <div>{props.children}</div>
      </div>
    )
  },
}))
vi.mock('./DetailRail', () => ({
  DetailRail: (props: Record<string, unknown>) => {
    h.rail(props)
    return <div>DETAIL_RAIL</div>
  },
}))
vi.mock('./PhaseFoldersCard', () => ({
  PhaseFoldersCard: (props: { rows: Array<{ no: string; name: string; depth: number }>; onOpenDir: (f: string) => void }) => {
    h.folders(props)
    return (
      <button type="button" onClick={() => props.onOpenDir('1-尽职调查')}>
        FOLDERS:{props.rows.length}
      </button>
    )
  },
}))
vi.mock('./ServiceItemStream', () => ({
  ServiceItemStream: (props: Record<string, unknown>) => {
    h.svcStream(props)
    return <div>SERVICE_STREAM</div>
  },
}))
vi.mock('./PhaseListCard', () => ({
  PhaseListCard: (props: Record<string, unknown>) => {
    h.phaseList(props)
    return <div>PHASE_LIST</div>
  },
}))
vi.mock('./nonlit-workbench', () => ({
  AdvisorWorkbench: () => <div>ADVISOR_WB</div>,
  CrossBorderWorkbench: () => <div>CROSSBORDER_WB</div>,
  SpecialPhaseWorkbench: () => <div>SPECIAL_WB</div>,
}))
vi.mock('./ContractFileOverlays', () => ({ ContractFileOverlays: () => <div>OVERLAYS</div> }))
vi.mock('./PaymentDialog', () => ({ PaymentDialog: () => <div>PAY_DIALOG</div> }))
vi.mock('./InvoicePoolDialog', () => ({ InvoicePoolDialog: () => <div>INVOICE_DIALOG</div> }))

import { MemoryRouter } from 'react-router'

import { NonLitDetailPage } from './NonLitDetailPage'

/** 页面里有 <Navigate>/<Link>，必须在 Router 上下文里渲染 */
function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/318']}>
      <NonLitDetailPage />
    </MemoryRouter>,
  )
}

/** 最小可用 deal：只有本页读到的字段 */
function deal(over: Record<string, unknown> = {}) {
  return {
    id: 318,
    client: '某某银行股份有限公司',
    caseType: 'advisor',
    team: [],
    from: '2026-01-01',
    to: '2026-12-31',
    parties: { client: '某某银行' },
    amountNum: 1000,
    totalReceived: '¥0',
    ...over,
  }
}

function basePage(over: Record<string, unknown> = {}) {
  return {
    valid: true,
    d: { isLoading: false, error: null, refetch: vi.fn(), today: new Date('2026-06-30') },
    deal: deal(),
    deadlines: [],
    contacts: [],
    money: [],
    next: null,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  h.params = { id: '318' }
  h.page = basePage()
  h.special = { tree: [], saving: false, isLoading: false, stagesError: null, setTreeLocal: vi.fn(), saveStages: vi.fn() }
  h.svc = { items: [], sourceSubpath: '3-办案', candidates: [], isLoading: false }
  h.netWidth = 1440
  h.docked = true
})

describe('NonLitDetailPage · 三态', () => {
  it('非法 id → 跳 /projects（不渲染页面骨架）', () => {
    h.page = basePage({ valid: false, deal: null })
    const { container } = renderPage()
    expect(container.textContent).toBe('')
    expect(screen.queryByText('CHILDREN:yes')).toBeNull()
  })

  it('加载中：显示「正在加载项目…」', () => {
    h.page = basePage({ deal: null, d: { isLoading: true, error: null, refetch: vi.fn(), today: new Date() } })
    renderPage()
    expect(screen.getByText('正在加载项目…')).toBeTruthy()
  })

  it('失败：显示后端错误并可重试', () => {
    const refetch = vi.fn()
    h.page = basePage({ deal: null, d: { isLoading: false, error: '合同不存在', refetch, today: new Date() } })
    renderPage()
    expect(screen.getByText('合同不存在')).toBeTruthy()
    fireEvent.click(screen.getByText('重试'))
    expect(refetch).toHaveBeenCalled()
  })

  it('deal 缺失但没报错：兜底文案「项目不存在」', () => {
    h.page = basePage({ deal: null })
    renderPage()
    expect(screen.getByText('项目不存在')).toBeTruthy()
  })
})

describe('NonLitDetailPage · 工作台分流', () => {
  it('advisor → 顾问工作台 + 服务事项流 + 右栏带文件夹', () => {
    renderPage()
    expect(screen.getByText('ADVISOR_WB')).toBeTruthy()
    expect(screen.getByText('SERVICE_STREAM')).toBeTruthy()
    expect(screen.queryByText('PHASE_LIST')).toBeNull()
    expect(h.rail.mock.calls[0]![0]).toMatchObject({ showFolder: true })
  })

  it('special → 专项工作台 + 阶段与交付物表 + 右栏让位给阶段目录', () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    h.special = { ...h.special, tree: [{ key: 'a', name: '尽职调查', acceptance: '', open: false, startDate: '', folders: [], deliverables: [] }] }
    renderPage()
    expect(screen.getByText('SPECIAL_WB')).toBeTruthy()
    expect(screen.getByText('PHASE_LIST')).toBeTruthy()
    expect(screen.queryByText('SERVICE_STREAM')).toBeNull()
    expect(h.rail.mock.calls[0]![0]).toMatchObject({ showFolder: false })
    expect(screen.getByText('FOLDERS:1')).toBeTruthy()
  })

  it('special + 合同名含「合同审查」→ 跨境工作台（后端 case_type 分不出跨境）', () => {
    h.page = basePage({ deal: deal({ caseType: 'special', client: '泰国工厂租赁合同审查' }) })
    renderPage()
    expect(screen.getByText('CROSSBORDER_WB')).toBeTruthy()
    expect(screen.queryByText('SPECIAL_WB')).toBeNull()
    // 跨境页仍属专项：阶段表照常渲染
    expect(screen.getByText('PHASE_LIST')).toBeTruthy()
  })

  it('未知 case_type → 兜底跨境工作台', () => {
    h.page = basePage({ deal: deal({ caseType: 'mystery' }) })
    renderPage()
    expect(screen.getByText('CROSSBORDER_WB')).toBeTruthy()
    expect(screen.getByText('SERVICE_STREAM')).toBeTruthy()
  })
})

describe('NonLitDetailPage · 周期轴', () => {
  it('常法：服务期轴 + 事项刻度（events 来自服务事项流）', () => {
    h.svc = {
      ...h.svc,
      items: [{ date: '2026-03-01', kind: '合同', title: '租赁合同审查', status: 'done' }],
    }
    renderPage()
    const props = h.termBar.mock.calls[0]![0]
    expect(props.title).toBeUndefined()
    expect(props.events).toEqual([{ date: '2026-03-01', title: '租赁合同审查' }])
  })

  it('专项：项目周期轴 + 阶段里程碑与「阶段 N / M」图例', () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    h.special = {
      ...h.special,
      tree: [
        { key: 'a', name: '尽职调查', state: 'done', startDate: '2026-02-01', folders: [], deliverables: [] },
        { key: 'b', name: '税务清算', state: 'doing', startDate: '', folders: [], deliverables: [] },
      ],
    }
    renderPage()
    const props = h.termBar.mock.calls[0]![0]
    expect(props.title).toBe('项目周期')
    // 只有带 startDate 的阶段成为里程碑，状态映射 done→ok / doing→doing
    expect(props.milestones).toEqual([{ date: '2026-02-01', title: '尽职调查', state: 'ok' }])
    expect(props.legend).toBe('阶段 1 / 2')
  })

  it('没有阶段时不给图例（不写 0 / 0）', () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    renderPage()
    expect(h.termBar.mock.calls[0]![0].legend).toBeUndefined()
  })

  it('缺 from/to 时整条轴不渲染', () => {
    h.page = basePage({ deal: deal({ from: null, to: null }) })
    renderPage()
    expect(h.termBar).not.toHaveBeenCalled()
  })
})

describe('NonLitDetailPage · 右栏与下一程序', () => {
  it('右栏拿到完整事实卡入参（期限/当事人/团队/收费/动作）', () => {
    const dealObj = deal()
    h.page = basePage({ deal: dealObj, deadlines: [{ id: 1 }], contacts: [{ group: '当事人', rows: [] }], money: [['标的额', '¥1,000']] })
    renderPage()
    const props = h.rail.mock.calls[0]![0]
    expect(props.deal).toBe(dealObj)
    expect(props.team).toEqual([])
    expect(props.deadlines).toEqual([{ id: 1 }])
    expect(props.moneyRows).toEqual([['标的额', '¥1,000']])
    // 四个动作都是函数：新增期限 / 新增收款 / 发票池 / 开文件 / 发起审查
    for (const fn of ['onAddDue', 'onAddPayment', 'onOpenInvoices', 'onOpenFile', 'onReviewFile']) {
      expect(typeof props[fn]).toBe('function')
    }
  })

  it('「＋ 新增期限」是占位动作（当前只有一句 toast）', () => {
    renderPage()
    h.rail.mock.calls[0]![0].onAddDue()
    expect(h.toast.info).toHaveBeenCalledWith('新增期限正在开发中')
  })

  it('有 next 时渲染「下一程序」块，新建按钮也是占位', () => {
    h.page = basePage({ next: '执行' })
    renderPage()
    expect(screen.getByText('下一程序')).toBeTruthy()
    fireEvent.click(screen.getByText('新建执行'))
    expect(h.toast.info).toHaveBeenCalledWith('新建执行正在开发中')
  })

  it('没有 next 时不渲染「下一程序」', () => {
    renderPage()
    expect(screen.queryByText('下一程序')).toBeNull()
  })
})

describe('NonLitDetailPage · 阶段目录与文件预览', () => {
  it('点阶段目录：取到文件就进预览态，并把布局切到「文档在右」', async () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    h.special = { ...h.special, tree: [{ key: 'a', name: '尽职调查', folders: [], deliverables: [] }] }
    h.listFolderEntries.mockResolvedValue({
      files: [{ name: '报告.pdf', subpath: '1-尽职调查/报告.pdf', size: 10, modified_at: '2026-05-01' }],
    })
    renderPage()
    expect(h.layout.mock.calls[0]![0]).toMatchObject({ picked: null, docSideBySide: false })

    fireEvent.click(screen.getByText('FOLDERS:1'))
    expect(await screen.findByText(/LAYOUT:picked=true\/side=true\/focus=false/)).toBeTruthy()
    const props = h.layout.mock.calls.at(-1)![0]
    expect(props.picked).toEqual({
      subpath: '1-尽职调查/报告.pdf',
      name: '报告.pdf',
      size: 10,
      modified_at: '2026-05-01',
    })
    expect(h.listFolderEntries).toHaveBeenCalledWith('contract', 318, '1-尽职调查')
  })

  it('目录里没有文件：给一句「还没有文件」而不是静默', async () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    h.special = { ...h.special, tree: [{ key: 'a', name: '尽职调查', folders: [], deliverables: [] }] }
    h.listFolderEntries.mockResolvedValue({ files: [] })
    renderPage()
    fireEvent.click(screen.getByText('FOLDERS:1'))
    await waitFor(() =>
      expect(h.toast.info).toHaveBeenCalledWith('「1-尽职调查」目录里还没有文件', {
        description: '把交付物拖进合同文件夹后即可点开',
      }),
    )
  })

  it('目录还不存在：读失败也有一句明确的解释（保存阶段后才会建目录）', async () => {
    h.page = basePage({ deal: deal({ caseType: 'special' }) })
    h.special = { ...h.special, tree: [{ key: 'a', name: '尽职调查', folders: [], deliverables: [] }] }
    h.listFolderEntries.mockRejectedValue(new Error('404'))
    renderPage()
    fireEvent.click(screen.getByText('FOLDERS:1'))
    await waitFor(() =>
      expect(h.toast.info).toHaveBeenCalledWith('「1-尽职调查」目录还不存在', {
        description: '保存阶段后系统会在合同文件夹里建同名目录',
      }),
    )
  })
})
