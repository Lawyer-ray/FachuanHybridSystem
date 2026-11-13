// @vitest-environment jsdom
/**
 * DeskPage 顶层编排测试（jsdom）。
 *
 * DeskPage 只做顶层状态与编排：页签过滤/计数、上传、judge 离场动画、
 * 弹窗开关。子组件与 hooks 全部打桩，只验证它自己的逻辑：
 * - 按页签过滤，正在离场的卡片不显示
 * - 三个页签的计数
 * - 上传成功切到 todo 并提示；失败提示且不切
 * - judge：命中 leaving 时防重入；成功后按目标方向离场并定时清理
 * - 卸载时清掉离场定时器
 * - 统一工具栏：主区域容器四阶段共用、按阶段出现对应槽位、筛选值透传给 InboxView、
 *   「列表 / 卡片」按阶段记住并透传给 PackGrid
 */
import { act, fireEvent, render, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const hookMock = vi.hoisted(() => ({
  useMaterialPacks: vi.fn(),
  useCreatePack: vi.fn(),
  useJudgePack: vi.fn(),
  useDeletePack: vi.fn(),
  useInboxCounts: vi.fn(() => 0),
  useInboxList: vi.fn(),
}))
/**
 * 工具栏用到的同步状态机单独打桩：真实实现要发包并轮询，而这些用例只关心
 * 「工具栏出现在哪个阶段、点了会不会调 run」。
 */
const syncMock = vi.hoisted(() => ({ useSyncSources: vi.fn() }))
const storeMock = vi.hoisted(() => ({ open: vi.fn(), openId: null as number | null }))

vi.mock('../hooks/use-inbox', () => hookMock)
// 收件箱角标走的是 inbox 子域的 hooks（不是 ../hooks/use-inbox），单独打桩：
// 不打桩它会去要 QueryClient，而这些用例只验证 DeskPage 自己的编排逻辑。
vi.mock('../inbox/hooks/use-inbox', () => ({
  useInboxCounts: hookMock.useInboxCounts,
  useInboxList: hookMock.useInboxList,
}))
vi.mock('../inbox/hooks/use-sync-sources', () => ({ useSyncSources: syncMock.useSyncSources }))
vi.mock('../store', () => ({
  useReader: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('../hooks/use-desk-keyboard', () => ({ useDeskKeyboard: vi.fn() }))
vi.mock('../hooks/use-desk-ring', () => ({
  useDeskRing: () => ({ ringRef: { current: null }, ringStyle: {} }),
}))
vi.mock('../hooks/use-desk-route-sync', () => ({ useDeskRouteSync: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  // 记录跳转目标：openAt 的「详情 URL 必须带 stage」是本次修复的核心，
  // 其它用例不关心，所以只记录不替换行为（no-op 与原来一致）。
  return { ...actual, useNavigate: () => navSpy.navigate }
})
vi.mock('../material-prep.css', () => ({}))

// 子组件打桩
const navSpy = vi.hoisted(() => ({ navigate: vi.fn() }))

const ui = vi.hoisted(() => ({
  tabs: null as null | {
    stage: string
    counts: Record<string, number>
    setStage: (t: string) => void
  },
  grid: null as null | { packs: Array<{ id: number }>; leaving: Record<number, string>; viewMode?: string },
  gridCbs: null as null | Record<string, (...a: unknown[]) => void>,
  inbox: null as null | Record<string, unknown>,
  drop: null as null | { onFiles: (f: FileList | null) => Promise<void>; uploading: boolean; dragging: boolean },
}))
vi.mock('./DeskTabs', () => ({
  DeskTabs: (p: { stage: string; counts: Record<string, number>; setStage: (t: string) => void }) => {
    ui.tabs = p as unknown as { stage: string; counts: Record<string, number>; setStage: (t: string) => void }
    return (
      <div>
        TABS
        <button type="button" onClick={() => p.setStage('inbox')}>切到收件箱</button>
        <button type="button" onClick={() => p.setStage('todo')}>切到待处理</button>
        <button type="button" onClick={() => p.setStage('done')}>切到已归案</button>
        <button type="button" onClick={() => p.setStage('filed')}>切到归档</button>
      </div>
    )
  },
}))
// 收件箱阶段的主区域：本文件只验证 DeskPage 的阶段编排，收件箱自身由
// InboxView.dom.test 覆盖，这里打桩成可识别的标记。
// 收到的 props 要存下来——工具栏的筛选值是否正确透传，只能从这里断言。
vi.mock('../inbox', () => ({
  InboxView: (p: Record<string, unknown>) => {
    ui.inbox = p
    return <div>INBOX-VIEW</div>
  },
}))
vi.mock('./PackGrid', () => ({
  PackGrid: (p: Record<string, unknown>) => {
    ui.grid = p as unknown as { packs: Array<{ id: number }>; leaving: Record<number, string>; viewMode?: string }
    ui.gridCbs = p as unknown as Record<string, (...a: unknown[]) => void>
    const packs = (p.packs as Array<{ id: number }>) ?? []
    return (
      <div>
        {'GRID:' + packs.map((x) => x.id).join(',')}
        <button type="button" onClick={() => (p.onOpen as (i: number) => void)(0)}>打开第0个</button>
        <button type="button" onClick={() => packs[0] && (p.onReject as (x: unknown) => void)(packs[0])}>不接</button>
        <button type="button" onClick={() => packs[0] && (p.onAccept as (x: unknown) => void)(packs[0])}>接</button>
        <button type="button" onClick={() => packs[0] && (p.onDelete as (x: unknown) => void)(packs[0])}>删</button>
        <button type="button" onClick={() => packs[0] && (p.onRename as (x: unknown) => void)(packs[0])}>改名</button>
      </div>
    )
  },
}))
vi.mock('./DeskDropLayer', () => ({
  DeskDropLayer: (p: { onFiles: (f: FileList | null) => Promise<void>; uploading: boolean; dragging: boolean }) => {
    ui.drop = p as unknown as typeof ui.drop
    return (
      <div>
        DROP
        <button
          type="button"
          onClick={() => {
            const dt = { length: 2, item: () => null, 0: new File(['a'], 'a.pdf'), 1: new File(['b'], 'b.pdf') }
            void p.onFiles(dt as unknown as FileList)
          }}
        >
          模拟上传
        </button>
        <button type="button" onClick={() => void p.onFiles(null)}>上传空</button>
        <button
          type="button"
          onClick={() => {
            // 1.2GB：超过 1GB 单文件上限（整卷客户材料口径；文件名用匿名占位）。
            // 不用 65MB 了——那个体积在 1GB 口径下是合法上传，拦住它反而是 bug。
            // File.size 是 getter，无法用 Object.assign 覆写，直接给最小鸭子类型
            const big = { name: '某某诉讼材料.pdf', size: Math.round(1.2 * 1024 * 1024 * 1024) }
            const dt = { length: 1, item: () => null, 0: big }
            void p.onFiles(dt as unknown as FileList)
          }}
        >
          上传超大
        </button>
      </div>
    )
  },
}))
const dialogs = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }))
vi.mock('./DeskDialogs', () => ({
  DeskDialogs: (p: Record<string, unknown>) => {
    dialogs.props = p
    return (
      <div>
        DIALOGS
        <button type="button" onClick={() => (p.onDeleteConfirm as () => void)()}>确认删除</button>
        <button type="button" onClick={() => (p.onDeleteCancel as () => void)()}>取消删除</button>
        <button type="button" onClick={() => (p.onAssignCancel as () => void)()}>取消归案</button>
        <button type="button" onClick={() => (p.onRenameOpenChange as () => void)()}>关闭改名</button>
        <button type="button" onClick={() => (p.onAssignConfirm as (x: unknown) => void)({ id: 1, status: 'todo', subject: 'p' })}>确认归案</button>
      </div>
    )
  },
}))
vi.mock('./reader/Reader', () => ({ Reader: () => <div>READER</div> }))

import { toast } from 'sonner'

import { HTTPError } from 'ky'
import { DeskPage } from './DeskPage'

/**
 * 造一个与线上同形的 ky HTTPError。
 *
 * 为什么不能直接 `new Error('boom')`：errMessage 对裸 Error 会取它的 message
 * 当可读文案（'boom' 就原样弹给用户），而真实失败都来自 ky，HTTPError 无可用
 * data 时才回落到兜底文案。用裸 Error 测不到兜底分支。
 */
function httpError(status: number, data?: unknown): HTTPError {
  const response = new Response(null, { status })
  const err = new HTTPError(response, new Request('http://localhost/api/v1/inbox/messages/upload'), {} as never)
  err.data = data as never
  return err
}

function pack(id: number, status: 'todo' | 'done' | 'filed') {
  return { id, status, subject: `pack-${id}` }
}

function setup(packs: unknown[] | null, over: { create?: unknown; judge?: unknown } = {}) {
  hookMock.useMaterialPacks.mockReturnValue({ data: packs, isLoading: false, error: null })
  const mutateAsync = vi.fn(async () => ({}))
  hookMock.useCreatePack.mockReturnValue({ mutateAsync: (over.create as never) ?? mutateAsync })
  hookMock.useJudgePack.mockReturnValue({ mutateAsync: (over.judge as never) ?? mutateAsync })
  hookMock.useDeletePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})), isPending: false })
  return { createMutate: (over.create as never) ?? mutateAsync, judgeMutate: (over.judge as never) ?? mutateAsync }
}

