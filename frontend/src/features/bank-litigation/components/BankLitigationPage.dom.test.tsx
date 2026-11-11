// @vitest-environment jsdom
/**
 * BankLitigationPage：银行批量诉讼的场景 2 全流程页。
 *
 * 这一页的产品判断是「四步是同一件事的连续动作，不做成四个路由」，
 * 所以页面的核心是一条**状态线**：先选案 → 同页内按办案时间线切分区。
 * 这里钉住这条线：
 * - 没选案时只给案件列表；选中（或带 initialCaseId 进来）直接进工作区
 * - 工作区三态：加载中 / 加载失败可重试 / 正常
 * - 导航分组按 SECTIONS 的首次出现顺序聚合（主链 7 段 + 支线 3 段），
 *   点击切换右侧内容；默认落在「① 收案」（律师打开案件的第一个动作）
 * - 页头 meta 逐项照实，缺值写占位而不是留空
 * - 面包屑「办案」回列表（保留选中案件是列表自己的事）
 *
 * 十个分区面板全部 stub：本文件测的是路由 / 导航 / 页壳，不是各面板内容。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  useCase: { loading: false, error: null as string | null, data: null as unknown, reload: vi.fn() },
  onOpen: undefined as ((id: number) => void) | undefined,
}))

vi.mock('../hooks/use-cases', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/use-cases')>()
  return { ...actual, useCase: () => stubs.useCase }
})

vi.mock('./CaseListPage', () => ({
  CaseListPage: ({ onOpen }: { onOpen: (id: number) => void }) => {
    stubs.onOpen = onOpen
    return (
      <button type="button" onClick={() => onOpen(77)}>
        CASE_LIST
      </button>
    )
  },
}))
vi.mock('./FilingPanels', () => ({
  CourtFilingPanel: ({ caseId }: { caseId: number }) => <div>COURT_FILING:{caseId}</div>,
}))
vi.mock('./DocConvertPanel', () => ({
  DocConvertPanel: ({ caseId }: { caseId: number }) => <div>DOC_CONVERT:{caseId}</div>,
}))
vi.mock('./OAActionPanels', () => ({ OAStampPanel: () => <div>OA_STAMP</div> }))
vi.mock('./ArchiveChecklistPanel', () => ({ OAArchivePanel: () => <div>OA_ARCHIVE</div> }))
vi.mock('./stages/ContractPanel', () => ({ ContractPanel: () => <div>CONTRACT_PANEL</div> }))
vi.mock('./stages/FilingPanel', () => ({ FilingPanel: () => <div>FILING_PANEL</div> }))
vi.mock('./stages/GapPanel', () => ({ GapPanel: () => <div>GAP_PANEL</div> }))
vi.mock('./stages/IntakePanel', () => ({ IntakePanel: () => <div>INTAKE_PANEL</div> }))
vi.mock('./stages/ReturnedPanel', () => ({ ReturnedPanel: () => <div>RETURNED_PANEL</div> }))
vi.mock('./stages/UnderstandPanel', () => ({ UnderstandPanel: () => <div>UNDERSTAND_PANEL</div> }))

import { BankLitigationPage } from './BankLitigationPage'

/** 案件详情：本页只读到页头 meta 这几个字段 */
function caseRow(over: Record<string, unknown> = {}) {
  return {
    id: 44,
    name: '某某银行诉张某金融借款合同纠纷',
    cause_of_action: '金融借款合同纠纷',
    current_stage: 'first_trial',
    status: '在办',
    target_amount: '998670.21',
    filing_number: null,
    ...over,
  }
}

function loaded(over: Record<string, unknown> = {}) {
  stubs.useCase = { loading: false, error: null, data: caseRow(over), reload: vi.fn() }
}

beforeEach(() => {
  vi.clearAllMocks()
  stubs.onOpen = undefined
  loaded()
})

describe('BankLitigationPage · 选案线', () => {
  it('没选案：只渲染案件列表，不进工作区', () => {
    render(<BankLitigationPage />)
    expect(screen.getByText('CASE_LIST')).toBeTruthy()
    expect(screen.getByText('银行批量诉讼')).toBeTruthy()
    expect(screen.queryByText('INTAKE_PANEL')).toBeNull()
  })

  it('从列表选案 → 进入该案工作区，默认落在「① 收案」', () => {
    render(<BankLitigationPage />)
    fireEvent.click(screen.getByText('CASE_LIST'))
    expect(screen.getByText('INTAKE_PANEL')).toBeTruthy()
    expect(screen.getByText('某某银行诉张某金融借款合同纠纷')).toBeTruthy()
  })

  it('带 initialCaseId 进来直接进工作区（深链入口）', () => {
    render(<BankLitigationPage initialCaseId={44} />)
    expect(screen.getByText('INTAKE_PANEL')).toBeTruthy()
    expect(screen.queryByText('CASE_LIST')).toBeNull()
  })

  it('initialCaseId 为 null 时仍从列表起（不把 null 当 0 号案件）', () => {
    render(<BankLitigationPage initialCaseId={null} />)
    expect(screen.getByText('CASE_LIST')).toBeTruthy()
  })

  it('面包屑「办案」回到案件列表', () => {
    render(<BankLitigationPage initialCaseId={44} />)
    fireEvent.click(screen.getByText('办案'))
    expect(screen.getByText('CASE_LIST')).toBeTruthy()
  })
})

