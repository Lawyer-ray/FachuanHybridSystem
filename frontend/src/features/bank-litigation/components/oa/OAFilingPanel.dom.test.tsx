// @vitest-environment jsdom
/**
 * OAFilingPanel：律所 OA 立案面板（服务端 Playwright 填 OA 收案登记）。
 *
 * 三条「别让律师白跑」的不变式：
 * 1. **凭证缺失点之前就说**：站点没配凭证 → 按钮禁用 + 红色徽标 + 右侧进度第一步
 *    直接标 blocked；案件没关联合同同理（后端按合同反查，没合同填不了）。
 * 2. **不能假装秒完成**：执行中按钮禁用、显示轮询次数与后端原始 status。
 * 3. **站点名不写死**：没有后端配置时用 DEMO_OA_SITES 撑画面，有配置就用真实的，
 *    并在切换站点时清掉上一次会话（否则会拿旧结果读新站点）。
 *
 * 子卡（站点清单 / 字段映射 / 历史表 / 失败原因）stub：各自有测试。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  configs: { loading: false, error: null, data: null, reload: vi.fn() } as Record<string, unknown>,
  oa: { phase: 'idle', status: '', error: null, ticks: 0, session: null } as Record<string, unknown>,
  run: vi.fn(() => Promise.resolve()),
  reset: vi.fn(),
  siteList: vi.fn(),
}))

vi.mock('../../hooks/use-cases', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/use-cases')>()
  return { ...actual, useOAConfigs: () => stubs.configs }
})
vi.mock('../../hooks/use-auto-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/use-auto-run')>()
  return { ...actual, useOAFiling: () => ({ state: stubs.oa, run: stubs.run, reset: stubs.reset }) }
})
vi.mock('./OASiteList', () => ({
  OASiteList: (props: {
    sites: Array<{ id: number; name: string; hasCredential: boolean }>
    currentName: string
    onPick: (name: string) => void
  }) => {
    stubs.siteList(props)
    return (
      <div>
        <div>SITE_LIST:{props.currentName}</div>
        {props.sites.map((s) => (
          <button key={s.id} type="button" onClick={() => props.onPick(s.name)}>
            PICK:{s.name}
          </button>
        ))}
      </div>
    )
  },
}))
vi.mock('./OAFieldMapping', () => ({ OAFieldMapping: () => <div>FIELD_MAPPING</div> }))
vi.mock('./OAHistoryTable', () => ({ OAHistoryTable: () => <div>HISTORY_TABLE</div> }))
vi.mock('./OAFailureCauses', () => ({ OAFailureCauses: () => <div>FAILURE_CAUSES</div> }))

import { DEMO_OA_FILING_LOG, DEMO_OA_HISTORY, DEMO_OA_SITES } from '../demo-data'
import { OAFilingPanel } from './OAFilingPanel'

/** 后端返回的 OA 站点配置（有凭证） */
function config(over: Record<string, unknown> = {}) {
  return { id: 1, oa_system_name: '某某所 OA', has_credential: true, ...over }
}

function setup(over: Record<string, unknown> = {}, panel: { caseId?: number; contractId?: number | null } = {}) {
  stubs.configs = { loading: false, error: null, data: [config()], reload: vi.fn(), ...over }
  return render(<OAFilingPanel caseId={panel.caseId ?? 44} contractId={panel.contractId === undefined ? 900 : panel.contractId} />)
}

const FAILED_STEPS = DEMO_OA_FILING_LOG.filter((l) => !l.ok).length
const LOG_MS = DEMO_OA_FILING_LOG.reduce((sum, l) => sum + l.ms, 0)

beforeEach(() => {
  vi.clearAllMocks()
  stubs.oa = { phase: 'idle', status: '', error: null, ticks: 0, session: null }
})

describe('OAFilingPanel · 三态', () => {
  it('读取配置时显示加载态', () => {
    setup({ loading: true, data: null })
    expect(screen.getByText('正在读取 OA 配置…')).toBeTruthy()
  })

  it('配置读取失败可重试', () => {
    const reload = vi.fn()
    setup({ error: new Error('权限不足'), reload })
    expect(screen.getByText('权限不足')).toBeTruthy()
    fireEvent.click(screen.getByText('重新加载'))
    expect(reload).toHaveBeenCalled()
  })
})

describe('OAFilingPanel · 站点来源', () => {
  it('有后端配置时用真实站点（名称取 oa_system_name）', () => {
    setup({ data: [config({ oa_system_name: '甲所 OA' }), config({ id: 2, oa_system_name: '乙所 OA' })] })
    expect(screen.getByText('SITE_LIST:甲所 OA')).toBeTruthy()
    expect(stubs.siteList.mock.calls.at(-1)![0].sites).toEqual([
      { id: 1, name: '甲所 OA', hasCredential: true },
      { id: 2, name: '乙所 OA', hasCredential: true },
    ])
  })

  it('配置为空数组时退回 demo 站点撑住画面（不摊空面板）', () => {
    setup({ data: [] })
    const sites = stubs.siteList.mock.calls.at(-1)![0].sites
    expect(sites.map((s: { name: string }) => s.name)).toEqual(DEMO_OA_SITES.map((d) => d.name))
    // demo 站点的 id 用负数，避免与真实 id 冲突
    expect(sites.every((s: { id: number }) => s.id < 0)).toBe(true)
    expect(sites.map((s: { hasCredential: boolean }) => s.hasCredential)).toEqual(
      DEMO_OA_SITES.map((d) => d.credential),
    )
  })

  it('切换站点：更新当前站点并清掉上一次会话', () => {
    setup({ data: [config({ oa_system_name: '甲所 OA' }), config({ id: 2, oa_system_name: '乙所 OA' })] })
    fireEvent.click(screen.getByText('PICK:乙所 OA'))
    expect(stubs.reset).toHaveBeenCalledTimes(1)
    expect(screen.getByText('SITE_LIST:乙所 OA')).toBeTruthy()
  })
})

