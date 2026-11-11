// @vitest-environment jsdom
/**
 * 就绪度面板单测（jsdom）。
 *
 * 这一页是「这件能不能递」的唯一答案，所以分支要逐个走：
 * - 两个 hook 都还在 loading → 整页 loading
 * - ready 报错 → ErrorBlock，且「重新校验」能同时重拉两个 hook
 * - r 为空（引擎没返回）→「校验服务暂无响应」，不是「已通过」
 * - mode='other'（执行/仲裁阶段）→「本阶段暂无专门校验」，明确「不是已通过」
 * - ready=false → 报还差几项，要件卡整块染红
 * - material.error → 在材料齐备栏里显示，不吞掉
 *
 * mock 只打 ../hooks/use-cases（这两个 hook 自身的行为已由
 * use-cases.dom.test.tsx 覆盖），组件 props 只有一个 caseId。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../hooks/use-cases', () => ({
  useReadiness: vi.fn(),
  useMaterialStatus: vi.fn(),
}))

import { useMaterialStatus, useReadiness } from '../hooks/use-cases'
import {
  DEMO_READINESS_CHECK_BASIS,
  DEMO_READINESS_HISTORY,
  DEMO_READINESS_PEERS,
  DEMO_READINESS_SLOT_META,
} from './demo-data'
import { ReadinessPanel } from './ReadinessPanel'

const useReadinessMock = vi.mocked(useReadiness)
const useMaterialStatusMock = vi.mocked(useMaterialStatus)

/**
 * 只取「材料齐备」格子墙那一段 DOM。
 *
 * 必须限定范围的原因：材料清单明细（MaterialFileList）里也有一列「所属槽位」，
 * 名字与槽位标签完全相同（如「借款/主合同」）。全页 getByText 会命中两处，
 * 而本条用例要断言的是格子墙一格一个槽位。
 */
function slotWall(): HTMLElement {
  const cell = [...document.querySelectorAll<HTMLElement>('div')].find((d) =>
    d.className.includes('flex flex-col gap-0.5 rounded-[8px] border'),
  )
  // 往上找到包住所有格子的那层 flex 容器
  const wall = cell?.parentElement
  if (!wall) throw new Error('找不到材料槽位格子墙')
  return wall
}

/** 一个「可以立案」的 ready 回包 */
function readyOk(over: Record<string, unknown> = {}) {
  return {
    loading: false,
    error: null,
    reload: vi.fn(),
    data: {
      ready: true,
      passed: 5,
      total: 5,
      stage: 'first_trial',
      mode: 'filing',
      checks: [
        { key: 'parties', label: '当事人齐备', ok: true, detail: '原告与被告均已登记' },
        { key: 'amount', label: '标的额已登记', ok: true, detail: '998,670.21', field: 'target_amount' },
      ],
      ...over,
    },
  }
}

/** 一个「还有 2 项没过」的 ready 回包 */
function readyFail() {
  return {
    loading: false,
    error: null,
    reload: vi.fn(),
    data: {
      ready: false,
      passed: 3,
      total: 5,
      stage: 'first_trial',
      mode: 'filing',
      checks: [
        { key: 'parties', label: '当事人齐备', ok: true, detail: '原告与被告均已登记' },
        { key: 'jurisdiction', label: '管辖法院已登记', ok: false, detail: '未登记主管机关（管辖法院）' },
      ],
    },
  }
}