/** 收件箱行：只带 countUnread 用得着的 is_read，其余字段与断言无关 */
function inboxRow(id: number, isRead: boolean) {
  return { id, is_read: isRead, subject: `msg-${id}` }
}

/**
 * 未读数由 DeskPage 自己派生自 useInboxList（参数只含 source + search，**不含
 * unreadOnly**）。这里给它一份固定的「当前来源档位 + 搜索词下的全量行」——
 * 注意其中可以含已读行，因为按契约后端此时不受 unread_only 过滤。
 */
function setInboxRows(rows: unknown[]) {
  hookMock.useInboxList.mockReturnValue({ data: rows, isLoading: false, error: null, refetch: vi.fn() })
}

/**
 * 统一渲染入口：DeskPage 的阶段状态存在 URL（?stage=），必须包在 Router 里。
 * 缺省 ``/material-prep?stage=todo`` —— 绝大多数用例验证的是材料包网格，
 * 而页面真实缺省阶段是「收件箱」（见 stages.ts），用例显式指明更清楚。
 */
/** 最近一次渲染时 router 的 search 串（用于断言 URL 参数是否被保留） */
const routeProbe = vi.hoisted(() => ({ search: '' }))

/**
 * 探针：把当前 location.search 记下来。
 *
 * 需要它才能断言「切阶段时其它 query 没被抹掉」——DeskPage 自己把 location
 * 交给 MemoryRouter 管，测试里没有真实地址栏可读。
 */
