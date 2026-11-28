// @vitest-environment jsdom
/**
 * AI 操作历史面板（jsdom）。
 *
 * 这张面板存在的理由就是让律师看见「AI 动过什么」，所以用例钉的是**最需要被
 * 看见**的三种行（缺一条信任就断一截）：
 * 1. `denied` —— 显示「你拒绝了」（这是人的决定，不是失败）；
 * 2. `verified=false` —— 显示红色「页面报成功但库里没变」（最危险的一种）；
 * 3. `expired` —— 显示「超时未处理」（系统兜底，不是律师拒的）。
 *
 * 另外守：空态文案、拉取失败给可重试提示且不崩、动作中文名来自生成物、
 * header 的入口真的能打开面板并请求最近 50 条。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ fetchUiActionHistory: vi.fn() }))
vi.mock('../api', () => apiMock)

// header 只从 store 读后端清单（这里不需要任何后端）
const storeMock = vi.hoisted(() => ({ backends: [] as Array<Record<string, unknown>> }))
vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))

import type { UiActionHistoryItem } from '../api-types'
import { CopilotHeader, type CopilotHeaderProps } from './CopilotHeader'
import { UiActionHistory } from './UiActionHistory'

/** 一条台账行（默认：判定材料包归属 / 成功 / 未核实 / 无批准人） */
function item(overrides: Partial<UiActionHistoryItem> = {}): UiActionHistoryItem {
  return {
    session_id: 's-1',
    action: 'ui_material_prep_judge',
    risk: 'confirm',
    outcome: 'ok',
    decision: 'approved',
    decided_at: '2026-11-29T09:00:00+08:00',
    verified: null,
    verify_note: '',
    approved_by_name: '',
    created_at: '2026-11-29T09:00:01+08:00',
    observed_location: '/material-prep',
    ...overrides,
  }
}

/** 每个用例一个全新的 QueryClient（关掉重试，失败态一次就现形） */
function renderWithQuery(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

function renderHistory() {
  return renderWithQuery(<UiActionHistory open onOpenChange={vi.fn()} />)
}

/** header 的最小必需 props（默认普通对话、无业务范围、无模型） */
function makeHeaderProps(overrides: Partial<CopilotHeaderProps> = {}): CopilotHeaderProps {
  return {
    railVisible: true,
    onToggleRail: vi.fn(),
    context: null,
    onExitContext: vi.fn(),
    treeDrawerOpen: false,
    onToggleTreeDrawer: vi.fn(),
    dockCapable: false,
    docked: false,
    currentTitle: '',
    currentModel: '',
    currentAgentKind: null,
    onNewSession: vi.fn(),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.fetchUiActionHistory.mockResolvedValue([])
})

describe('UiActionHistory：三种关键行', () => {
  it('denied 显示「你拒绝了」、verified=false 显示红色「页面报成功但库里没变」、expired 显示「超时未处理」', async () => {
    apiMock.fetchUiActionHistory.mockResolvedValue([
      item({ action: 'ui_material_prep_judge', outcome: 'denied', decision: 'denied' }),
      item({ action: 'ui_material_prep_delete_pack', outcome: 'ok', verified: false, verify_note: '材料包仍在' }),
      item({ action: 'ui_material_prep_judge', outcome: 'expired', decision: 'expired' }),
    ])
    renderHistory()

    expect(await screen.findByText('你拒绝了')).toBeTruthy()
    expect(screen.getByText('超时未处理')).toBeTruthy()

    const mismatch = screen.getByText('页面报成功但库里没变')
    expect(mismatch.className).toContain('text-destructive')
  })
})

describe('UiActionHistory：空态与错误态', () => {
  it('没有记录时给一句空态，不渲染空列表', async () => {
    renderHistory()

    expect(await screen.findByText('还没有 AI 操作记录')).toBeTruthy()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('拉取失败给可重试的提示，不崩也不弹错误横幅', async () => {
    apiMock.fetchUiActionHistory.mockRejectedValue(new Error('network down'))
    renderHistory()

    expect(await screen.findByText('操作历史加载失败，请稍后重试。')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(apiMock.fetchUiActionHistory).toHaveBeenCalledTimes(2))
  })
})

describe('UiActionHistory：动作中文名与明细', () => {
  it('中文名从生成物取（ui_material_prep_judge → 判定材料包归属），并显示批准人与时间', async () => {
    apiMock.fetchUiActionHistory.mockResolvedValue([
      item({ verified: true, approved_by_name: '王律师' }),
    ])
    renderHistory()

    expect(await screen.findByText('判定材料包归属')).toBeTruthy()
    expect(screen.getByText('经 王律师 批准')).toBeTruthy()
    expect(screen.getByText('服务端已核实')).toBeTruthy()
    expect(screen.getByRole('list', { name: 'AI 操作记录' })).toBeTruthy()
    expect(document.querySelector('time')?.textContent).not.toBe('')
  })
})

describe('CopilotHeader：历史入口', () => {
  it('点「AI 操作历史」打开面板，并按默认 50 条拉取', async () => {
    renderWithQuery(<CopilotHeader {...makeHeaderProps()} />)

    fireEvent.click(screen.getByRole('button', { name: 'AI 操作历史' }))

    expect(await screen.findByText('还没有 AI 操作记录')).toBeTruthy()
    expect(apiMock.fetchUiActionHistory).toHaveBeenCalledWith(50)
  })
})
