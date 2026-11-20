// @vitest-environment jsdom
/**
 * 「AI 上下文」抽屉测试（jsdom）。
 *
 * 覆盖四件会直接误导律师的事：
 * 1. **分组顺序**：已确认的事实在前、同事的判断在后。混在一起时，未确认的判断会被
 *    当成项目事实使用——这正是这个面板要解决的问题；
 * 2. **来源与锚点标记**：确认人 / 创建时间、本案 / 项目，缺一条律师就判断不了这条
 *    笔记管到哪、是谁说的；
 * 3. **空态给出下一步**：告诉律师去助手点书签，而不是留一片空白；
 * 4. **请求带 contract_id**：不带就退化成全量记忆，把别的项目的笔记搬到本项目下。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  listProjectNotes: vi.fn(),
}))

import { listProjectNotes, type ProjectNote } from '../../api'

import { ProjectMemoryDrawer } from './ProjectMemoryDrawer'

const EMPTY_COPY =
  '本项目还没有 AI 笔记。在 AI 助手里点回答下方的书签，就能把结论存到这里，同团队可见。'

function note(overrides: Partial<ProjectNote> = {}): ProjectNote {
  return {
    id: 'm-1',
    content: '对方已同意分三期付清',
    confirmed_at: '',
    confirmed_by: '',
    case_id: null,
    created_at: '2026-10-01T09:00:00',
    ...overrides,
  }
}

function renderDrawer(contractId = 42) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<ProjectMemoryDrawer open onOpenChange={vi.fn()} contractId={contractId} />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listProjectNotes).mockResolvedValue([])
})

describe('ProjectMemoryDrawer', () => {
  it('分组顺序固定：已确认的事实在前，同事的判断在后（即使后端把判断排在前面）', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([
      note({ id: 'j-1', content: '可能构成表见代理' }),
      note({ id: 'f-1', content: '对方已同意分三期付清', confirmed_at: '2026-10-02T10:00:00', confirmed_by: '王律师' }),
    ])
    renderDrawer()

    const facts = await screen.findByRole('region', { name: '已确认的事实' })
    const judgments = screen.getByRole('region', { name: '同事的判断' })
    expect(within(facts).getByText('对方已同意分三期付清')).toBeTruthy()
    expect(within(facts).queryByText('可能构成表见代理')).toBeNull()
    expect(within(judgments).getByText('可能构成表见代理')).toBeTruthy()

    const headings = screen.getAllByRole('heading', { level: 3 })
    expect(headings[0]?.textContent).toContain('已确认的事实')
    expect(headings[1]?.textContent).toContain('同事的判断')
  })

  it('已确认显示「<确认人> 确认」，未确认显示创建时间；锚点标记区分本案 / 项目', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([
      note({ id: 'f-1', confirmed_at: '2026-10-02T10:00:00', confirmed_by: '王律师', case_id: 7 }),
      note({ id: 'j-1', content: '可能构成表见代理', created_at: '2026-10-03T18:30:00', case_id: null }),
    ])
    renderDrawer()

    const facts = await screen.findByRole('region', { name: '已确认的事实' })
    expect(within(facts).getByText('王律师 确认')).toBeTruthy()
    expect(within(facts).getByText('本案')).toBeTruthy()

    const judgments = screen.getByRole('region', { name: '同事的判断' })
    expect(within(judgments).getByText('2026年10月3日')).toBeTruthy()
    expect(within(judgments).getByText('项目')).toBeTruthy()
  })

  it('确认人姓名缺失时退回「已确认」，不渲染出半个「 确认」', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([
      note({ id: 'f-1', confirmed_at: '2026-10-02T10:00:00', confirmed_by: '' }),
    ])
    renderDrawer()

    const facts = await screen.findByRole('region', { name: '已确认的事实' })
    // 整段文本恰好是「已确认」；若代码退化成拼接空名字，这里会变成「 确认」而失败
    expect(within(facts).getByText('已确认')).toBeTruthy()
  })

  it('只有同事的判断时，事实组仍占位计数 0（律师一眼看出没人确认过）', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([note({ id: 'j-1', content: '可能构成表见代理' })])
    renderDrawer()

    const facts = await screen.findByRole('region', { name: '已确认的事实' })
    expect(within(facts).getByRole('heading', { level: 3 }).textContent).toContain('0')
    expect(within(facts).queryByText('可能构成表见代理')).toBeNull()
    expect(within(screen.getByRole('region', { name: '同事的判断' })).getByText('可能构成表见代理')).toBeTruthy()
  })

  it('空态说明笔记从哪来：助手回答下方的书签', async () => {
    renderDrawer()
    expect(await screen.findByText(EMPTY_COPY)).toBeTruthy()
  })

  it('请求带上 contract_id（不带会读到别的项目的笔记）', async () => {
    renderDrawer(88)
    await waitFor(() => expect(listProjectNotes).toHaveBeenCalledWith(88))
  })

  it('失败给人话 + 重试入口，不静默留白', async () => {
    vi.mocked(listProjectNotes).mockRejectedValueOnce(new Error('请求超时，请稍后重试'))
    renderDrawer()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('请求超时，请稍后重试')

    fireEvent.click(within(alert).getByRole('button', { name: '重试' }))
    await waitFor(() => expect(listProjectNotes).toHaveBeenCalledTimes(2))
  })
})