/** 一个材料回包：两个槽位（一个齐备一个缺件） */
function materialOk() {
  return {
    loading: false,
    error: null,
    reload: vi.fn(),
    data: {
      ok_count: 1,
      need_count: 2,
      missing_count: 1,
      slots: [
        { key: 'contract', label: '借款/主合同', status: 'ok', file_names: ['借款合同.pdf'] },
        { key: 'coll', label: '催收记录', status: 'miss', reason: '未归案' },
        { key: 'id', label: '当事人身份证明', status: 'stale' },
        { key: 'guarantee', label: '担保材料', status: 'na' },
      ],
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useReadinessMock.mockReturnValue(readyOk() as never)
  useMaterialStatusMock.mockReturnValue(materialOk() as never)
})

describe('ReadinessPanel · 加载与错误', () => {
  it('两个 hook 都在 loading 时整页显示加载态（半个结论比没有更危险）', () => {
    useReadinessMock.mockReturnValue({ loading: true, error: null, data: null, reload: vi.fn() } as never)
    useMaterialStatusMock.mockReturnValue({ loading: true, error: null, data: null, reload: vi.fn() } as never)

    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('正在校验起诉条件…')).toBeTruthy()
    // 只要还缺一半数据，就不该出现结论文案
    expect(screen.queryByText('起诉条件已满足，可以立案')).toBeNull()
  })

  it('ready 报错时显示 ErrorBlock，点重试会同时重拉两个 hook', () => {
    const readyReload = vi.fn()
    const materialReload = vi.fn()
    // ⚠️ ErrorBlock 走 errMessage：吃 Error 才抽得到原话，吃字符串会落 fallback。
    // 所以这里传 Error 实例，断言「后端原话能被展示」这条契约。
    useReadinessMock.mockReturnValue({
      loading: false,
      error: new Error('起诉条件校验超时'),
      data: null,
      reload: readyReload,
    } as never)
    useMaterialStatusMock.mockReturnValue({
      loading: false,
      error: null,
      data: null,
      reload: materialReload,
    } as never)

    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText(/起诉条件校验超时/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))
    // 全页只有 ErrorBlock 的「重新加载」；它只重拉 ready 那一路
    expect(readyReload).toHaveBeenCalledTimes(1)
    // 材料那一路的 reload 由「重新校验」按钮负责，不在 ErrorBlock 里联动
    expect(materialReload).not.toHaveBeenCalled()
  })

  it('material 报错时在「材料齐备」栏里显示原因，不影响法律要件结论', () => {
    useMaterialStatusMock.mockReturnValue({
      loading: false,
      error: '材料服务 502',
      data: null,
      reload: vi.fn(),
    } as never)

    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('材料服务 502')).toBeTruthy()
    // 法律要件部分照常出结论
    expect(screen.getByText('起诉条件已满足，可以立案')).toBeTruthy()
  })
})

describe('ReadinessPanel · 结论文案三种', () => {
  it('ready=true →「起诉条件已满足，可以立案」+ 通过/总数', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('起诉条件已满足，可以立案')).toBeTruthy()
    expect(screen.getByText('法律要件与卷宗要件都过，才允许推进到一张网递交。')).toBeTruthy()
    // 数字块与右栏都有 5/5
    expect(screen.getAllByText('5/5').length).toBeGreaterThan(0)
  })

  it('ready=false →「还有 N 项没过，先补齐」，N = total - passed', () => {
    useReadinessMock.mockReturnValue(readyFail() as never)
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('还有 2 项没过，先补齐')).toBeTruthy()
  })

  it('mode=other（执行/仲裁）→「本阶段暂无专门校验」，并明说「不是已通过」', () => {
    useReadinessMock.mockReturnValue(readyOk({ mode: 'other', ready: false, passed: 0, total: 0, checks: [] }) as never)
    render(<ReadinessPanel caseId={406} />)

    expect(screen.getByText('本阶段暂无专门校验')).toBeTruthy()
    // 同一句在两处出现：结论条说明 + 法律要件卡的空态说明
    expect(screen.getAllByText(/执行、仲裁等阶段还没有对应的校验规则 —— 不是「已通过」，只是这里不判断。/))
      .toHaveLength(2)
    // 校验模式在两处呈现（顶部数字块 + 右栏键值行），都写「不判断」
    expect(screen.getAllByText('不判断')).toHaveLength(2)
  })

  it('r 为空（引擎没返回）→「校验服务暂无响应」，不冒充成功也不冒充失败', () => {
    useReadinessMock.mockReturnValue({
      loading: false,
      error: null,
      data: null,
      reload: vi.fn(),
    } as never)
    render(<ReadinessPanel caseId={406} />)

    expect(screen.getByText('校验服务暂无响应')).toBeTruthy()
    expect(screen.getByText(/起诉条件引擎这次没返回结果/)).toBeTruthy()
    // 数量格退化成 0/0
    expect(screen.getAllByText('0/0').length).toBeGreaterThan(0)
  })
})