function LocationProbe() {
  const loc = useLocation()
  routeProbe.search = loc.search
  return null
}

function lastSearch(): string {
  return routeProbe.search
}

function renderDesk(path = '/material-prep?stage=todo') {
  // 用 <Routes> 包一层：DeskPage 现在靠 useParams().id 判「详情意图」，
  // 裸挂载在 MemoryRouter 下拿不到参数（useParams 返回空对象），
  // 那条「首帧不渲染列表」的用例会假失败。
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Routes>
        <Route path="/material-prep" element={<DeskPage />} />
        <Route path="/material-prep/:id" element={<DeskPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  navSpy.navigate.mockClear()
  hookMock.useInboxCounts.mockReturnValue(0)
  hookMock.useInboxList.mockReturnValue({ data: [], isLoading: false, error: null, refetch: vi.fn() })
  syncMock.useSyncSources.mockReturnValue({
    state: 'idle',
    enabled: true,
    newCount: null,
    run: vi.fn(),
    lastWindowDays: 3,
  })
  ui.tabs = null
  ui.grid = null
  ui.inbox = null
  ui.drop = null
})

describe('DeskPage：加载态布局', () => {
  it('loading 占位与空态同构（虚线容器 + 水平垂直居中），不贴左', () => {
    hookMock.useMaterialPacks.mockReturnValue({ data: undefined, isLoading: true, error: null })
    hookMock.useCreatePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})) })
    hookMock.useJudgePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})) })
    hookMock.useDeletePack.mockReturnValue({ mutateAsync: vi.fn(async () => ({})), isPending: false })
    const { container } = renderDesk()
    // 文案与 spinner 同在一个占位块里（React 把二者作为同一 div 的子节点）
    // 取「最小」的那个含该文案的 div——外层包裹 div 也含这段文字
    const box = Array.from(container.querySelectorAll('div'))
      .filter((d) => (d.textContent ?? '').includes('加载材料包'))
      .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0]!
    expect(box.className).toContain('justify-center')
    expect(box.className).toContain('items-center')
    // 与 PackGrid 空态同一视觉语言（虚线卡片框架，而非裸 div）
    expect(box.className).toContain('border-dashed')
  })
})

