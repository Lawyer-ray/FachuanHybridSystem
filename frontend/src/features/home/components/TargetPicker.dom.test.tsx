// @vitest-environment jsdom
/**
 * TargetPicker（关联对象关键字联想）组件单测（jsdom）。
 *
 * 这一个组件被「新增安排弹窗」和「事件编辑表单」共用，之前两侧逐字复制、
 * 已经踩过只改一边的漂移。守住三条不变量：
 * - 点候选：把选中的 TargetOption 原样交给父层，并清空检索词；
 * - 分类 tab：只显示有候选的类目，计数与过滤后的列表一致；
 * - 收起再展开：检索词与候选面板复位成干净空态（不带着上次没选中的词）。
 *
 * mock 边界：../api 只桩 searchTargetOptions（候选数据），不发真实请求。
 * 用一个小 Harness 包一层控制 open——组件本身是无状态受控件，开合由父层决定。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  searchTargetOptions: vi.fn(async (): Promise<TargetOption[]> => []),
}))

vi.mock('../api', () => ({ ...apiMock }))

import { TargetPicker } from './TargetPicker'
import type { TargetOption } from '../api'

const OPTIONS: TargetOption[] = [
  { id: 1, target_type: 'contract', target_type_label: '合同', title: '顾问合同', hint: '' },
  { id: 2, target_type: 'case', target_type_label: '案件', title: '张三诉李四', hint: '' },
  {
    id: 3,
    target_type: 'case_log',
    target_type_label: '日志',
    title: '开庭记录',
    hint: '对方已提交答辩状',
  },
]

/**
 * 父层替身：控制 open（组件本身受控）。点候选后与两个真实父层（新增安排弹窗 /
 * 事件编辑表单）同款——落到自己的「已选」状态并收起检索框；另留手动收起/展开入口。
 */
function Harness({ onPick }: { onPick: (option: TargetOption) => void }) {
  const [open, setOpen] = useState(true)
  const [picked, setPicked] = useState<TargetOption | null>(null)
  return (
    <>
      {picked && <div>已选：{picked.title}</div>}
      <button type="button" onClick={() => setOpen(false)}>
        收起
      </button>
      <button type="button" onClick={() => setOpen(true)}>
        展开
      </button>
      <TargetPicker
        open={open}
        inputId="target-q"
        listId="target-list"
        onPick={(o) => {
          setPicked(o)
          onPick(o)
          setOpen(false)
        }}
      />
    </>
  )
}

function renderPicker() {
  const onPick = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={qc}>
      <Harness onPick={onPick} />
    </QueryClientProvider>,
  )
  return { ...utils, onPick }
}

function input(): HTMLInputElement {
  return screen.getByRole('combobox') as HTMLInputElement
}

function tab(label: string): HTMLButtonElement {
  return screen.getByRole('button', { name: new RegExp(`^${label}`) }) as HTMLButtonElement
}

/** 输入关键字并等候选面板出来（防抖 250ms，前端不发空词请求） */
async function search(keyword = '张') {
  fireEvent.change(input(), { target: { value: keyword } })
  await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThan(0), {
    timeout: 3000,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.searchTargetOptions.mockResolvedValue([])
})

describe('TargetPicker：点候选', () => {
  it('点选后把候选原样交给父层，父层落「已选」并收起检索框', async () => {
    apiMock.searchTargetOptions.mockResolvedValue(OPTIONS)
    const { onPick, container } = renderPicker()

    await search('张三')
    expect(apiMock.searchTargetOptions).toHaveBeenCalledWith('张三', expect.anything())

    fireEvent.click(screen.getByRole('option', { name: /张三诉李四/ }))

    expect(onPick).toHaveBeenCalledWith(OPTIONS[1])
    expect(screen.getByText('已选：张三诉李四')).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    container.remove()
  })
})

describe('TargetPicker：分类 tab 计数与过滤', () => {
  it('tab 计数按候选数渲染，点某类只留该类候选', async () => {
    apiMock.searchTargetOptions.mockResolvedValue(OPTIONS)
    const { container } = renderPicker()
    await search()

    expect(tab('全部').textContent).toBe('全部3')
    expect(tab('合同').textContent).toBe('合同1')
    expect(tab('案件').textContent).toBe('案件1')
    expect(tab('日志').textContent).toBe('日志1')

    fireEvent.click(tab('案件'))
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByRole('option', { name: /张三诉李四/ })).toBeTruthy()
    expect(screen.queryByRole('option', { name: /顾问合同/ })).toBeNull()
    expect(screen.queryByRole('option', { name: /开庭记录/ })).toBeNull()
    container.remove()
  })

  it('没有候选的类目不渲染 tab（不出现 0 计数的死入口）', async () => {
    apiMock.searchTargetOptions.mockResolvedValue([OPTIONS[0]!, OPTIONS[1]!])
    const { container } = renderPicker()
    await search()

    expect(tab('全部').textContent).toBe('全部2')
    expect(tab('合同').textContent).toBe('合同1')
    expect(tab('案件').textContent).toBe('案件1')
    expect(screen.queryByRole('button', { name: /^日志/ })).toBeNull()
    container.remove()
  })
})

describe('TargetPicker：收起再展开复位', () => {
  it('收起后不渲染检索框；再展开是空检索词，输入新词只出新候选', async () => {
    const other: TargetOption = {
      id: 9,
      target_type: 'contract',
      target_type_label: '合同',
      title: '另一份顾问合同',
      hint: '',
    }
    apiMock.searchTargetOptions.mockImplementation(async (q?: string) => (q === '张三' ? OPTIONS : [other]))
    const { container } = renderPicker()
    await search('张三')

    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    expect(screen.queryByRole('combobox')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    // 关键词复位成空（不带着上次没选中的「张三」）
    expect(input().value).toBe('')

    await search('李')
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /另一份顾问合同/ })).toBeTruthy()
      expect(screen.queryByRole('option', { name: /张三诉李四/ })).toBeNull()
    })
    expect(apiMock.searchTargetOptions).toHaveBeenCalledWith('李', expect.anything())
    container.remove()
  })

  it('点兜底层收起候选后，重新展开并输入仍能再次出候选', async () => {
    apiMock.searchTargetOptions.mockResolvedValue(OPTIONS)
    const { container } = renderPicker()
    await search('张')

    // 面板外那层透明遮罩：点它只收起候选，不清空关键词
    fireEvent.click(container.querySelector('.fixed.inset-0.z-40') as HTMLElement)
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(input().value).toBe('张')

    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    await search('张')

    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(OPTIONS.length))
    container.remove()
  })
})
