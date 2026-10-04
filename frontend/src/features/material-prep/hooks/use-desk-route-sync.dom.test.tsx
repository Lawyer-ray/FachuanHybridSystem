// @vitest-environment jsdom
/**
 * useDeskRouteSync 路由参数 ↔ 阅读器 store 同步单测（jsdom + MemoryRouter）。
 *
 * mock 只打 api 层（../api 的 getPackDetail）；useReader store 保持真实，
 * 验证三条副作用：:id 路由自动开包（含 id 变化 / 同 id 防重开）、关阅读器回退
 * 列表 URL、关闭后失效列表查询。effect 依赖数组上两处 eslint-disable 的
 * 刻意行为（deps 只含 id / 只含 openId）按实际行为覆盖。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getPackDetail: vi.fn(),
  }
})

import { getPackDetail } from '../api'
import { useReader } from '../store'
import type { InboxMessageDetail } from '../types'

import { PACKS_KEY } from './use-inbox'
import { useDeskRouteSync } from './use-desk-route-sync'

const getDetailMock = vi.mocked(getPackDetail)

/** 附件用图片（resolveMats 零网络即可算出页数），detail 保持最小形状 */
function makeDetail(id: number): InboxMessageDetail {
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
    segs: 0,
    named: 0,
    pages: 1,
    mats: 1,
    types: [],
    compose: '',
    body_text: '',
    body_html: '',
    attachments: [
      {
        filename: 'photo.jpg',
        original_filename: null,
        custom_filename: null,
        size: 10,
        content_type: 'image/jpeg',
        part_index: 0,
      },
    ],
    draft_state: {},
  }
}

/** 记录路由路径变化（观察回退 navigate 是否发生） */
const locHistory: string[] = []
function LocProbe() {
  const loc = useLocation()
  locHistory.push(loc.pathname)
  return null
}

/** 暴露路由 navigate 给用例：经 ref 容器中转（渲染期只写成员，不重排模块变量） */
const navRef: { current: ReturnType<typeof useNavigate> | null } = { current: null }
function NavProbe() {
  navRef.current = useNavigate()
  return null
}

function setup(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <NavProbe />
        <LocProbe />
        <Routes>
          <Route path="/material-prep" element={<>{children}</>} />
          <Route path="/material-prep/:id" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
  const utils = renderHook(() => useDeskRouteSync(), { wrapper })
  const navigate = (to: string) => act(() => navRef.current!(to))
  return { ...utils, navigate, invalidateSpy }
}

beforeEach(() => {
  vi.clearAllMocks()
  locHistory.length = 0
  // 渲染前复位 store（此时无订阅者）；不在 afterEach 里复位——hook 仍挂载时
  // 改 store 会逸出 act，还会经 effect 触发回退 navigate 污染下个用例
  useReader.getState().resetAll()
})

/**
 * 冲刷 store.open 的异步链（mock 均 resolved，微任务深度固定）：每次 act 内
 * flush 一拍微任务，让详情解析 / 状态落地都发生在 act 里，避免更新逸出。
 */
async function settle(times = 4) {
  for (let i = 0; i < times; i++) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

describe('副作用 1：:id 路由自动开包', () => {
  it('列表路由（无 id）：不触发 open，getPackDetail 零调用', () => {
    setup('/material-prep')
    expect(useReader.getState().openId).toBeNull()
    expect(getDetailMock).not.toHaveBeenCalled()
  })

  it('详情路由（分享直达 / 刷新）：自动 openPack(id)，拉详情直至 ready', async () => {
    getDetailMock.mockResolvedValue(makeDetail(5))
    setup('/material-prep/5')
    await settle()
    expect(useReader.getState().status).toBe('ready')
    expect(getDetailMock).toHaveBeenCalledWith(5)
    expect(useReader.getState().openId).toBe(5)
    expect(useReader.getState().detail?.subject).toBe('材料包 5')
  })

  it('store 已打开同一 id：URL 重渲染不重复开包', async () => {
    act(() => {
      useReader.setState({ openId: 5 })
    })
    setup('/material-prep/5')
    await settle(1)
    // effect 内先查 getState().openId === Number(id)，相同即跳过
    expect(getDetailMock).not.toHaveBeenCalled()
    expect(useReader.getState().openId).toBe(5)
  })

  it('openPack 的 id 变化触发：5 → 7 切换路由后打开新包', async () => {
    getDetailMock.mockResolvedValue(makeDetail(5))
    const { navigate } = setup('/material-prep/5')
    await settle()
    expect(useReader.getState().status).toBe('ready')
    expect(getDetailMock).toHaveBeenCalledTimes(1)

    getDetailMock.mockResolvedValue(makeDetail(7))
    navigate('/material-prep/7')
    await settle()
    expect(useReader.getState().openId).toBe(7)
    expect(getDetailMock).toHaveBeenCalledWith(7)
  })

  it('开包失败：停在 error 态，不自动回退 URL（用户手动处理）', async () => {
    getDetailMock.mockRejectedValue(new Error('后端不可达'))
    setup('/material-prep/5')
    await settle()
    expect(useReader.getState().status).toBe('error')
    expect(useReader.getState().error).toBe('后端不可达')
    expect(locHistory.at(-1)).toBe('/material-prep/5')
  })
})

describe('副作用 2：关阅读器回退列表 URL', () => {
  it('从打开态退到未打开且 URL 停在 :id：replace 回 /material-prep', async () => {
    getDetailMock.mockResolvedValue(makeDetail(5))
    setup('/material-prep/5')
    // 模拟 store.open 已把 openId 置位（open 的同步首拍），再模拟关闭后的 openId 清空
    act(() => {
      useReader.setState({ openId: 5 })
    })
    expect(locHistory).toContain('/material-prep/5')
    act(() => {
      useReader.setState({ openId: null })
    })
    await settle(1)
    expect(locHistory.at(-1)).toBe('/material-prep')
  })

  it('关闭发生在列表路由（无 id）：不需要回退，URL 保持不动', async () => {
    setup('/material-prep')
    act(() => {
      useReader.setState({ openId: 5 })
    })
    act(() => {
      useReader.setState({ openId: null })
    })
    await settle(1)
    expect(locHistory.every((p) => p === '/material-prep')).toBe(true)
  })
})

describe('副作用 3：关闭阅读器后失效列表查询', () => {
  it('openId 从非 null 变 null：invalidate PACKS_KEY（列表卡片刷新进度）', async () => {
    const { invalidateSpy } = setup('/material-prep')
    act(() => {
      useReader.setState({ openId: 5 })
    })
    expect(invalidateSpy).not.toHaveBeenCalled()
    act(() => {
      useReader.setState({ openId: null })
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })

  it('打开（null → 5）与切换（5 → 7）都不触发失效：只有关闭才刷列表', async () => {
    const { invalidateSpy } = setup('/material-prep')
    act(() => {
      useReader.setState({ openId: 5 })
    })
    act(() => {
      useReader.setState({ openId: 7 })
    })
    await settle(1)
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
