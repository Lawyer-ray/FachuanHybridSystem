// @vitest-environment jsdom
/**
 * SystemStatus（设置页·系统状态三卡片）渲染单测（jsdom）。
 *
 * mock 边界：仅 mock 同域 `../api`（四个端点封装）与 `sonner`（toast）。
 * 不 mock @/lib/api——`probeBackend` 的计时逻辑属于被测语义的一部分，留给真实实现。
 *
 * 覆盖：
 * - 三卡齐出（后端 / Django-Q / LLM 网关）与各自的正常态文案
 * - 后端探针：慢响应 >1000ms 判 yellow「在线 · …ms」而非 error
 * - 后端探针失败 → error「无法连接」且不拖垮另两卡（独立性契约）
 * - Django-Q：clusters=0 判「无集群心跳」；>1 判僵尸集群并给告警文案；
 *   clusters=null（redis 探测失败）判「无法探测」而不是误报成 0
 * - LLM：模型列表渲染为可选项、无模型时下拉禁用 + 「测试连接」禁用
 * - 「刷新」统一 invalidate settings 前缀（一次点击三卡一起重取）
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  probeBackend: vi.fn(),
  fetchQClusterStatus: vi.fn(),
  fetchLlmModels: vi.fn(),
  fetchAgentUsage: vi.fn(),
  testLlmConnection: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock('../api', () => ({
  probeBackend: stubs.probeBackend,
  fetchQClusterStatus: stubs.fetchQClusterStatus,
  fetchLlmModels: stubs.fetchLlmModels,
  fetchAgentUsage: stubs.fetchAgentUsage,
  testLlmConnection: stubs.testLlmConnection,
}))
vi.mock('sonner', () => ({ toast: stubs.toast }))

import { SystemStatus } from './SystemStatus'

/** 正常的 Django-Q 聚合（单集群、队列空、今日有成败） */
const Q_OK = {
  clusters: 1,
  queue_depth: 0,
  succeeded_today: 203,
  failed_today: 81,
  last_success_at: '2026-10-27 16:32:33',
  last_failed_at: null,
  broker_error: null,
}

const MODELS = [
  { id: 'kimi-2.6', name: 'kimi-2.6（默认）', backend: 'siliconflow', context_window: 128000 },
  { id: 'glm53', name: 'glm53', backend: 'siliconflow', context_window: 128000 },
]

const USAGE = {
  runs: 12,
  ok_runs: 9,
  error_runs: 3,
  cancelled_runs: 0,
  error_rate: 0.25,
  avg_duration_ms: 2400,
}

function renderStatus() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  render(
    <QueryClientProvider client={qc}>
      <SystemStatus />
    </QueryClientProvider>,
  )
  return { qc, invalidate }
}

/** 默认全绿的数据桩（各用例按需覆盖单点，避免样板重复） */
function stubAllOk() {
  stubs.probeBackend.mockResolvedValue(134)
  stubs.fetchQClusterStatus.mockResolvedValue(Q_OK)
  stubs.fetchLlmModels.mockResolvedValue(MODELS)
  stubs.fetchAgentUsage.mockResolvedValue(USAGE)
}

beforeEach(() => {
  vi.clearAllMocks()
  stubAllOk()
})

afterEach(cleanup)

describe('SystemStatus 三卡齐出', () => {
  it('渲染后端 / Django-Q / LLM 三张卡', async () => {
    renderStatus()
    expect(screen.getByText('后端服务')).toBeTruthy()
    expect(screen.getByText('Django-Q 任务队列')).toBeTruthy()
    expect(screen.getByText('LLM 网关')).toBeTruthy()
    // 等三卡的数据各自落位，避免 act 警告
    await screen.findByText('在线 · 134ms')
  })

  it('正常态：后端延迟 / 队列明细 / 模型数都来自接口数据', async () => {
    renderStatus()
    expect(await screen.findByText('在线 · 134ms')).toBeTruthy()
    expect(await screen.findByText('运行中')).toBeTruthy()
    expect(screen.getByText('203 / 81')).toBeTruthy()
    expect(screen.getByText('2026-10-27 16:32:33')).toBeTruthy()
    expect(await screen.findByText('2 个模型')).toBeTruthy()
    // usage：12 次、成功率 75%（error_rate 0.25）
    expect(screen.getByText('12 次 · 成功率 75%')).toBeTruthy()
    expect(screen.getByText('2.4s')).toBeTruthy()
  })
})

describe('后端探针卡', () => {
  it('慢响应 >1000ms 判黄牌但仍表述为在线（不是 error）', async () => {
    stubs.probeBackend.mockResolvedValue(1500)
    renderStatus()
    expect(await screen.findByText('在线 · 1500ms')).toBeTruthy()
    // 黄牌态不应渲染「无法连接」
    expect(screen.queryByText('无法连接')).toBeNull()
  })

  it('探针失败 → 「无法连接」+ 错误文案，且另两卡照常渲染（独立性）', async () => {
    stubs.probeBackend.mockRejectedValue(new Error('boom'))
    renderStatus()
    expect(await screen.findByText('无法连接')).toBeTruthy()
    // 另两卡不受牵连
    expect(await screen.findByText('运行中')).toBeTruthy()
    expect(await screen.findByText('2 个模型')).toBeTruthy()
  })
})

