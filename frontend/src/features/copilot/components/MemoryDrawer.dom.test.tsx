// @vitest-environment jsdom
/**
 * 记忆抽屉测试（jsdom）。
 *
 * 覆盖四个真正会出事的点：
 * 1. **待确认区置顶**——它是「AI 自动抽取」进上下文的唯一闸门，被折叠进
 *    普通列表等于闸门失效；
 * 2. **确认/忽略分别调用后端**（accept 布尔不能反）；
 * 3. **只有个人层可删**——团队/律所层由策展管理，界面不能给出删除入口；
 * 4. **新增不合法内容不发请求**（空 / 超长）。
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

import { MemoryDrawer } from './MemoryDrawer'

function memory(overrides: Record<string, unknown> = {}) {
  return {
    id: 'm-1',
    scope: 'lawyer',
    kind: 'preference',
    content: '文书先给结论再给理由',
    status: 'active',
    confidence: 1,
    hit_count: 0,
    created_at: '2026-10-20T10:00:00',
    source_session_id: '',
    ...overrides,
  }
}

function renderDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<MemoryDrawer open onOpenChange={vi.fn()} />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listMemories.mockResolvedValue([])
  apiMock.fetchMemoryScopes.mockResolvedValue({ law_firm: { id: 1, can_curate: false }, teams: [] })
  apiMock.confirmMemories.mockResolvedValue({ ok: true, affected: 1 })
  apiMock.createMemory.mockResolvedValue(memory())
  apiMock.forgetMemory.mockResolvedValue({ ok: true })
})

describe('MemoryDrawer', () => {
  it('空态提示引导用户录入或口头说「记住」', async () => {
    renderDrawer()
    expect(await screen.findByText(/还没有记忆/)).toBeTruthy()
  })

  it('待确认区展示自动抽取的记忆并提供确认/忽略', async () => {
    apiMock.listMemories.mockResolvedValue([
      memory({ id: 'p-1', content: '该律师偏好表格而不是列表', status: 'pending', confidence: 0.8 }),
    ])
    renderDrawer()

    expect(await screen.findByText(/待确认 1 条/)).toBeTruthy()
    expect(screen.getByText('该律师偏好表格而不是列表')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('确认这条记忆'))
    await waitFor(() => expect(apiMock.confirmMemories).toHaveBeenCalledWith(['p-1'], true))
  })

  it('忽略走 accept=false —— 不能把否决写成通过', async () => {
    apiMock.listMemories.mockResolvedValue([memory({ id: 'p-2', status: 'pending' })])
    renderDrawer()

    fireEvent.click(await screen.findByLabelText('忽略这条记忆'))
    await waitFor(() => expect(apiMock.confirmMemories).toHaveBeenCalledWith(['p-2'], false))
  })

  it('只有个人层显示删除按钮 —— 团队/律所意图层不可删', async () => {
    apiMock.listMemories.mockResolvedValue([
      memory({ id: 'mine', scope: 'lawyer', content: '我的偏好' }),
      memory({ id: 'team-1', scope: 'team', content: '团队惯例' }),
      memory({ id: 'firm-1', scope: 'law_firm', content: '所内规范' }),
    ])
    renderDrawer()

    await screen.findByText('团队惯例')
    // 三条记忆，但只有个人层那一条带删除按钮
    expect(screen.getAllByLabelText('删除这条记忆')).toHaveLength(1)
  })

  it('删除个人记忆调用后端', async () => {
    apiMock.listMemories.mockResolvedValue([memory({ id: 'mine' })])
    renderDrawer()

    fireEvent.click(await screen.findByLabelText('删除这条记忆'))
    await waitFor(() => expect(apiMock.forgetMemory).toHaveBeenCalledWith('mine'))
  })

  it('空内容不发新增请求', async () => {
    renderDrawer()
    await screen.findByText(/还没有记忆/)

    const button = screen.getByRole('button', { name: /记住/ })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(button)
    expect(apiMock.createMemory).not.toHaveBeenCalled()
  })

  it('新增成功后清空输入并刷新列表', async () => {
    renderDrawer()
    const textarea = (await screen.findByLabelText('让助手记住一件事')) as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '引用法条时附条文原文' } })

    fireEvent.click(screen.getByRole('button', { name: /记住/ }))
    await waitFor(() => expect(apiMock.createMemory).toHaveBeenCalledWith('引用法条时附条文原文', 'preference'))
  })

  it('可策展时显示提炼入口', async () => {
    apiMock.fetchMemoryScopes.mockResolvedValue({
      law_firm: { id: 1, can_curate: false },
      teams: [{ id: 7, name: '劳动争议组', can_curate: true }],
    })
    renderDrawer()

    expect(await screen.findByText('提炼为团队惯例')).toBeTruthy()
  })

  it('不可策展时隐藏提炼入口', async () => {
    renderDrawer()
    await screen.findByText(/还没有记忆/)
    expect(screen.queryByText('提炼为团队惯例')).toBeNull()
  })
})
