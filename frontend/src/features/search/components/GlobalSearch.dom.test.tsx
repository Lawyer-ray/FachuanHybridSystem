// @vitest-environment jsdom
/**
 * GlobalSearch（⌘K 命令面板）组件渲染单测（jsdom + 真实 timers）。
 *
 * mock 只打 api 层（../api 的 runSearch；CATEGORY_ORDER 等常量保留真实实现）。
 * 覆盖：开关挂载、输入防抖 250ms 触发查询（trim 后上送）、结果按类别分组渲染、
 * 空结果兜底、筛选标签前端过滤、键盘 ↑↓/Enter 选中跳转（inbox 跳 /material-prep/:id、
 * 未建页类别回调 onPickUnavailable）、查询失败分支、关闭再打开状态清零。
 * 防抖用真实短等待断言（fake timers 与 RTL waitFor 的探测不兼容，参照既有用例先例）。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, runSearch: vi.fn() }
})

import { runSearch } from '../api'

import { GlobalSearch } from './GlobalSearch'

const runSearchMock = vi.mocked(runSearch)

const onOpenChange = vi.fn()
const onPickUnavailable = vi.fn()

// 不显式标注 Hit：Hit 正在从手写类型迁移到 api-schema 生成物引用，
// 工厂返回结构形状（category/id/title/subtitle）对两种类型态都可结构兼容。
function makeHit(category: string, id: number, title: string, subtitle = '') {
  return { category, id, title, subtitle }
}

function setupUi(open = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <GlobalSearch open={open} onOpenChange={onOpenChange} onPickUnavailable={onPickUnavailable} />
        <Routes>
          <Route path="/material-prep/:id" element={<div>material-reader-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const input = () => screen.getByPlaceholderText('搜案件 / 客户 / 合同 / 收件箱 / 法院短信 / 联系人')

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

beforeEach(() => {
  vi.clearAllMocks()
  runSearchMock.mockResolvedValue([])
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('GlobalSearch 挂载与引导', () => {
  it('open=false：面板不渲染，也不发请求', () => {
    setupUi(false)
    expect(screen.queryByPlaceholderText(/搜案件/)).toBeNull()
    expect(runSearch).not.toHaveBeenCalled()
  })

  it('打开且无关键词：展示引导文案，停顿后仍不发请求', async () => {
    setupUi(true)
    expect(screen.getByText('输入关键词开始搜索')).toBeTruthy()
    await sleep(320)
    expect(runSearch).not.toHaveBeenCalled()
  })

  it('关闭再打开：上次输入被清空，回到引导态（防抖窗口后）', async () => {
    runSearchMock.mockResolvedValue([makeHit('cases', 1, '王五案')])
    const { rerender } = setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await waitFor(() => expect(runSearch).toHaveBeenCalledWith('王五'))
    expect(await screen.findByText('王五案')).toBeTruthy()

    // 挂起后续查询：重开后旧词的最后一批响应不落进新面板
    runSearchMock.mockReturnValue(new Promise(() => {}))
    const shell = ({ open }: { open: boolean }): ReactNode => (
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <GlobalSearch open={open} onOpenChange={onOpenChange} />
        </MemoryRouter>
      </QueryClientProvider>
    )
    rerender(shell({ open: false }))
    rerender(shell({ open: true }))
    // q 被关闭 effect 清空，debounced 在 250ms 防抖后跟上 → 回到引导态
    await waitFor(() => expect(screen.getByText('输入关键词开始搜索')).toBeTruthy(), { timeout: 2000 })
    expect(screen.queryByText('王五案')).toBeNull()
  })
})

describe('GlobalSearch 防抖查询', () => {
  it('输入停顿 250ms 后才触发查询，且关键词 trim 后上送', async () => {
    setupUi(true)
    fireEvent.change(input(), { target: { value: '  王五  ' } })
    // 防抖窗口内（100ms < 250ms）不重查
    await sleep(100)
    expect(runSearch).not.toHaveBeenCalled()
    await waitFor(() => expect(runSearch).toHaveBeenCalledWith('王五'), { timeout: 2000 })
  })

  it('查询失败：不崩溃，落到空结果兜底文案', async () => {
    runSearchMock.mockRejectedValue(new Error('网络中断'))
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await waitFor(() => expect(runSearch).toHaveBeenCalled())
    expect(await screen.findByText('没有匹配「王五」的结果')).toBeTruthy()
  })
})

describe('GlobalSearch 结果渲染', () => {
  it('结果按类别分组渲染：组标签 + 标题 + 副标题 + 全部计数', async () => {
    runSearchMock.mockResolvedValue([
      makeHit('cases', 1, '王五诉讼案', '(2026)粤01民初1号'),
      makeHit('inbox', 7, '法院专递-王五', '2 个附件'),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    expect(await screen.findByText('王五诉讼案')).toBeTruthy()
    // 组标签是 div；同名筛选标签是 button（own text 同为「案件」），用 selector 区分
    expect(screen.getByText('案件', { selector: 'div' })).toBeTruthy()
    expect(screen.getByText('收件箱', { selector: 'div' })).toBeTruthy()
    expect(screen.getByText('法院专递-王五')).toBeTruthy()
    expect(screen.getByText('(2026)粤01民初1号')).toBeTruthy()
    // 筛选标签的可访问名是「标签+计数」紧拼（如「全部2」），用正则容忍
    expect(screen.getByRole('button', { name: /^全部/ })).toBeTruthy()
  })

  it('无命中：展示空态文案', async () => {
    runSearchMock.mockResolvedValue([])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '不存在' } })
    expect(await screen.findByText('没有匹配「不存在」的结果')).toBeTruthy()
  })

  it('筛选标签是纯前端过滤：点「收件箱」后只留该类别命中', async () => {
    runSearchMock.mockResolvedValue([
      makeHit('cases', 1, '王五诉讼案'),
      makeHit('inbox', 7, '法院专递-王五'),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('王五诉讼案')

    fireEvent.click(screen.getByRole('button', { name: /^收件箱/ }))
    expect(screen.getByText('法院专递-王五')).toBeTruthy()
    expect(screen.queryByText('王五诉讼案')).toBeNull()
  })
})

describe('GlobalSearch 键盘导航与选中', () => {
  it('inbox 命中回车：关闭面板并跳转 /material-prep/:id', async () => {
    runSearchMock.mockResolvedValue([makeHit('inbox', 7, '法院专递-王五')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('法院专递-王五')

    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(await screen.findByText('material-reader-page')).toBeTruthy()
  })

  it('未建页类别回车：回调 onPickUnavailable（传类别展示名）并关闭面板', async () => {
    runSearchMock.mockResolvedValue([makeHit('cases', 1, '王五诉讼案')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('王五诉讼案')
    expect(screen.getByText('未建页')).toBeTruthy()

    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onPickUnavailable).toHaveBeenCalledWith('案件')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByText('material-reader-page')).toBeNull()
  })
})
