// @vitest-environment jsdom
/**
 * 「AI 上下文」抽屉测试（jsdom）。
 *
 * 覆盖会直接误导律师的事：
 * 1. **分组顺序**：已确认的事实在前、同事的判断在后。混在一起时，未确认的判断会被
 *    当成项目事实使用——这正是这个面板要解决的问题；
 * 2. **来源与锚点标记**：确认人 / 创建时间、本案 / 项目，缺一条律师就判断不了这条
 *    笔记管到哪、是谁说的；
 * 3. **空态给出下一步**：告诉律师去助手点书签，而不是留一片空白；
 * 4. **请求带 contract_id**：不带就退化成全量记忆，把别的项目的笔记搬到本项目下；
 * 5. **确认入口**：只有未确认的判断能点；改写才带 content；失败不关弹窗；
 * 6. **分页**：加载更多按 50 步进、追加而不是替换；末页给计数；失败可原地重试。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  listProjectNotes: vi.fn(),
  confirmProjectNote: vi.fn(),
}))

import { toast } from 'sonner'

import { confirmProjectNote, listProjectNotes, type ProjectNote } from '../../api'

import { ProjectMemoryDrawer } from './ProjectMemoryDrawer'

const EMPTY_COPY =
  '本项目还没有 AI 笔记。在 AI 助手里点回答下方的书签，就能把结论存到这里，同团队可见。'

/** 「同事的判断」行上的确认入口（aria-label 是它的可访问名，测试按它定位） */
const CONFIRM_ROW = '确认这条判断为项目事实'

/** 翻页 / 确认后重取都要跨一次 react-query 往返；并行会话把机器占满时，默认 1s 不够 */
const ROUND_TRIP = { timeout: 3000 }

