// @vitest-environment jsdom
/**
 * CaseBindingSection 测试（jsdom）。
 *
 * 第 1 步「案件绑定」的分支：
 * - 已绑定（含管线模式）→ 只读 chip，文案区分来源
 * - 未绑定 → 推荐卡片（最多 3 条，超出提示总数）+ 搜索
 * - 推荐唯一高分时自动预选一次，之后用户手动改动不再被覆盖
 * - 选中后点绑定：成功提示 + 清空 + 回调；失败提示且不回调
 * - 搜索至少 2 字符才查
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  bindTask: vi.fn(),
  searchCasesForBinding: vi.fn(async (): Promise<CaseSearchItem[]> => []),
}))
const domainMock = vi.hoisted(() => ({ pickAutoRecommendation: vi.fn() }))

vi.mock('../api', () => apiMock)
vi.mock('../domain', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../domain')>()
  return { ...actual, pickAutoRecommendation: domainMock.pickAutoRecommendation }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { CaseBindingSection } from './CaseBindingSection'
import type { CaseSearchItem } from '../types'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function task(over: Record<string, unknown> = {}) {
  return {
    task_id: 9,
    binding: null,
    binding_mode: null,
    recommendations: [],
    ...over,
  } as never
}

function reco(id: number, name: string, score = 90) {
  return { case_id: id, case_name: name, case_numbers: [`（20XX）${id}号`], score, reasons: ['同当事人'] }
}

function renderSection(t: unknown, onBound = vi.fn()) {
  const utils = render(wrap(<CaseBindingSection task={t as never} onBound={onBound} />))
  return { ...utils, onBound }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.bindTask.mockResolvedValue({})
  apiMock.searchCasesForBinding.mockResolvedValue([])
  domainMock.pickAutoRecommendation.mockReturnValue(null)
})

describe('CaseBindingSection：已绑定态', () => {
  it('普通绑定显示「已绑定案件：」', () => {
    const { container } = renderSection(
      task({ binding: { success: true, case_name: '张三诉李四' }, binding_mode: 'manual' }),
    )
    expect(container.textContent).toContain('已绑定案件：张三诉李四')
    container.remove()
  })

  it('管线模式显示「已由法院短信绑定：」', () => {
    const { container } = renderSection(
      task({ binding: { success: true, case_name: '王五案' }, binding_mode: 'pipeline' }),
    )
    expect(container.textContent).toContain('已由法院短信绑定：王五案')
    container.remove()
  })

  it('binding.success 为假时仍视为未绑定', () => {
    const { container } = renderSection(task({ binding: { success: false, case_name: 'X' } }))
    expect(container.textContent).not.toContain('已绑定案件')
    container.remove()
  })

  it('有 case_name 但 success 缺失时也不算已绑定', () => {
    const { container } = renderSection(task({ binding: { case_name: 'X' } }))
    expect(container.textContent).not.toContain('已绑定案件')
    container.remove()
  })
})

describe('CaseBindingSection：推荐卡片', () => {
  it('渲染推荐案件与相关度', () => {
    const { container } = renderSection(task({ recommendations: [reco(1, '张三诉李四'), reco(2, '王五案', 80)] }))
    expect(container.textContent).toContain('推荐案件')
    expect(within(container).getByText('张三诉李四')).toBeTruthy()
    expect(container.textContent).toContain('相关度 90')
    container.remove()
  })

  it('最多渲染 3 条，超出提示总数', () => {
    const recs = [reco(1, 'A'), reco(2, 'B'), reco(3, 'C'), reco(4, 'D'), reco(5, 'E')]
    const { container } = renderSection(task({ recommendations: recs }))
    expect(within(container).getByText('A')).toBeTruthy()
    expect(within(container).getByText('C')).toBeTruthy()
    expect(within(container).queryByText('D')).toBeNull()
    expect(container.textContent).toContain('共 5 个推荐')
    container.remove()
  })

  it('自动预选时显示「已按相关度预选」标记', async () => {
    domainMock.pickAutoRecommendation.mockReturnValue(reco(1, '张三诉李四'))
    const { container } = renderSection(task({ recommendations: [reco(1, '张三诉李四')] }))
    await waitFor(() => expect(container.textContent).toContain('已按相关度预选'))
    container.remove()
  })

  it('点推荐卡片选中该案', async () => {
    const { container, onBound } = renderSection(task({ recommendations: [reco(1, '张三诉李四')] }))
    fireEvent.click(within(container).getByText('张三诉李四'))

    const bindBtn = within(container).getByRole('button', { name: /绑定/ })
    fireEvent.click(bindBtn)
    await waitFor(() => expect(apiMock.bindTask).toHaveBeenCalledWith(9, 1))
    expect(onBound).toHaveBeenCalled()
    container.remove()
  })
})

describe('CaseBindingSection：绑定提交', () => {
  it('成功后提示、清空选择并回调', async () => {
    const { container, onBound } = renderSection(task({ recommendations: [reco(1, '张三诉李四')] }))
    fireEvent.click(within(container).getByText('张三诉李四'))
    fireEvent.click(within(container).getByRole('button', { name: /绑定/ }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已绑定案件：张三诉李四'))
    expect(onBound).toHaveBeenCalled()
    container.remove()
  })

  it('失败时提示且不回调', async () => {
    apiMock.bindTask.mockRejectedValue(new Error('案件已被删除'))
    const { container, onBound } = renderSection(task({ recommendations: [reco(1, '张三诉李四')] }))
    fireEvent.click(within(container).getByText('张三诉李四'))
    fireEvent.click(within(container).getByRole('button', { name: /绑定/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onBound).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('CaseBindingSection：搜索', () => {
  it('输入至少 2 字符才发请求', async () => {
    const { container } = renderSection(task())
    const input = container.querySelector('input') as HTMLInputElement

    fireEvent.change(input, { target: { value: '张' } })
    await new Promise((r) => setTimeout(r, 400))
    expect(apiMock.searchCasesForBinding).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '张三' } })
    await waitFor(() => expect(apiMock.searchCasesForBinding).toHaveBeenCalled(), { timeout: 3000 })
    container.remove()
  })

  it('搜索结果可点选后绑定', async () => {
    apiMock.searchCasesForBinding.mockResolvedValue([
      { id: 77, name: '搜到的案件', case_numbers: ['（20XX）77号'] },
    ])
    const { container } = renderSection(task())
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '搜到' } })

    await waitFor(() => expect(screen.getByText('搜到的案件')).toBeTruthy(), { timeout: 3000 })
    fireEvent.click(screen.getByText('搜到的案件'))
    fireEvent.click(within(container).getByRole('button', { name: /绑定/ }))

    await waitFor(() => expect(apiMock.bindTask).toHaveBeenCalledWith(9, 77))
    container.remove()
  })
})