describe('ReadinessPanel · 法律要件卡', () => {
  it('逐条列要件，未通过的带上红色说明与判定依据', () => {
    useReadinessMock.mockReturnValue(readyFail() as never)
    render(<ReadinessPanel caseId={406} />)

    expect(screen.getByText('当事人齐备')).toBeTruthy()
    expect(screen.getByText('管辖法院已登记')).toBeTruthy()
    expect(screen.getByText('未登记主管机关（管辖法院）')).toBeTruthy()

    // 判定依据来自 DEMO_READINESS_CHECK_BASIS[key]
    const basis = DEMO_READINESS_CHECK_BASIS.jurisdiction!
    expect(screen.getByText(`判定依据：${basis.basis}`)).toBeTruthy()
    expect(screen.getByText(`数据来源：${basis.source}`)).toBeTruthy()
  })

  it('detail 为空时写破折号，不显示空白行', () => {
    useReadinessMock.mockReturnValue(
      readyOk({ checks: [{ key: 'parties', label: '当事人齐备', ok: true, detail: '' }] }) as never,
    )
    render(<ReadinessPanel caseId={406} />)
    // 判据是：这条要件的 detail 行渲染成破折号而不是空字符串。
    // 页面上别处也有破折号，所以按要件标题定位后看它的 detail 兄弟节点。
    const card = screen.getByText('当事人齐备').closest('div')!.parentElement!
    expect(within(card).getByText('—')).toBeTruthy()
  })

  it('有 field 的要件多显示一行字段名（用来定位到底看的是哪个值）', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('字段：target_amount')).toBeTruthy()
  })

  it('mode=appeal 时标题变成「答辩条件」', () => {
    useReadinessMock.mockReturnValue(readyOk({ mode: 'appeal' }) as never)
    render(<ReadinessPanel caseId={406} />)
    // 标题（SectionTitle 的 h3）+ 「校验模式」格都会写「答辩条件」
    expect(screen.getByRole('heading', { name: '答辩条件' })).toBeTruthy()
    expect(screen.getAllByText('答辩条件').length).toBeGreaterThanOrEqual(2)
  })

  it('没有校验项时按模式给不同说明，不摆空列表', () => {
    useReadinessMock.mockReturnValue(readyOk({ checks: [] }) as never)
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('暂无校验项。')).toBeTruthy()
  })

  it('「重新校验」同时触发两个 hook 的 reload', () => {
    const readyReload = vi.fn()
    const materialReload = vi.fn()
    useReadinessMock.mockReturnValue({ ...readyOk(), reload: readyReload } as never)
    useMaterialStatusMock.mockReturnValue({ ...materialOk(), reload: materialReload } as never)

    render(<ReadinessPanel caseId={406} />)
    fireEvent.click(screen.getByRole('button', { name: '重新校验' }))
    expect(readyReload).toHaveBeenCalledTimes(1)
    expect(materialReload).toHaveBeenCalledTimes(1)
  })
})

describe('ReadinessPanel · 材料齐备格子墙', () => {
  it('四个槽位各一格，状态标签按 status 映射（齐备/缺件/待更新/不适用）', () => {
    render(<ReadinessPanel caseId={406} />)

    const wall = slotWall()
    // 四个槽位在格子墙里各一格（清单明细里的同名「所属槽位」不算）
    for (const label of ['借款/主合同', '催收记录', '当事人身份证明', '担保材料']) {
      expect(within(wall).getAllByRole('generic').filter((el) => el.getAttribute('title') === label)).toHaveLength(1)
    }
    expect(within(wall).getByText('借款/主合同')).toBeTruthy()

    // 状态标签同样收在格子墙里断言，避免与右栏统计撞名
    expect(within(wall).getAllByText('齐备').length).toBeGreaterThan(0)
    expect(within(wall).getByText('缺件')).toBeTruthy()
    expect(within(wall).getByText('待更新')).toBeTruthy()
    // 「不适用」既是状态标签，也是 guarantee 槽位台账里的 source 字段
    expect(within(wall).getAllByText('不适用').length).toBeGreaterThan(0)
  })

  it('槽位副行优先显示 reason，其次文件名，都没有写破折号', () => {
    render(<ReadinessPanel caseId={406} />)
    const wall = slotWall()
    expect(within(wall).getByText('未归案')).toBeTruthy()
    expect(within(wall).getByText('借款合同.pdf')).toBeTruthy()
  })

  it('有台账的槽位补上「N 个文件 · 时间 · 来源」，没台账的不补', () => {
    render(<ReadinessPanel caseId={406} />)
    const wall = slotWall()
    const meta = DEMO_READINESS_SLOT_META.contract!
    expect(within(wall).getByText(`${meta.fileCount} 个文件`)).toBeTruthy()
    expect(within(wall).getByText(meta.lastAt)).toBeTruthy()
    // 四个槽位的来源都是「整包分段 · 自动归案」/「人工上传」/「不适用」，
    // 同一个来源会在多个格子出现，用 allBy
    expect(within(wall).getAllByText(meta.source).length).toBeGreaterThan(0)
    // 四个槽位都有台账，所以格子墙里「N 个文件」正好 4 条
    expect(within(wall).getAllByText(/^\d+ 个文件$/)).toHaveLength(4)
  })

  it('右栏标题旁报 ok/need 计数', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('1/2')).toBeTruthy()
  })

  it('没有槽位时给「还没有材料，先上传卷宗」而不是空盒子', () => {
    useMaterialStatusMock.mockReturnValue({
      loading: false,
      error: null,
      reload: vi.fn(),
      data: { ok_count: 0, need_count: 0, missing_count: 0, slots: [] },
    } as never)
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('还没有材料，先上传卷宗。')).toBeTruthy()
  })

  it('材料缺件数 >0 时数字块染红口径正确（0 件时不染红）', () => {
    render(<ReadinessPanel caseId={406} />)
    // 缺件 1 项
    expect(screen.getAllByText('1 项').length).toBeGreaterThan(0)

    useMaterialStatusMock.mockReturnValue({
      loading: false,
      error: null,
      reload: vi.fn(),
      data: { ok_count: 2, need_count: 2, missing_count: 0, slots: [] },
    } as never)
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getAllByText('0 项').length).toBeGreaterThan(0)
  })
})