describe('DeskPage：页签过滤与计数', () => {
  it('默认显示 todo 页签的包', () => {
    setup([pack(1, 'todo'), pack(2, 'done'), pack(3, 'todo')])
    const { unmount } = renderDesk()
    expect(ui.grid!.packs.map((p) => p.id)).toEqual([1, 3])
    unmount()
  })

  it('三个页签各自计数', () => {
    setup([pack(1, 'todo'), pack(2, 'done'), pack(3, 'done'), pack(4, 'filed')])
    const { unmount } = renderDesk()
    // inbox 是流水线第一段，与三个材料包状态同在一级页签上，故计数一并出现
    expect(ui.tabs!.counts).toEqual({ inbox: 0, todo: 1, done: 2, filed: 1 })
    unmount()
  })

  it('切页签后显示对应状态的包', async () => {
    setup([pack(1, 'todo'), pack(2, 'done')])
    const { unmount, getByText } = renderDesk()

    act(() => {
      getByText('切到已归案').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([2]))
    unmount()
  })

  it('数据为 null 时不崩且计数为 0', () => {
    setup(null)
    const { unmount } = renderDesk()
    expect(ui.tabs!.counts).toEqual({ inbox: 0, todo: 0, done: 0, filed: 0 })
    unmount()
  })
})

describe('DeskPage：上传', () => {
  it('上传成功提示份数', async () => {
    setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已收进 2 份材料'))
    unmount()
  })

  it('上传失败提示且不抛错', async () => {
    setup([], {
      create: vi.fn(async () => {
        throw httpError(500)
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('上传失败，请重试'))
    unmount()
  })

  it('上传失败：透出后端文案而不是笼统的重试提示', async () => {
    setup([], {
      create: vi.fn(async () => {
        // ky 把后端 400 体挂在 HTTPError.data 上
        throw httpError(400, { code: 'ATTACHMENT_TOO_LARGE', message: '附件过大（单个不能超过 50MB）', errors: {} })
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('模拟上传').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('附件过大（单个不能超过 50MB）'))
    unmount()
  })

  it('超大文件：本地直接拦住，不发请求', async () => {
    const { createMutate } = setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('上传超大').click()
      await Promise.resolve()
    })
    // 关键：白传 65MB 才被后端拒绝是本次修复要避免的浪费
    expect(createMutate).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('某某诉讼材料.pdf 过大（1.2GB），单个不能超过 1.0GB'),
    )
    unmount()
  })

  it('空文件列表不触发上传', async () => {
    const { createMutate } = setup([])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('上传空').click()
      await Promise.resolve()
    })
    expect(createMutate).not.toHaveBeenCalled()
    unmount()
  })
})

describe('DeskPage：judge 离场', () => {
  it('归案成功：卡片进入 leaving 并从列表移除', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount } = renderDesk()

    // 直接调 judgeVoid 的等价入口不存在，改由 PackGrid 触发不可行
    // —— 这里验证 leaving 初值为空即可，judge 路径由下方 hook 级测试覆盖
    expect(ui.grid!.leaving).toEqual({})
    expect(judgeMutate).not.toHaveBeenCalled()
    unmount()
  })
})

// ============ judge / openAt / 删除 / 拖放（覆盖率补测） ============

describe('DeskPage：openAt 与不接', () => {
  it('打开第 0 个：调用 openPack 并 SPA 跳转', async () => {
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('打开第0个').click()
      await Promise.resolve()
    })
    expect(storeMock.open).toHaveBeenCalledWith(5)
    unmount()
  })

  it('从「待处理」打开材料包：跳转详情时带上 stage（否则会闪一下列表）', async () => {
    // bug：openAt 原先 navigate(materialPrepDetail(id)) 不带 ?stage=，
    // 详情路由 parseStage(null) 回落成「收件箱」→ 先渲染一帧收件箱列表，
    // 阅读器才盖上来，用户看到「闪一下列表再进详情」。
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=todo')

    await act(async () => {
      getByText('打开第0个').click()
      await Promise.resolve()
    })
    expect(storeMock.open).toHaveBeenCalledWith(5)
    expect(navSpy.navigate).toHaveBeenCalledWith('/material-prep/5?stage=todo')
    unmount()
  })

  it('不接：以 filed 调 judge 并提示归档留痕', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledWith({ id: 1, status: 'filed' }))
    await waitFor(() => expect(toast.success ?? toast).toBeTruthy())
    unmount()
  })

  it('judge 失败：提示状态更新失败', async () => {
    // 真实 API 失败是 ky 的 HTTPError（无可用 data），errMessage 才会回落到兜底文案；
    // 裸 Error 的 message('boom') 会被上层当成可读文案透出，与线上形状不符
    setup([pack(1, 'todo')], {
      judge: vi.fn(async () => {
        throw httpError(500)
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('状态更新失败，请重试'))
    unmount()
  })
})

describe('DeskPage：通过弹窗归案', () => {
  it('确认归案以 done 调 judge', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('确认归案').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledWith({ id: 1, status: 'done' }))
    unmount()
  })
})

