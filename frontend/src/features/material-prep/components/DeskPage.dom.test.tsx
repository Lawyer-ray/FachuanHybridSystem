// @vitest-environment jsdom
/**
 * DeskPage（材料预处理工作台）组件渲染单测（jsdom + 真实 timers）。
 *
 * mock 边界：../api（use-inbox 消费的五个接口）、../store（useReader 桩，
 * open/openId 可控）、AppNavbar（子组件桩）、./reader/Reader（重阅读器桩）。
 * 覆盖：加载/错误态、页签计数与切换过滤、包卡片渲染、上传入口（新建材料包 →
 * 隐藏 input click → uploadPack）、卡片打开的路由跳转（navigate /material-prep/:id）、
 * 「不接」判案下推 setPackStatusRemote 与离场后卡片移除。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  listMaterialPacks: vi.fn(),
  uploadPack: vi.fn(),
  setPackStatusRemote: vi.fn(),
  deletePack: vi.fn(),
  renamePack: vi.fn(),
}))

const readerStub = vi.hoisted(() => ({
  state: {
    openId: null as number | null,
    open: vi.fn(),
    resetAll: vi.fn(),
  },
}))

vi.mock('../store', () => ({
  useReader: Object.assign(
    (sel: (s: typeof readerStub.state) => unknown) => sel(readerStub.state),
    { getState: () => readerStub.state },
  ),
}))

vi.mock('@/components/shared/AppNavbar', () => ({
  AppNavbar: () => <nav>navbar-stub</nav>,
}))
vi.mock('./reader/Reader', () => ({
  Reader: () => <div>reader-stub</div>,
}))

import { listMaterialPacks, setPackStatusRemote, uploadPack } from '../api'
import type { InboxMessage } from '../types'

import { DeskPage } from './DeskPage'

const listMock = vi.mocked(listMaterialPacks)
const uploadMock = vi.mocked(uploadPack)
const judgeMock = vi.mocked(setPackStatusRemote)

/** 记录路由变化（观察 navigate 是否把列表页推到 :id 详情路由） */
const locHistory: Array<{ pathname: string; search: string }> = []
function LocProbe() {
  const loc = useLocation()
  locHistory.push({ pathname: loc.pathname, search: loc.search })
  return null
}

function makePack(id: number, over: Partial<InboxMessage> = {}): InboxMessage {
  return {
    id,
    source_name: '手动上传',
    source_type: 'manual_upload',
    subject: `材料包 ${id}`,
    sender: '',
    recipient: '',
    received_at: '2026-10-01 10:00:00',
    has_attachments: true,
    attachment_count: 1,
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: '2026-10-01 10:00:00',
    status: 'todo',
    segs: 2,
    named: 2,
    pages: 5,
    mats: 2,
    types: ['PDF'],
    compose: '',
    ...over,
  }
}

function setupUi(initialEntry = '/material-prep') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocProbe />
        <Routes>
          <Route path="/material-prep" element={<DeskPage />} />
          <Route path="/material-prep/:id" element={<DeskPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  readerStub.state.openId = null
  readerStub.state.open.mockReset()
  listMock.mockResolvedValue([])
  uploadMock.mockResolvedValue(makePack(9) as never)
  judgeMock.mockResolvedValue({ ok: true } as never)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('DeskPage 加载 / 错误态', () => {
  it('首屏加载中：展示加载文案', () => {
    listMock.mockReturnValue(new Promise(() => {}))
    setupUi()
    expect(screen.getByText('加载材料包…')).toBeTruthy()
  })

  it('列表接口失败：展示可读错误信息', async () => {
    listMock.mockRejectedValue(new Error('后端连接失败'))
    setupUi()
    expect(await screen.findByText('无法加载材料包：后端连接失败')).toBeTruthy()
  })
})

describe('DeskPage 页签与卡片', () => {
  it('按页签过滤卡片并展示计数；默认停在待处理', async () => {
    listMock.mockResolvedValue([
      makePack(1, { subject: '王五的起诉材料' }),
      makePack(2, { subject: '赵六的证据包' }),
      makePack(3, { subject: '已归案的旧材料', status: 'done' }),
    ])
    setupUi()
    expect(await screen.findByText('王五的起诉材料')).toBeTruthy()
    expect(screen.getByText('赵六的证据包')).toBeTruthy()
    expect(screen.queryByText('已归案的旧材料')).toBeNull()
    expect(screen.getByRole('button', { name: /待处理/ }).textContent).toContain('2')
    expect(screen.getByRole('button', { name: /已归案/ }).textContent).toContain('1')
  })

  it('切换到已归案页签：只显示该状态卡片', async () => {
    listMock.mockResolvedValue([
      makePack(1, { subject: '王五的起诉材料' }),
      makePack(3, { subject: '已归案的旧材料', status: 'done' }),
    ])
    setupUi()
    await screen.findByText('王五的起诉材料')
    fireEvent.click(screen.getByRole('button', { name: /已归案/ }))
    expect(screen.getByText('已归案的旧材料')).toBeTruthy()
    expect(screen.queryByText('王五的起诉材料')).toBeNull()
  })

  it('点卡片打开层：调 openPack 并把路由推到 /material-prep/:id', async () => {
    listMock.mockResolvedValue([makePack(2, { subject: '赵六的证据包' })])
    setupUi()
    await screen.findByText('赵六的证据包')
    fireEvent.click(screen.getByRole('button', { name: '打开材料包：赵六的证据包' }))
    expect(readerStub.state.open).toHaveBeenCalledWith(2)
    await waitFor(() =>
      expect(locHistory.at(-1)?.pathname).toBe('/material-prep/2'),
    )
  })
})

describe('DeskPage 上传与判案动作', () => {
  it('新建材料包：触发隐藏 file input 的点击，选中文件后走 uploadPack', async () => {
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {})
    listMock.mockResolvedValue([makePack(1, { subject: '已有包' })])
    const { container } = setupUi()
    await screen.findByText('已有包')

    fireEvent.click(screen.getByRole('button', { name: /新建材料包/ }))
    expect(clickSpy).toHaveBeenCalled()

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeTruthy()
    const file = new File(['x'], 'contract.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(1))
    expect((uploadMock.mock.calls[0]?.[0] as File[]).length).toBe(1)
    clickSpy.mockRestore()
  })

  it('「不接」判案：下推 setPackStatusRemote(filed)，离场动画后卡片从当前页签移除', async () => {
    listMock.mockResolvedValue([
      makePack(1, { subject: '王五的起诉材料' }),
      makePack(2, { subject: '赵六的证据包' }),
    ])
    setupUi()
    await screen.findByText('王五的起诉材料')
    fireEvent.click(screen.getAllByRole('button', { name: '不接' })[0]!)

    await waitFor(() =>
      expect(judgeMock).toHaveBeenCalledWith(1, 'filed', undefined),
    )
    // PACK_LEAVE_REMOVAL_MS=540 的离场动画后，卡片从列表消失
    await waitFor(() => expect(screen.queryByText('王五的起诉材料')).toBeNull(), { timeout: 2000 })
    expect(screen.getByText('赵六的证据包')).toBeTruthy()
  })
})
