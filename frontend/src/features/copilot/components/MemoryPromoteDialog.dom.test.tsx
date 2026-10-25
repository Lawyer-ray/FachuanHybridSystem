// @vitest-environment jsdom
/**
 * 策展提升对话框测试（jsdom）。
 *
 * 这里守的是**三道闸门在前端也要成立**（后端有同样的校验，前端做前置拦截是
 * 为了让律师一次填对，而不是提交后猜哪里被拒）：
 *
 * 1. 未选来源 → 不能提交；
 * 2. 原样提升（与来源原文相同）→ 不能提交；
 * 3. 含敏感信息 → 不能提交；
 * 4. 律所层只能选「惯例/偏好」，不能选「事实」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listMemories: vi.fn(),
  createMemory: vi.fn(),
  forgetMemory: vi.fn(),
  restoreMemory: vi.fn(),
  confirmMemories: vi.fn(),
  fetchMemoryScopes: vi.fn(),
  fetchPromoteCandidates: vi.fn(),
  promoteMemory: vi.fn(),
}))

vi.mock('../memory-api', () => apiMock)

import { MemoryPromoteDialog } from './MemoryPromoteDialog'

const TEAM_SCOPES = {
  law_firm: { id: 1, can_curate: true },
  teams: [{ id: 7, name: '劳动争议组', can_curate: true }],
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    id: 'c-1',
    kind: 'procedure',
    content: '回复法院函件不要超过 800 字',
    hit_count: 4,
    from_lawyer: '李律师',
    pii_risk: [],
    ...overrides,
  }
}

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<MemoryPromoteDialog open onOpenChange={vi.fn()} scopes={TEAM_SCOPES} onPromoted={vi.fn()} />, {
    wrapper: wrap,
  })
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: '提炼' }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.fetchPromoteCandidates.mockResolvedValue([candidate()])
  apiMock.promoteMemory.mockResolvedValue({ id: 'new' })
})

describe('MemoryPromoteDialog', () => {
  it('渲染候选池（含来源律师与使用次数）', async () => {
    renderDialog()
    expect(await screen.findByText('回复法院函件不要超过 800 字')).toBeTruthy()
    expect(screen.getByText('李律师')).toBeTruthy()
    expect(screen.getByText(/用过 4 次/)).toBeTruthy()
  })

  it('未选来源不能提交', async () => {
    renderDialog()
    await screen.findByText('回复法院函件不要超过 800 字')
    expect(submitButton().disabled).toBe(true)
  })

  it('原样提升被拦住 —— 必须改写', async () => {
    renderDialog()
    const checkbox = (await screen.findByRole('checkbox')) as HTMLInputElement
    fireEvent.click(checkbox)

    const textarea = screen.getByLabelText('改写后的规则') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '回复法院函件不要超过 800 字' } })

    expect(await screen.findByText(/与来源原文相同/)).toBeTruthy()
    expect(submitButton().disabled).toBe(true)
    expect(apiMock.promoteMemory).not.toHaveBeenCalled()
  })

  it('含敏感信息被拦住', async () => {
    renderDialog()
    fireEvent.click(await screen.findByRole('checkbox'))

    const textarea = screen.getByLabelText('改写后的规则') as HTMLTextAreaElement
    // PII 检测闸门自身的测试输入
    fireEvent.change(textarea, { target: { value: '客户手机 13800138000 的案子都可分期' } }) // privacy-allow

    expect(await screen.findByText(/含 手机号/)).toBeTruthy()
    expect(submitButton().disabled).toBe(true)
  })

  it('改写后可以提交，并带上选了哪些来源', async () => {
    renderDialog()
    fireEvent.click(await screen.findByRole('checkbox'))

    const textarea = screen.getByLabelText('改写后的规则') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '回复法院函件控制在 800 字以内' } })

    await waitFor(() => expect(submitButton().disabled).toBe(false))
    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(apiMock.promoteMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceIds: ['c-1'],
          content: '回复法院函件控制在 800 字以内',
          scope: 'team',
          teamId: 7,
        }),
      ),
    )
  })

  it('含敏感模式的候选标出「需脱敏」', async () => {
    apiMock.fetchPromoteCandidates.mockResolvedValue([candidate({ pii_risk: ['手机号'] })])
    renderDialog()
    expect(await screen.findByText('需脱敏')).toBeTruthy()
  })

  it('律所层不提供「事实」类型 —— 具体事实不属于全所规范', async () => {
    renderDialog()
    await screen.findByText('回复法院函件不要超过 800 字')

    // 默认目标团队层：事实可选
    const kindSelect = screen.getByLabelText('规则类型') as HTMLSelectElement
    expect(Array.from(kindSelect.options).map((o) => o.value)).toContain('fact')

    // 切到律所层后事实被移除
    const targetSelect = screen.getByLabelText('提升目标') as HTMLSelectElement
    fireEvent.change(targetSelect, { target: { value: 'law_firm' } })

    await waitFor(() => {
      const options = Array.from((screen.getByLabelText('规则类型') as HTMLSelectElement).options).map((o) => o.value)
      expect(options).not.toContain('fact')
    })
  })
})