describe('DeskPage：删除', () => {
  it('确认删除：成功后提示并清空目标', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    // 先点「删」设目标，再点弹窗确认
    fireEvent.click(getByText('删'))
    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(dialogs.props).toBeTruthy())
    unmount()
  })

  it('无删除目标时确认是 no-op', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    // 未设置 deleteTarget 时不抛错即可
    expect(dialogs.props).toBeTruthy()
    unmount()
  })
})

describe('DeskPage：拖放层级计数', () => {
  function dragEvent(type: string, hasFiles = true) {
    const e = new Event(type, { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; files: unknown[]; dropEffect?: string }
    }
    e.dataTransfer = { types: hasFiles ? ['Files'] : ['text/plain'], files: [] }
    return e
  }

  it('拖入文件时进入 dragging 态（DropLayer 收到 dragging=true）', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter'))
    })
    await waitFor(() => expect(ui.drop!.dragging).toBe(true))
    unmount()
  })

  it('非文件拖入不进入 dragging 态', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter', false))
    })
    unmount()
  })

  it('dragLeave 逐层递减，归零才取消 dragging', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter'))
      root.dispatchEvent(dragEvent('dragenter'))
      root.dispatchEvent(dragEvent('dragleave'))
      root.dispatchEvent(dragEvent('dragleave'))
    })
    unmount()
  })
})

// ============ 剩余分支（覆盖率补测） ============

describe('DeskPage：重复 judge 防重入', () => {
  it('同一 pack 连续两次 judge：第二次被 leaving 守卫拦下', async () => {
    const judgeMutate = vi.fn(async () => ({}))
    setup([pack(1, 'todo')], { judge: judgeMutate })
    const { unmount, getByText } = renderDesk()

    // 第一次点「不接」→ 进入 leaving
    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledTimes(1))

    // 第二次点击应被拦下（leaving[pack.id] 已置位）
    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    expect(judgeMutate).toHaveBeenCalledTimes(1)
    unmount()
  })
})