describe('Django-Q 卡状态判定', () => {
  it('clusters=0 → 无集群心跳（error）', async () => {
    stubs.fetchQClusterStatus.mockResolvedValue({ ...Q_OK, clusters: 0 })
    renderStatus()
    expect(await screen.findByText('无集群心跳')).toBeTruthy()
    expect(screen.getByText('0 个')).toBeTruthy()
  })

  it('clusters>1 → 僵尸集群告警文案（warn）', async () => {
    stubs.fetchQClusterStatus.mockResolvedValue({ ...Q_OK, clusters: 3 })
    renderStatus()
    expect(await screen.findByText('疑似僵尸集群 ×3')).toBeTruthy()
    expect(screen.getByText(/多棵进程树在抢同一队列/)).toBeTruthy()
  })

  it('clusters=null（redis 探测失败）→ 无法探测，不回退成 0 个集群', async () => {
    stubs.fetchQClusterStatus.mockResolvedValue({
      ...Q_OK,
      clusters: null,
      broker_error: 'Connection refused',
    })
    renderStatus()
    // 「无法探测」出现在两处：卡片状态标签 + 「在线集群」行值，故用 getAllByText
    await waitFor(() => expect(screen.getAllByText('无法探测').length).toBeGreaterThan(0))
    // 关键：不能把 null 误显示为「0 个」（那会被读成"没集群在跑"）
    expect(screen.queryByText('0 个')).toBeNull()
    expect(screen.getByText(/redis 探测失败：Connection refused/)).toBeTruthy()
  })

  it('队列接口失败 → 该卡报错，但后端卡与 LLM 卡不受影响', async () => {
    stubs.fetchQClusterStatus.mockRejectedValue(new Error('q down'))
    renderStatus()
    // 普通 Error 的 message 由 errMessage 直接透出（fallback「读取失败」只在无 message 时用）
    await waitFor(() => expect(screen.getByText('q down')).toBeTruthy())
    expect(await screen.findByText('在线 · 134ms')).toBeTruthy()
    expect(await screen.findByText('2 个模型')).toBeTruthy()
  })
})

describe('LLM 卡', () => {
  it('模型列表渲染为下拉选项，默认选中第一个', async () => {
    renderStatus()
    await screen.findByText('2 个模型')
    const select = screen.getByLabelText('选择测试模型') as HTMLSelectElement
    await waitFor(() => expect(select.value).toBe('kimi-2.6'))
    expect(screen.getByText('kimi-2.6（默认）')).toBeTruthy()
    expect(screen.getByText('glm53')).toBeTruthy()
  })

  it('无可用模型时下拉与「测试连接」均禁用', async () => {
    stubs.fetchLlmModels.mockResolvedValue([])
    renderStatus()
    await screen.findByText('0 个模型')
    const select = screen.getByLabelText('选择测试模型') as HTMLSelectElement
    await waitFor(() => expect(select.disabled).toBe(true))
    expect(screen.getByText('（无可用模型）')).toBeTruthy()
    const btn = screen.getByRole('button', { name: /测试连接/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('模型面失败 → 「网关不可达」', async () => {
    stubs.fetchLlmModels.mockRejectedValue(new Error('gw down'))
    renderStatus()
    expect(await screen.findByText('网关不可达')).toBeTruthy()
  })

  it('点「测试连接」用当前选中模型发起探测，成功走 toast 与卡片文案', async () => {
    stubs.testLlmConnection.mockResolvedValue({
      ok: true,
      model: 'kimi-2.6',
      backend: 'siliconflow',
    })
    renderStatus()
    await screen.findByText('2 个模型')
    fireEvent.click(screen.getByRole('button', { name: /测试连接/ }))
    await waitFor(() => expect(stubs.testLlmConnection).toHaveBeenCalledWith('kimi-2.6'))
    // 成功后 toast + 卡片内结果文案
    await waitFor(() =>
      expect(stubs.toast.success).toHaveBeenCalledWith(
        expect.stringContaining('连接成功'),
      ),
    )
    expect(screen.getByText(/连接成功：kimi-2\.6/)).toBeTruthy()
  })

  it('测试连接返回 ok=false → 卡片展示后端给的 error，不走成功分支', async () => {
    stubs.testLlmConnection.mockResolvedValue({ ok: false, error: '需要管理员权限' })
    renderStatus()
    await screen.findByText('2 个模型')
    fireEvent.click(screen.getByRole('button', { name: /测试连接/ }))
    expect(await screen.findByText('需要管理员权限')).toBeTruthy()
    expect(stubs.toast.error).toHaveBeenCalled()
  })
})

describe('刷新契约', () => {
  it('点「刷新」invalidate 整个 settings 前缀（三卡一起重取）', async () => {
    const { invalidate } = renderStatus()
    await screen.findByText('在线 · 134ms')
    fireEvent.click(screen.getByRole('button', { name: /刷新/ }))
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['settings'] }),
    )
  })
})