function note(overrides: Partial<ProjectNote> = {}): ProjectNote {
  return {
    id: 'm-1',
    content: '对方已同意分三期付清',
    confirmed_at: '',
    confirmed_by: '',
    case_id: null,
    created_at: '2026-10-01T09:00:00',
    is_superseded: false,
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

/** 确认弹窗的根节点：抽屉本身也是 role=dialog，只能用弹窗内独有的输入框反查 */
async function findConfirmDialog() {
  const textarea = await screen.findByRole('textbox', { name: '确认的内容' })
  return { dialog: textarea.closest('[role="dialog"]') as HTMLElement, textarea: textarea as HTMLTextAreaElement }
}

beforeEach(() => {
  // reset 而不是 clear：一次性的 mockResolvedValueOnce 队列不能漏到下一个用例里
  vi.resetAllMocks()
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
    await waitFor(() => expect(listProjectNotes).toHaveBeenCalledWith(88, { offset: 0 }))
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

it('被推翻的旧结论单独一组，不与现行结论并排', async () => {
  vi.mocked(listProjectNotes).mockResolvedValue([
    note({ id: 'm-new', content: '新结论：六个月内分期' }),
    note({ id: 'm-old', content: '旧结论：三个月内付清', is_superseded: true }),
  ])
  renderDrawer()
  await screen.findByText('新结论：六个月内分期')

  const supersededGroup = screen.getByRole('region', { name: '已被推翻' })
  expect(within(supersededGroup).getByText('旧结论：三个月内付清')).toBeTruthy()
  // 现行的那组里不能再出现旧结论
  expect(within(screen.getByRole('region', { name: '同事的判断' })).queryByText('旧结论：三个月内付清')).toBeNull()
})

describe('确认入口', () => {
  it('只有「同事的判断」里未确认的行有确认按钮：已确认 / 已被推翻都不给', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([
      note({ id: 'f-1', content: '对方已同意分三期付清', confirmed_at: '2026-10-02T10:00:00', confirmed_by: '王律师' }),
      note({ id: 'j-1', content: '可能构成表见代理' }),
      note({ id: 'old-1', content: '旧结论：三个月内付清', is_superseded: true }),
    ])
    renderDrawer()

    const judgments = await screen.findByRole('region', { name: '同事的判断' })
    expect(within(judgments).getByRole('button', { name: CONFIRM_ROW })).toBeTruthy()
    expect(
      within(screen.getByRole('region', { name: '已确认的事实' })).queryByRole('button', { name: CONFIRM_ROW }),
    ).toBeNull()
    expect(
      within(screen.getByRole('region', { name: '已被推翻' })).queryByRole('button', { name: CONFIRM_ROW }),
    ).toBeNull()
  })

  it('改写后提交：请求带这条 id 与新文本，成功后重拉列表（该条移到事实组）', async () => {
    vi.mocked(listProjectNotes)
      .mockResolvedValueOnce([note({ id: 'j-1', content: '可能构成表见代理' })])
      .mockResolvedValueOnce([
        note({
          id: 'j-1',
          content: '可能构成表见代理',
          confirmed_at: '2026-11-01T10:00:00',
          confirmed_by: '王律师',
        }),
      ])
    vi.mocked(confirmProjectNote).mockResolvedValue(note({ id: 'j-1', confirmed_at: '2026-11-01T10:00:00' }))
    renderDrawer()

    fireEvent.click(
      within(await screen.findByRole('region', { name: '同事的判断' })).getByRole('button', { name: CONFIRM_ROW }),
    )

    const { dialog, textarea } = await findConfirmDialog()
    // 预告后果是这套设计的闸门：确认后同项目所有律师都会当事实用
    expect(dialog.textContent).toContain('确认后本项目的所有律师都会把它当已确认的事实使用')
    // 预填原文，律师只在原文基础上改准
    expect(textarea.value).toBe('可能构成表见代理')
    // 字数按改写后的长度实时显示，上限与后端一致
    expect(dialog.textContent).toContain(`${textarea.value.length}/300`)

    fireEvent.change(textarea, { target: { value: '可能构成表见代理（对方以项目经理名义签约）' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '确认为项目事实' }))

    await waitFor(() =>
      expect(confirmProjectNote).toHaveBeenCalledWith('j-1', '可能构成表见代理（对方以项目经理名义签约）'),
    )
    // 成功后 invalidate → 同一个 query key 重拉第一页
    await waitFor(() => expect(listProjectNotes).toHaveBeenCalledTimes(2), ROUND_TRIP)
    const facts = await screen.findByRole('region', { name: '已确认的事实' })
    await waitFor(() => expect(within(facts).getByText('可能构成表见代理')).toBeTruthy())
    expect(toast.success).toHaveBeenCalled()
  })

  it('没改写就不传 content（后端把「没传」当保留原文）', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([note({ id: 'j-1', content: '可能构成表见代理' })])
    vi.mocked(confirmProjectNote).mockResolvedValue(note({ id: 'j-1', confirmed_at: '2026-11-01T10:00:00' }))
    renderDrawer()

    fireEvent.click(
      within(await screen.findByRole('region', { name: '同事的判断' })).getByRole('button', { name: CONFIRM_ROW }),
    )
    const { dialog } = await findConfirmDialog()
    fireEvent.click(within(dialog).getByRole('button', { name: '确认为项目事实' }))

    await waitFor(() => expect(confirmProjectNote).toHaveBeenCalledWith('j-1', undefined))
  })

  it('确认失败：toast 报错且弹窗不关（改到一半的字不能丢）', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([note({ id: 'j-1', content: '可能构成表见代理' })])
    vi.mocked(confirmProjectNote).mockRejectedValue(new Error('这条笔记已被删除'))
    renderDrawer()

    fireEvent.click(
      within(await screen.findByRole('region', { name: '同事的判断' })).getByRole('button', { name: CONFIRM_ROW }),
    )
    const { dialog, textarea } = await findConfirmDialog()
    const edited = '可能构成表见代理（对方以项目经理名义签约）'
    fireEvent.change(textarea, { target: { value: edited } })
    fireEvent.click(within(dialog).getByRole('button', { name: '确认为项目事实' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect((screen.getByRole('textbox', { name: '确认的内容' }) as HTMLTextAreaElement).value).toBe(edited)
  })
})

describe('分页', () => {
  it('加载更多带 offset=50，结果追加在后面而不是替换', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => note({ id: `p1-${i}`, content: `第 ${i + 1} 条判断` }))
    const page2 = [note({ id: 'p2-1', content: '第 51 条判断' })]
    vi.mocked(listProjectNotes)
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2)
    renderDrawer()

    await screen.findByText('第 1 条判断', {}, ROUND_TRIP)
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    await waitFor(() => expect(listProjectNotes).toHaveBeenLastCalledWith(42, { offset: 50 }), ROUND_TRIP)
    expect(await screen.findByText('第 51 条判断', {}, ROUND_TRIP)).toBeTruthy()
    expect(screen.getByText('第 1 条判断')).toBeTruthy()
    expect(listProjectNotes).toHaveBeenCalledTimes(2)
  })

  it('末页（返回条数 < limit）给总数文案，不再给「加载更多」', async () => {
    vi.mocked(listProjectNotes).mockResolvedValue([note({ id: 'j-1' }), note({ id: 'j-2', content: '另一条判断' })])
    renderDrawer()

    expect(await screen.findByText('已全部加载 2 条')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('加载更多失败：保留已加载内容，原地重试能接着加载', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => note({ id: `p1-${i}`, content: `第 ${i + 1} 条判断` }))
    const page2 = [note({ id: 'p2-1', content: '第 51 条判断' })]
    vi.mocked(listProjectNotes)
      .mockResolvedValueOnce(page1)
      .mockRejectedValueOnce(new Error('请求超时，请稍后重试'))
      .mockResolvedValueOnce(page2)
    renderDrawer()

    await screen.findByText('第 1 条判断', {}, ROUND_TRIP)
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('加载更多失败')
    // 已加载的那 50 条不能被清掉
    expect(screen.getByText('第 1 条判断')).toBeTruthy()

    fireEvent.click(within(alert).getByRole('button', { name: '重试' }))
    expect(await screen.findByText('第 51 条判断', {}, ROUND_TRIP)).toBeTruthy()
  })
})