describe('OAFilingPanel · 统计与阻断', () => {
  it('顶部四格：本月立案合计数 / 凭证 / 关联合同 / 日志失败步', () => {
    setup()
    const filed = DEMO_OA_SITES.reduce((s, x) => s + x.filedThisMonth, 0)
    expect(screen.getByText(`${filed} 件`)).toBeTruthy()
    // 「已配置」在统计格与右侧进度第一步各出现一次
    expect(screen.getAllByText('已配置').length).toBeGreaterThan(0)
    expect(screen.getByText('已关联')).toBeTruthy()
    // 「N 步」在统计格与右栏「待处理失败」各出现一次
    expect(screen.getAllByText(`${FAILED_STEPS} 步`).length).toBeGreaterThan(0)
  })

  it('没关联合同：按钮禁用、红色徽标、左栏统计改「未关联」', () => {
    setup({}, { contractId: null })
    expect(screen.getByText('案件未关联合同')).toBeTruthy()
    // 「未关联」在统计格 / 本次立案段 / 合同编号格各出现一次
    expect(screen.getAllByText('未关联').length).toBeGreaterThan(0)
    expect((screen.getByRole('button', { name: /在 OA 立案/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('补齐上述两项后才允许发起')).toBeTruthy()
  })

  it('站点没配凭证：额外提示该站点未配凭证，按钮维持禁用', () => {
    setup({ data: [config({ has_credential: false })] })
    expect(screen.getByText('该站点未配凭证')).toBeTruthy()
    expect(screen.getAllByText('未配置').length).toBeGreaterThan(0)
    expect((screen.getByRole('button', { name: /在 OA 立案/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('凭证与合同都齐：按钮可点，没有「补齐」提示', () => {
    setup()
    expect((screen.getByRole('button', { name: /在 OA 立案/ }) as HTMLButtonElement).disabled).toBe(false)
    expect(screen.queryByText('补齐上述两项后才允许发起')).toBeNull()
    expect(screen.queryByText('该站点未配凭证')).toBeNull()
  })
})

describe('OAFilingPanel · 发起与会话', () => {
  it('点立案：提交站点名 / 合同 / 案件三要素', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /在 OA 立案/ }))
    expect(stubs.run).toHaveBeenCalledWith({ site_name: '某某所 OA', contract_id: 900, case_id: 44 })
  })

  it('执行中：按钮禁用并显示「OA 立案进行中…」与轮询次数', () => {
    stubs.oa = { phase: 'running', status: 'running', error: null, ticks: 5, session: null }
    setup()
    expect((screen.getByRole('button', { name: /OA 立案进行中/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('已轮询 5 次')).toBeTruthy()
  })

  it('未跑过时不显示轮询次数', () => {
    setup()
    expect(screen.queryByText(/已轮询/)).toBeNull()
  })
})

describe('OAFilingPanel · 执行日志与右栏', () => {
  it('日志逐步列出阶段、说明、耗时与时间', () => {
    setup()
    expect(screen.getByText(`最近一次 · 共 ${DEMO_OA_FILING_LOG.length} 步 · ${FAILED_STEPS} 次重试`)).toBeTruthy()
    for (const l of DEMO_OA_FILING_LOG) {
      expect(screen.getByTitle(l.message)).toBeTruthy()
      expect(screen.getAllByText(`${l.ms} ms`).length).toBeGreaterThan(0)
      expect(screen.getAllByText(l.at).length).toBeGreaterThan(0)
    }
  })

  it('本次日志耗时按毫秒汇总成秒（一位小数）', () => {
    setup()
    expect(screen.getByText(`${(LOG_MS / 1000).toFixed(1)} s`)).toBeTruthy()
  })

  it('近期表现：已立案件数与最近成功 / 退回时间来自历史记录', () => {
    setup()
    const filed = DEMO_OA_HISTORY.filter((r) => r.state === 'filed').length
    const returned = DEMO_OA_HISTORY.find((r) => r.state === 'returned')
    expect(screen.getByText(`${filed} 件`)).toBeTruthy()
    // 历史表本身也是 stub 之外的动态数据源；这里只断言右栏「最近成功」取自首条
    expect(screen.getAllByText(DEMO_OA_HISTORY[0]!.at).length).toBeGreaterThan(0)
    if (returned) expect(screen.getAllByText(returned.at).length).toBeGreaterThan(0)
  })

  it('本次立案段写明站点与关联合同编号（未关联时写「未关联」）', () => {
    setup()
    expect(screen.getByText('#900')).toBeTruthy()

    setup({}, { contractId: null })
    expect(screen.getAllByText('未关联').length).toBeGreaterThan(0)
  })

  it('字段映射 / 历史立案 / 失败原因三块都在', () => {
    setup()
    expect(screen.getByText('FIELD_MAPPING')).toBeTruthy()
    expect(screen.getByText('HISTORY_TABLE')).toBeTruthy()
    expect(screen.getByText('FAILURE_CAUSES')).toBeTruthy()
  })
})