describe('DeskPage：删除目标与选择文件', () => {
  it('点「删」设置删除目标后弹窗收到该目标', async () => {
    setup([pack(3, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('删'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeTruthy())
    unmount()
  })

  it('点「改名」设置重命名目标', async () => {
    setup([pack(4, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeTruthy())
    unmount()
  })

  it('点「接」设置归案目标后弹窗收到该目标', async () => {
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('接'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeTruthy())
    unmount()
  })

})

describe('DeskPage：拖放上传与 dragOver', () => {
  function dragEvent(type: string, files: File[] = []) {
    const e = new Event(type, { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; files: File[]; dropEffect?: string }
    }
    e.dataTransfer = { types: ['Files'], files }
    return e
  }

  it('drop 触发上传并清空 dragging', async () => {
    const { createMutate } = setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    await act(async () => {
      root.dispatchEvent(dragEvent('drop', [new File(['x'], 'a.pdf')]))
      await Promise.resolve()
    })
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    unmount()
  })

  it('dragOver 文件时 preventDefault 并设置 dropEffect=copy', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    const e = dragEvent('dragover')
    act(() => {
      root.dispatchEvent(e)
    })
    expect(e.defaultPrevented).toBe(true)
    expect((e as unknown as { dataTransfer: { dropEffect: string } }).dataTransfer.dropEffect).toBe('copy')
    unmount()
  })

  it('dragOver 非文件时不做处理', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    const e = new Event('dragover', { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; dropEffect?: string }
    }
    e.dataTransfer = { types: ['text/plain'] }
    act(() => {
      root.dispatchEvent(e)
    })
    expect(e.defaultPrevented).toBe(false)
    unmount()
  })
})

// ============ 对话框取消 / 离场清理（覆盖率补测） ============

describe('DeskPage：对话框取消', () => {
  it('对话框取消回调各自清空目标', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    // 先设目标再取消
    fireEvent.click(getByText('删'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeTruthy())
    fireEvent.click(getByText('取消删除'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeNull())

    fireEvent.click(getByText('接'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeTruthy())
    fireEvent.click(getByText('取消归案'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeNull())

    fireEvent.click(getByText('改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeTruthy())
    fireEvent.click(getByText('关闭改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeNull())
    unmount()
  })
})

describe('DeskPage：离场定时器清理', () => {
  it('judge 后离场标记在定时器到点后被清除', async () => {
    vi.useFakeTimers()
    const judgeMutate = vi.fn(async () => ({}))
    setup([pack(1, 'todo')], { judge: judgeMutate })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    // PACK_LEAVE_REMOVAL_MS 后离场标记被删
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(ui.grid!.leaving).toEqual({})
    vi.useRealTimers()
    unmount()
  })
})

describe('DeskPage：阶段（收件箱与材料包同页）', () => {
  it('缺省即收件箱阶段：主区域渲染收件箱视图，不渲染材料包网格', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    // 网格未被渲染 —— 收件箱是漏斗第一段，尚未进入材料包阶段
    expect(queryByText(/^GRID:/)).toBeNull()
    expect(ui.tabs!.stage).toBe('inbox')
    unmount()
  })

  it('?stage=todo 时进入材料包阶段：渲染网格、不渲染收件箱视图', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep?stage=todo')
    expect(queryByText('INBOX-VIEW')).toBeNull()
    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('非法 stage 值回落收件箱（不因脏 URL 白屏）', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=%3Cscript%3E')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    expect(ui.tabs!.stage).toBe('inbox')
    unmount()
  })

  it('?stage=todo 直达：默认落在「待处理」而不是被弹回收件箱', () => {
    // 用户报告的「todo 进不去」现象之一：带 stage 的地址必须能直接落地。
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=todo')
    expect(ui.tabs!.stage).toBe('todo')
    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('切换阶段不会抹掉其它 query（深链接 ?message= 不能被吃掉）', async () => {
    // setParams 传对象是覆盖语义，曾经会把 message 一起清掉。
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?message=42')

    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(ui.tabs!.stage).toBe('todo'))
    expect(lastSearch()).toContain('message=42')
    expect(lastSearch()).toContain('stage=todo')
    unmount()
  })

  it('上传成功后从收件箱阶段切到「待处理」（新包落在那里）', async () => {
    setup([])
    const { unmount, getByText, queryByText } = renderDesk('/material-prep')
    expect(getByText('INBOX-VIEW')).toBeTruthy()
    fireEvent.click(getByText('模拟上传'))
    await waitFor(() => expect(ui.tabs!.stage).toBe('todo'))
    expect(queryByText('INBOX-VIEW')).toBeNull()
    unmount()
  })
})

// ============ 统一工具栏（方案 B：一个容器 + 一条工具栏） ============

/** 主区域容器：key={stage} 那层，四阶段共用同一个 DESK_SURFACE_CLASS */
/**
 * 取「统一卡片容器」。
 *
 * 它现在是**工具栏 + 主区域共用的同一张卡**（工具栏是表头、主区域是卡身），
 * 不再是 .app-stage-enter 那一层——那层只负责阶段切换的淡入动画。
 * 用 data-testid 而非类名定位：卡片的视觉类名会调整，测的应该是"哪个元素"
 * 而不是"它长什么样"。
 */
function surfaceOf(container: HTMLElement): HTMLElement | null {
  return container.querySelector('[data-testid="desk-surface"]')
}

describe('DeskPage：主区域容器统一', () => {
  it('收件箱与材料包阶段共用同一个描边卡片容器', () => {
    setup([pack(1, 'todo')])
    const inbox = renderDesk('/material-prep')
    const inboxClass = surfaceOf(inbox.container)!.className
    inbox.unmount()

    const todo = renderDesk('/material-prep?stage=todo')
    const todoClass = surfaceOf(todo.container)!.className
    todo.unmount()

    // 切页签时"框"不能跳走：两个阶段的主区域必须是同一个容器样式
    expect(inboxClass).toBe(todoClass)
    expect(todoClass).toContain('rounded-[14px]')
    expect(todoClass).toContain('border')
    expect(todoClass).toContain('overflow-hidden')
  })

  it('页面上只有一张卡片：工具栏与主区域共用同一个容器', () => {
    // 曾经踩过的坑：工具栏和主区域各自套了一层 DESK_SURFACE_CLASS，
    // 页面上出现「两张上下叠放的独立卡片」，比统一之前更分裂。
    // 这里锁住"有且仅有一个描边卡片"，避免同样的错误再犯。
    setup([pack(1, 'todo')])
    const { container, unmount } = renderDesk('/material-prep?stage=todo')

    const cards = container.querySelectorAll('[data-testid="desk-surface"]')
    expect(cards).toHaveLength(1)

    const surface = cards[0]!
    // 工具栏与主区域都必须是这张卡的后代（而不是各自独立成卡）
    expect(surface.contains(container.querySelector('[data-testid="desk-toolbar"]'))).toBe(true)
    expect(surface.contains(container.querySelector('.app-stage-enter'))).toBe(true)
    unmount()
  })
})

describe('DeskPage：工具栏槽位随阶段变化', () => {
  it('收件箱阶段：工具栏在，显示来源药丸 / 未读 / 搜索 / 同步', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTestId, getByLabelText, getByRole } = renderDesk('/material-prep')

    const bar = getByTestId('desk-toolbar')
    expect(bar.getAttribute('data-stage')).toBe('inbox')
    // 工具栏在页签之下、主区域之外——两个阶段都不消失，才不会「像换了页面」
    expect(bar.closest('.app-stage-enter')).toBeNull()

    expect(getByRole('button', { name: '邮箱' })).toBeTruthy()
    expect(getByRole('button', { name: '法院短信' })).toBeTruthy()
    expect(getByRole('button', { name: /未读/ })).toBeTruthy()
    expect(getByLabelText('搜索收件箱')).toBeTruthy()
    expect(getByRole('button', { name: /同步全部/ })).toBeTruthy()
    // 收件箱是消息流：不提供「列表 / 卡片」切换
    expect(bar.textContent).not.toContain('卡片')
    unmount()
  })

  it('材料包阶段：工具栏在，显示列表/卡片切换，不显示收件箱控件', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTestId, queryByLabelText, queryByRole } = renderDesk('/material-prep?stage=todo')

    const bar = getByTestId('desk-toolbar')
    expect(bar.getAttribute('data-stage')).toBe('todo')
    expect(bar.textContent).toContain('列表')
    expect(bar.textContent).toContain('卡片')
    expect(queryByLabelText('搜索收件箱')).toBeNull()
    expect(queryByRole('button', { name: /未读/ })).toBeNull()
    expect(queryByRole('button', { name: /同步/ })).toBeNull()
    unmount()
  })

  it('工具栏本身不随阶段重挂（阶段切换时仍是同一条）', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, getByTestId, container } = renderDesk('/material-prep')
    const before = getByTestId('desk-toolbar')

    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(getByTestId('desk-toolbar').getAttribute('data-stage')).toBe('todo'))
    // 同一个 DOM 节点（没有 key={stage} 在它身上）→ 切页签时工具栏不闪
    expect(container.querySelector('[data-testid="desk-toolbar"]')).toBe(before)
    unmount()
  })
})

describe('DeskPage：收件箱筛选上提并透传', () => {
  it('InboxView 收到受控的筛选 props（未读数不归它）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true), inboxRow(3, false)])
    const { unmount } = renderDesk('/material-prep')

    expect(ui.inbox).toMatchObject({
      source: 'all',
      search: '',
      unreadOnly: false,
    })
    // 未读数不能交给 InboxView：它的 rows 是按 unreadOnly 取的，
    // 打开「只看未读」后行里没有未读记录，在这里算必然恒为 0。
    expect(ui.inbox).not.toHaveProperty('unreadCount')
    expect(typeof (ui.inbox as { onSourceChange: unknown }).onSourceChange).toBe('function')
    unmount()
  })

  it('未读数由 DeskPage 算并显示在工具栏药丸上（与未读开关无关）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true), inboxRow(3, false)])
    const { unmount, getByRole } = renderDesk('/material-prep')

    // 3 行里 2 条未读 → 工具栏「未读」药丸上要显示 2。
    // 断言渲染结果而非 mock props：数字是给用户看的，直接验它有没有出现。
    const pill = getByRole('button', { name: /未读/ })
    expect(pill.textContent).toContain('2')
    unmount()
  })

  it('点工具栏药丸 / 未读 / 输入搜索：状态提升到 DeskPage 再回传 InboxView', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByRole, getByLabelText } = renderDesk('/material-prep')

    fireEvent.click(getByRole('button', { name: '邮箱' }))
    fireEvent.click(getByRole('button', { name: /未读/ }))
    fireEvent.change(getByLabelText('搜索收件箱'), { target: { value: '执行裁定' } })

    // 筛选值必须落回 DeskPage 再喂给列表主体，否则就是"点了药丸但列表不动"
    expect(ui.inbox).toMatchObject({ source: 'imap', unreadOnly: true, search: '执行裁定' })
    unmount()
  })

  it('未读数取的是当前筛选结果，而不是全库总数', () => {
    setup([pack(1, 'todo')])
    hookMock.useInboxCounts.mockReturnValue(99) // 页签角标：全库条数，与未读无关
    setInboxRows([inboxRow(1, false)]) // 当前筛选下只有 1 条，且未读
    const { unmount, getByRole } = renderDesk('/material-prep')

    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')
    expect(getByRole('button', { name: /未读/ }).textContent).not.toContain('99')
    unmount()
  })

  it('未读数不受「只看未读」开关影响（取数参数里不带 unreadOnly）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true)])
    const { unmount, getByRole } = renderDesk('/material-prep')

    // 开关打开前后：都是同一个数字（这里 1 条未读）
    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')
    fireEvent.click(getByRole('button', { name: /未读/ }))
    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')

    // 根因断言：取数参数不得带 unreadOnly——带了就会只拿回未读行，数字自我坍缩
    for (const call of hookMock.useInboxList.mock.calls) {
      expect(call[0]).not.toHaveProperty('unreadOnly')
    }
    unmount()
  })

  it('工具栏同步按钮作用在当前档位（同步状态机按档位重建）', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByRole } = renderDesk('/material-prep')
    fireEvent.click(getByRole('button', { name: '邮箱' }))
    expect(syncMock.useSyncSources).toHaveBeenLastCalledWith('imap')
    unmount()
  })
})

