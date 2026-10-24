// @vitest-environment jsdom
/**
 * SessionSidebar 测试（jsdom）。
 *
 * 覆盖：加载中/空态、会话行渲染与当前项标记、切换会话、行内重命名
 * （Enter 提交 / Esc 取消 / 空标题不提交）、删除确认流的「相邻会话顺位接管」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  renameSession: vi.fn(),
  getUsageSummary: vi.fn(),
}))
const storeMock = vi.hoisted(() => ({
  sessionId: 's-2' as string | null,
  context: null as { origin: 'case' | 'contract'; refId: number; title: string } | null,
  switchSession: vi.fn(),
}))
const switchSpy = vi.hoisted(() => vi.fn())

vi.mock('../api', () => apiMock)
vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))

import { SessionSidebar } from './SessionSidebar'

function session(id: string, title = '') {
  return { session_id: id, title, status: 'active', llm_model: '', created_at: '', updated_at: '2026-10-20T10:00:00' }
}

function renderSidebar(variant: 'rail' | 'overlay' = 'rail') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<SessionSidebar variant={variant} onClose={vi.fn()} />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  storeMock.sessionId = 's-2'
  storeMock.context = null
  storeMock.switchSession = switchSpy
  apiMock.listSessions.mockResolvedValue([session('s-1', '第一'), session('s-2', '第二'), session('s-3', '')])
  apiMock.deleteSession.mockResolvedValue({ deleted: 1 })
  apiMock.renameSession.mockResolvedValue(session('s-1', '改名'))
  apiMock.getUsageSummary.mockResolvedValue({
    runs: 42,
    ok_runs: 40,
    error_runs: 1,
    cancelled_runs: 1,
    input_tokens: 120000,
    output_tokens: 8000,
    total_tokens: 128000,
    tool_calls: 66,
    avg_duration_ms: 4200,
    error_rate: 0.024,
  })
})

describe('SessionSidebar：列表态', () => {
  it('加载中显示提示', () => {
    apiMock.listSessions.mockReturnValue(new Promise(() => {}))
    const { container } = renderSidebar()
    expect(within(container).getByText('加载中…')).toBeTruthy()
    container.remove()
  })

  it('空列表显示暂无历史会话', async () => {
    apiMock.listSessions.mockResolvedValue([])
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('暂无历史会话')).toBeTruthy())
    container.remove()
  })

  it('渲染会话标题，未命名显示占位文案', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())
    expect(within(container).getByText('未命名对话')).toBeTruthy()
    container.remove()
  })

  it('当前会话标记 aria-current，其余不标记', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第二')).toBeTruthy())

    const rows = container.querySelectorAll('[role="button"]')
    const marked = Array.from(rows).filter((r) => r.getAttribute('aria-current') === 'true')
    expect(marked).toHaveLength(1)
    expect(marked[0]!.textContent).toContain('第二')
    container.remove()
  })
})

describe('SessionSidebar：切换', () => {
  it('点非当前会话触发 switchSession', async () => {
    const { container } = renderSidebar()
    const row = await waitFor(() => within(container).getByText('第一').closest('[role="button"]') as HTMLElement)
    fireEvent.click(row)
    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith('s-1'))
    container.remove()
  })

  it('点当前会话不重复切换', async () => {
    const { container } = renderSidebar()
    const row = await waitFor(() => within(container).getByText('第二').closest('[role="button"]') as HTMLElement)
    fireEvent.click(row)
    expect(switchSpy).not.toHaveBeenCalled()
    container.remove()
  })

  it('键盘 Enter / Space 也能切换（W-P1 回归）', async () => {
    const { container } = renderSidebar()
    const row = await waitFor(() => within(container).getByText('第一').closest('[role="button"]') as HTMLElement)

    fireEvent.keyDown(row, { key: 'Enter' })
    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith('s-1'))

    switchSpy.mockClear()
    fireEvent.keyDown(row, { key: ' ' })
    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith('s-1'))
    container.remove()
  })
})

describe('SessionSidebar：行内重命名', () => {
  it('Enter 提交新标题', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())

    fireEvent.click(within(container).getAllByRole('button', { name: '重命名' })[0]!)
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '新标题' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(apiMock.renameSession).toHaveBeenCalledWith('s-1', '新标题'))
    container.remove()
  })

  it('标题未变时不发请求', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())

    fireEvent.click(within(container).getAllByRole('button', { name: '重命名' })[0]!)
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.keyDown(input, { key: 'Enter' })

    await new Promise((r) => setTimeout(r, 50))
    expect(apiMock.renameSession).not.toHaveBeenCalled()
    container.remove()
  })

  it('Esc 退出编辑且不提交', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())

    fireEvent.click(within(container).getAllByRole('button', { name: '重命名' })[0]!)
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '改了但不保存' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())
    expect(apiMock.renameSession).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('SessionSidebar：删除与顺位接管', () => {
  it('点删除弹确认框，取消不删', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())

    fireEvent.click(within(container).getAllByRole('button', { name: '删除对话' })[0]!)
    await waitFor(() => expect(screen.getByText('删除该对话？')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(apiMock.deleteSession).not.toHaveBeenCalled()
    container.remove()
  })

  it('确认删除后调用接口', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第一')).toBeTruthy())

    fireEvent.click(within(container).getAllByRole('button', { name: '删除对话' })[0]!)
    await waitFor(() => expect(screen.getByText('删除该对话？')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => expect(apiMock.deleteSession).toHaveBeenCalledWith('s-1'))
    container.remove()
  })

  it('删除当前会话：相邻会话顺位接管（先下）', async () => {
    // 当前是 s-2，列表 s-1/s-2/s-3 → 应切到 s-3
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('第二')).toBeTruthy())

    const delButtons = within(container).getAllByRole('button', { name: '删除对话' })
    fireEvent.click(delButtons[1]!)
    await waitFor(() => expect(screen.getByText('删除该对话？')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith('s-3'))
    container.remove()
  })

  it('删除末位会话：上一位接管（先下后上）', async () => {
    // s-3 是最后一项，index+1 不存在 → 取 index-1 即 s-2
    storeMock.sessionId = 's-3'
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('未命名对话')).toBeTruthy())

    const delButtons = within(container).getAllByRole('button', { name: '删除对话' })
    fireEvent.click(delButtons[2]!)
    await waitFor(() => expect(screen.getByText('删除该对话？')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith('s-2'))
    container.remove()
  })

  it('删除唯一会话：回落到空白新对话', async () => {
    apiMock.listSessions.mockResolvedValue([session('s-only', '唯一')])
    storeMock.sessionId = 's-only'
    const { container } = renderSidebar()
    await waitFor(() => expect(within(container).getByText('唯一')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: '删除对话' }))
    await waitFor(() => expect(screen.getByText('删除该对话？')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => expect(switchSpy).toHaveBeenCalledWith(null))
    container.remove()
  })
})

describe('SessionSidebar：业务范围与用量（P1-1 / P1-2）', () => {
  it('始终拉全量列表并带 limit（不按 scope 过滤：进项目也要能看到别的项目）', async () => {
    storeMock.context = { origin: 'contract', refId: 386, title: '张三委托' }
    const { container } = renderSidebar()
    await waitFor(() => expect(apiMock.listSessions).toHaveBeenCalledWith(100))
    // 第二参数（scope）必须缺省——按 scope 查会让别的项目分组从侧栏消失
    expect(apiMock.listSessions.mock.calls[0]).toHaveLength(1)
    container.remove()
  })

  it('项目模式空列表：空态提示带业务名', async () => {
    storeMock.context = { origin: 'contract', refId: 386, title: '张三委托' }
    apiMock.listSessions.mockResolvedValue([])
    const { container } = renderSidebar()
    await waitFor(() => expect(container.textContent).toContain('「张三委托」还没有 AI 会话'))
    container.remove()
  })

  it('按项目分组：多项目各成一个文件夹，当前项目组头高亮并展开', async () => {
    storeMock.context = { origin: 'contract', refId: 386, title: '张三委托' }
    apiMock.listSessions.mockResolvedValue([
      { ...session('a-1', '本项目会话'), origin: 'contract', contract_id: 386, scope_name: '张三委托' },
      { ...session('b-1', '别的项目会话'), origin: 'contract', contract_id: 999, scope_name: '李四委托' },
    ])
    const { container } = renderSidebar()
    // 两个项目都在（进项目后别的项目不消失）
    await waitFor(() => expect(container.textContent).toContain('张三委托'))
    expect(container.textContent).toContain('李四委托')
    // 当前项目组头标 aria-current，且组内会话可见
    const currentHead = container.querySelector('[aria-current="true"][aria-expanded]')
    expect(currentHead?.textContent).toContain('张三委托')
    expect(container.textContent).toContain('本项目会话')
    container.remove()
  })

  it('非当前项目默认收起，点组头可展开', async () => {
    storeMock.context = { origin: 'contract', refId: 386, title: '张三委托' }
    apiMock.listSessions.mockResolvedValue([
      { ...session('a-1', '本项目会话'), origin: 'contract', contract_id: 386, scope_name: '张三委托', updated_at: '2026-10-20T10:00:00' },
      { ...session('b-1', '别的项目会话'), origin: 'contract', contract_id: 999, scope_name: '李四委托', updated_at: '2026-10-19T10:00:00' },
    ])
    const { container } = renderSidebar()
    await waitFor(() => expect(container.textContent).toContain('李四委托'))
    // 非当前项目会话默认收起
    expect(container.textContent).not.toContain('别的项目会话')
    const otherHead = Array.from(container.querySelectorAll('[aria-expanded]')).find((b) =>
      (b.textContent ?? '').includes('李四委托'),
    ) as HTMLElement
    fireEvent.click(otherHead)
    await waitFor(() => expect(container.textContent).toContain('别的项目会话'))
    container.remove()
  })

  it('底部显示近 30 天用量摘要（轮次 / tokens / 失败率）', async () => {
    const { container } = renderSidebar()
    await waitFor(() => expect(apiMock.getUsageSummary).toHaveBeenCalledWith(30))
    await waitFor(() => {
      expect(container.textContent).toContain('近 30 天 42 轮')
      expect(container.textContent).toContain('128.0k tokens')
      expect(container.textContent).toContain('失败 2.4%')
    })
    container.remove()
  })

  it('零用量时用量行不渲染', async () => {
    apiMock.getUsageSummary.mockResolvedValue({
      runs: 0, ok_runs: 0, error_runs: 0, cancelled_runs: 0,
      input_tokens: 0, output_tokens: 0, total_tokens: 0, tool_calls: 0,
      avg_duration_ms: 0, error_rate: 0,
    })
    const { container } = renderSidebar()
    await waitFor(() => expect(apiMock.getUsageSummary).toHaveBeenCalled())
    // 等 listSessions 渲染完成后确认无用量行
    await waitFor(() => expect(within(container).getByText('新对话')).toBeTruthy())
    expect(container.textContent).not.toContain('近 30 天')
    container.remove()
  })
})