describe('BankLitigationPage · 工作区三态', () => {
  it('加载中：页壳仍在，内容显示加载态', () => {
    stubs.useCase = { loading: true, error: null, data: null, reload: vi.fn() }
    render(<BankLitigationPage initialCaseId={44} />)
    expect(screen.getByText('正在加载案件…')).toBeTruthy()
    expect(screen.getByText('案件')).toBeTruthy()
  })

  it('加载失败：显示后端原话并可重试', () => {
    const reload = vi.fn()
    // useLoad 的 error 是已归一化的字符串（raw Error 在 hook 里就取了 message），
    // 这里照实填，让断言钉住的内容与真实数据形状一致。
    stubs.useCase = { loading: false, error: '案件已归档', data: null, reload }
    render(<BankLitigationPage initialCaseId={44} />)
    // ErrorBlock 走 errMessage：字符串原样透出
    expect(screen.getByText('案件已归档')).toBeTruthy()
    fireEvent.click(screen.getByText('重新加载'))
    expect(reload).toHaveBeenCalled()
  })

  it('没有数据也没报错：说的是「案件不存在」，给回列表而不是假重试', () => {
    const reload = vi.fn()
    stubs.useCase = { loading: false, error: null, data: null, reload }
    render(<BankLitigationPage initialCaseId={44} />)
    // 拉取成功但没案子：说的是「案件不存在」而不是笼统的「加载失败」
    // （后者会被读成网络故障，引用户白点一次重试）。
    expect(screen.getByRole('alert').textContent).toContain('案件不存在')
    // 查无此案重试没有意义：按钮是「返回案件列表」，且不会去调 reload。
    fireEvent.click(screen.getByText('返回案件列表'))
    expect(reload).not.toHaveBeenCalled()
  })
})

describe('BankLitigationPage · 页头 meta', () => {
  it('案由 / 阶段 / 状态 / 标的额逐项照实', () => {
    const { container } = render(<BankLitigationPage initialCaseId={44} />)
    const text = container.textContent ?? ''
    expect(text).toContain('金融借款合同纠纷')
    expect(text).toContain('first_trial')
    expect(text).toContain('在办')
    expect(text).toContain('¥998,670.21')
  })

  it('缺案由 / 缺阶段 / 缺标的额时写占位文案（不留空白让人猜）', () => {
    loaded({ cause_of_action: null, current_stage: null, target_amount: null })
    const { container } = render(<BankLitigationPage initialCaseId={44} />)
    const text = container.textContent ?? ''
    expect(text).toContain('（未填案由）')
    expect(text).toContain('（未设阶段）')
    expect(text).not.toContain('标的')
  })

  it('有立案号时一并显示（跨行也不截断语义）', () => {
    // 案号按隐私闸门口径脱敏（年号用 20XX、区号用 01、序号用某某）
    loaded({ filing_number: '（20XX）粤01民初某某号' })
    render(<BankLitigationPage initialCaseId={44} />)
    expect(screen.getByText('（20XX）粤01民初某某号')).toBeTruthy()
  })
})

describe('BankLitigationPage · 分区导航', () => {
  it('按「主链 · 律师视角」与「支线」两组聚合，条目按时间线顺序', () => {
    render(<BankLitigationPage initialCaseId={44} />)
    expect(screen.getByText('主链 · 律师视角')).toBeTruthy()
    expect(screen.getByText('支线')).toBeTruthy()

    const labels = screen
      .getAllByRole('button')
      .map((b) => b.querySelector('span > span')?.textContent)
      .filter((s): s is string => Boolean(s))
    expect(labels).toEqual([
      '① 收案',
      '② 读懂',
      '③ 缺件',
      '④ 文书',
      '⑤ 回扫',
      '⑥ 校验',
      '一张网提交',
      '要素式转换',
      'OA 盖章',
      'OA 归档',
    ])
  })

  it('默认分区标 aria-current="page"，其余不标', () => {
    render(<BankLitigationPage initialCaseId={44} />)
    const current = screen.getAllByRole('button').filter((b) => b.getAttribute('aria-current') === 'page')
    expect(current).toHaveLength(1)
    expect(current[0]!.textContent).toContain('① 收案')
  })

  it('点分区切换右侧内容，且同时只有一个分区被标为当前', () => {
    render(<BankLitigationPage initialCaseId={44} />)

    const expectations: Array<[string, string]> = [
      ['② 读懂', 'UNDERSTAND_PANEL'],
      ['③ 缺件', 'GAP_PANEL'],
      ['④ 文书', 'CONTRACT_PANEL'],
      ['⑤ 回扫', 'RETURNED_PANEL'],
      ['⑥ 校验', 'FILING_PANEL'],
      ['一张网提交', 'COURT_FILING:44'],
      ['要素式转换', 'DOC_CONVERT:44'],
      ['OA 盖章', 'OA_STAMP'],
      ['OA 归档', 'OA_ARCHIVE'],
      ['① 收案', 'INTAKE_PANEL'],
    ]
    for (const [label, marker] of expectations) {
      fireEvent.click(screen.getByText(label))
      expect(screen.getByText(marker)).toBeTruthy()
      const current = screen.getAllByRole('button').filter((b) => b.getAttribute('aria-current') === 'page')
      expect(current).toHaveLength(1)
      expect(current[0]!.textContent).toContain(label)
    }
  })

  it('每个分区都带副标题（只看裸文字看不出点进去看到什么）', () => {
    render(<BankLitigationPage initialCaseId={44} />)
    expect(screen.getByText('客户材料自动拆分')).toBeTruthy()
    expect(screen.getByText('核签字盖章 → 去一张网')).toBeTruthy()
    expect(screen.getByText('结案材料入档')).toBeTruthy()
  })
})
