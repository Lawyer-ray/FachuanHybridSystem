// @vitest-environment jsdom
/**
 * CaseAssignPicker 测试（jsdom）。
 *
 * 法院短信人工分配案件的选择器：
 * - 挂载即拉在办案件（minLength=0），候选进文档流内（非浮层）
 * - 输入关键词实时检索；选中后输入框显示「案号 · 案件名」并收起候选
 * - 选中态有「重选」按钮（清空选中与关键词）
 * - 主按钮在未选中或 busy 时禁用；busy 时显示「正在指定…」
 * - busy 时输入框禁用
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const searchMock = vi.hoisted(() => vi.fn<(kw: string, opts?: unknown) => Promise<Array<{ id: number; name: string; case_numbers: string[] }>>>(async () => []))
vi.mock('@/features/document-recognition', () => ({
  searchCasesForBinding: (kw: string, opts?: unknown) => searchMock(kw, opts),
}))

import { CaseAssignPicker } from './CaseAssignPicker'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function renderPicker(props: Partial<Parameters<typeof CaseAssignPicker>[0]> = {}) {
  const onAssign = vi.fn(async () => {})
  const utils = render(wrap(<CaseAssignPicker busy={false} onAssign={onAssign} {...props} />))
  return { ...utils, onAssign }
}

function searchInput(): HTMLInputElement {
  return screen.getByPlaceholderText('搜索案号 / 案件名 / 当事人') as HTMLInputElement
}

function submitButton(): HTMLButtonElement {
  return Array.from(document.querySelectorAll('button')).find((b) =>
    /指定案件并继续处理|正在指定…/.test(b.textContent ?? ''),
  ) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  searchMock.mockResolvedValue([])
})

describe('CaseAssignPicker：初始与检索', () => {
  it('挂载即检索（minLength=0 传空关键词）', async () => {
    const { unmount } = renderPicker()
    await waitFor(() => expect(searchMock).toHaveBeenCalled())
    expect(searchMock.mock.calls[0]?.[0]).toBe('')
    unmount()
  })

  it('有候选时按「案号 · 案件名」渲染进文档流', async () => {
    searchMock.mockResolvedValue([
      { id: 1, name: '张三案', case_numbers: ['（2026）京01民初1号'] },
    ])
    const { unmount } = renderPicker()
    await waitFor(() => expect(screen.getByText('（2026）京01民初1号')).toBeTruthy())
    expect(screen.getByText('张三案')).toBeTruthy()
    unmount()
  })

  it('无案号时回落「案件 id」', async () => {
    searchMock.mockResolvedValue([{ id: 7, name: '无号案', case_numbers: [] }])
    const { unmount } = renderPicker()
    await waitFor(() => expect(screen.getByText('案件 7')).toBeTruthy())
    unmount()
  })

  it('输入关键词触发带 limit 的检索', async () => {
    const { unmount } = renderPicker()
    await waitFor(() => expect(searchMock).toHaveBeenCalled())
    searchMock.mockClear()

    fireEvent.change(searchInput(), { target: { value: '张三' } })
    await waitFor(() => expect(searchMock).toHaveBeenCalled(), { timeout: 3000 })
    expect(searchMock.mock.calls[0]?.[1]).toMatchObject({ limit: 10 })
    unmount()
  })
})

describe('CaseAssignPicker：选中与重选', () => {
  async function pickFirst() {
    searchMock.mockResolvedValue([
      { id: 5, name: '目标案件', case_numbers: ['（2026）京02民初9号'] },
    ])
    const utils = renderPicker()
    const option = await waitFor(() => screen.getByText('目标案件'))
    fireEvent.click(option)
    return utils
  }

  it('选中后输入框显示「案号 · 案件名」', async () => {
    const { unmount } = await pickFirst()
    expect(searchInput().value).toBe('（2026）京02民初9号 · 目标案件')
    unmount()
  })

  it('选中后候选列表收起（只剩选中卡片的「重选」入口）', async () => {
    const { unmount } = await pickFirst()
    // 候选列表收起后没有可点的候选按钮，只剩「重选」与提交按钮
    expect(screen.queryByRole('button', { name: /目标案件/ })).toBeNull()
    expect(screen.getByRole('button', { name: '重选' })).toBeTruthy()
    unmount()
  })

  it('选中有「重选」按钮，点击清空选中与关键词', async () => {
    const { unmount } = await pickFirst()
    fireEvent.click(screen.getByRole('button', { name: '重选' }))
    expect(searchInput().value).toBe('')
    unmount()
  })

  it('修改输入会清掉已选中的案件', async () => {
    const { unmount } = await pickFirst()
    fireEvent.change(searchInput(), { target: { value: '新词' } })
    await waitFor(() => expect(searchInput().value).toBe('新词'))
    unmount()
  })
})

describe('CaseAssignPicker：提交按钮', () => {
  it('未选中时禁用', () => {
    const { unmount } = renderPicker()
    expect(submitButton().disabled).toBe(true)
    unmount()
  })

  it('选中后可用并调用 onAssign(id)', async () => {
    searchMock.mockResolvedValue([{ id: 9, name: '案件九', case_numbers: [] }])
    const { unmount, onAssign } = renderPicker()
    fireEvent.click(await waitFor(() => screen.getByText('案件九')))

    expect(submitButton().disabled).toBe(false)
    fireEvent.click(submitButton())
    await waitFor(() => expect(onAssign).toHaveBeenCalledWith(9))
    unmount()
  })

  it('busy 时禁用并显示「正在指定…」', async () => {
    searchMock.mockResolvedValue([{ id: 9, name: '案件九', case_numbers: [] }])
    const { unmount, rerender } = renderPicker()
    fireEvent.click(await waitFor(() => screen.getByText('案件九')))

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    rerender(
      <QueryClientProvider client={qc}>
        <CaseAssignPicker busy onAssign={vi.fn(async () => {})} />
      </QueryClientProvider>,
    )
    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /正在指定…/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    unmount()
  })

  it('busy 时输入框禁用', () => {
    const { unmount } = renderPicker({ busy: true })
    expect(searchInput().disabled).toBe(true)
    unmount()
  })
})