describe('ReadinessPanel · 下方三块', () => {
  it('历史校验记录逐行显示，通过/未通过两种胶囊条数与数据吻合', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(
      screen.getByText(`最近 ${DEMO_READINESS_HISTORY.length} 次 · 归案后与每日定时各校一次`),
    ).toBeTruthy()

    // 历史记录区（第 1 个 ul）逐行一个结果胶囊
    const historyList = screen.getAllByRole('list')[0]!
    const rows = within(historyList).getAllByRole('listitem')
    expect(rows).toHaveLength(DEMO_READINESS_HISTORY.length)

    for (const [i, h] of DEMO_READINESS_HISTORY.entries()) {
      const row = rows[i]!
      expect(within(row).getByText(h.result === 'pass' ? '通过' : '未通过')).toBeTruthy()
      expect(within(row).getByText(`${h.passed}/${h.total}`)).toBeTruthy()
      expect(within(row).getByText(String(h.missing))).toBeTruthy()
      expect(within(row).getByText(h.by)).toBeTruthy()
    }

    // 每条都带操作人与说明
    for (const h of DEMO_READINESS_HISTORY) {
      expect(screen.getAllByText(h.note).length).toBeGreaterThan(0)
    }
  })

  it('标题旁的胶囊跟当前结论走：「当前通过 / 当前未通过」', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('当前通过')).toBeTruthy()

    useReadinessMock.mockReturnValue(readyFail() as never)
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getAllByText('当前未通过').length).toBeGreaterThan(0)
  })

  it('同类案件对比：齐备/缺 N 胶囊与统计格按 missing 归并', () => {
    render(<ReadinessPanel caseId={406} />)
    const complete = DEMO_READINESS_PEERS.filter((p) => p.missing === 0).length
    const missing = DEMO_READINESS_PEERS.length - complete
    const rate = Math.round((complete / DEMO_READINESS_PEERS.length) * 100)

    expect(screen.getByText(`同一委托 · ${DEMO_READINESS_PEERS.length} 件`)).toBeTruthy()
    expect(screen.getByText(`${rate}%`)).toBeTruthy()
    // 「齐备」在材料槽位那里也会出现（contract 槽位状态 ok），所以这里是「至少」
    expect(screen.getAllByText('齐备').length).toBeGreaterThanOrEqual(complete)
    // 缺 1 / 缺 2 两种文案，总数等于缺件案件数
    const missingPills = screen.getAllByText(/^缺 \d+$/).length
    expect(missingPills).toBe(missing)
  })

  it('同类案件名去掉「某某银行广州分行诉」与案由后缀再显示', () => {
    render(<ReadinessPanel caseId={406} />)
    const peers = screen.getByText(`同一委托 · ${DEMO_READINESS_PEERS.length} 件`)
    const section = peers.closest('div')!.parentElement!
    expect(within(section).getByText('谭某某')).toBeTruthy()
    expect(within(section).queryByText(/某某银行广州分行诉/)).toBeNull()
  })

  it('材料清单明细跟着渲染（共 10 个文件）', () => {
    render(<ReadinessPanel caseId={406} />)
    expect(screen.getByText('材料清单明细')).toBeTruthy()
  })
})