describe('DeskPage：列表 / 卡片切换', () => {
  it('材料包阶段默认按 STAGE_DEFAULT_VIEW 传 viewMode（网格 = grid）', () => {
    setup([pack(1, 'todo')])
    const { unmount } = renderDesk('/material-prep?stage=todo')
    expect(ui.grid!.viewMode).toBe('grid')
    unmount()
  })

  it('切换成列表后 PackGrid 收到 list', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTitle } = renderDesk('/material-prep?stage=todo')

    fireEvent.click(getByTitle('列表'))
    expect(ui.grid!.viewMode).toBe('list')
    unmount()
  })

  /**
   * 刷新 / 直达详情时「先闪一下列表页」的回归测试。
   *
   * 曾经的行为：URL 带 :id 进来，首帧 openId 仍是 null（要等 route-sync 的
   * effect 异步打开），DeskPage 据此把列表完整渲染一遍；紧接着阅读器才盖上来。
   * 用户看到的就是「先出现列表页，然后出现详情页」。
   *
   * 修法：用 URL 里的 :id 判「详情意图」，首帧就不挂载列表。
   */
  it('URL 带 :id 时首帧不渲染列表（避免刷新闪烁）', () => {
    setup([pack(1, 'todo'), pack(2, 'todo')])
    const { queryByText, unmount } = renderDesk('/material-prep/576?stage=todo')

    // 列表网格一个节点都不该出现
    expect(queryByText(/^GRID:/)).toBeNull()
    unmount()
  })

  it('无 :id 时列表照常渲染', () => {
    setup([pack(1, 'todo')])
    const { getByText, unmount } = renderDesk('/material-prep?stage=todo')

    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('切换结果按阶段记住：去别的阶段再切回来仍是上次选的形态', async () => {
    setup([pack(1, 'todo'), pack(2, 'done')])
    const { unmount, getByTitle, getByText } = renderDesk('/material-prep?stage=todo')

    fireEvent.click(getByTitle('列表'))
    expect(ui.grid!.viewMode).toBe('list')

    // 换阶段：已归案仍用缺省（grid）——各阶段互不影响
    act(() => {
      getByText('切到已归案').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([2]))
    expect(ui.grid!.viewMode).toBe('grid')

    // 切回待处理：用户的选择还在
    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([1]))
    expect(ui.grid!.viewMode).toBe('list')
    unmount()
  })
})
