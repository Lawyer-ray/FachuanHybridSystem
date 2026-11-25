// @vitest-environment jsdom
/**
 * DeskPage 测试的共用桩与固定装置（不单独执行：文件名不匹配 `*.test.*`）。
 *
 * 三个按被测单元拆分的测试文件（DeskPage.upload / DeskPage.judge / DeskPage.toolbar）
 * 共用这一组子组件打桩与渲染入口：DeskPage 的编排依赖全部在这里一次钉死，
 * 各测试文件只保留自己的用例，避免三份 mock 各自漂移。
 */
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { vi } from 'vitest'

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

vi.mock('../hooks/use-material-packs', () => hookMock)
// 收件箱角标走的是 inbox 子域的 hooks（不是 ../hooks/use-material-packs），单独打桩：
// 不打桩它会去要 QueryClient，而这些用例只验证 DeskPage 自己的编排逻辑。
vi.mock('../inbox/hooks/use-inbox', () => ({
  useInboxCounts: hookMock.useInboxCounts,
  useInboxList: hookMock.useInboxList,
}))
vi.mock('../inbox/hooks/use-sync-sources', () => ({ useSyncSources: syncMock.useSyncSources }))
vi.mock('../store', () => ({
  useReader: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
// 回传件待核对入口要 QueryClient（跨案件清单）。这些用例只验证 DeskPage 自己的
// 编排逻辑，与 inbox 角标同口径：打桩掉，别让一个提示组件成为 DeskPage 的测试前提。
vi.mock('../doc-verify/PendingEntry', () => ({ PendingEntry: () => null }))
vi.mock('../hooks/use-desk-keyboard', () => ({ useDeskKeyboard: vi.fn() }))
vi.mock('../hooks/use-desk-ring', () => ({
  useDeskRing: () => ({ ringRef: { current: null }, ringStyle: {} }),
}))
vi.mock('../hooks/use-desk-route-sync', () => ({ useDeskRouteSync: vi.fn() }))
// sonner v2 的 toast 是「可调用对象」：既 `toast('文案')` 也 `toast.error('文案')`。
// 只做成带方法的普通对象会漏掉前一种用法（删除成功走的就是 `toast(`${subject} 已删除`)`）。
vi.mock('sonner', () => {
  const fn = vi.fn()
  return {
    toast: Object.assign(fn, {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    }),
  }
})
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
    ui.tabs = p
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
    ui.drop = p
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

import { HTTPError } from 'ky'
import { DeskPage } from './DeskPage'

/**
 * 造一个与线上同形的 ky HTTPError。
 *
 * 为什么不能直接 `new Error('boom')`：errMessage 对裸 Error 会取它的 message
 * 当可读文案（'boom' 就原样弹给用户），而真实失败都来自 ky，HTTPError 无可用
 * data 时才回落到兜底文案。用裸 Error 测不到兜底分支。
 */
export function httpError(status: number, data?: unknown): HTTPError {
  const response = new Response(null, { status })
  const err = new HTTPError(response, new Request('http://localhost/api/v1/inbox/messages/upload'), {} as never)
  err.data = data
  return err
}

export function pack(id: number, status: 'todo' | 'done' | 'filed') {
  return { id, status, subject: `pack-${id}` }
}

export function setup(packs: unknown[] | null, over: { create?: unknown; judge?: unknown; del?: unknown } = {}) {
  hookMock.useMaterialPacks.mockReturnValue({ data: packs, isLoading: false, error: null })
  const mutateAsync = vi.fn(() => Promise.resolve({}))
  hookMock.useCreatePack.mockReturnValue({ mutateAsync: (over.create as never) ?? mutateAsync })
  hookMock.useJudgePack.mockReturnValue({ mutateAsync: (over.judge as never) ?? mutateAsync })
  const deleteMutate = (over.del as never) ?? vi.fn(() => Promise.resolve({}))
  hookMock.useDeletePack.mockReturnValue({ mutateAsync: deleteMutate, isPending: false })
  return {
    createMutate: (over.create as never) ?? mutateAsync,
    judgeMutate: (over.judge as never) ?? mutateAsync,
    deleteMutate: deleteMutate as ReturnType<typeof vi.fn>,
  }
}

/** 收件箱行：只带 countUnread 用得着的 is_read，其余字段与断言无关 */
export function inboxRow(id: number, isRead: boolean) {
  return { id, is_read: isRead, subject: `msg-${id}` }
}

/**
 * 未读数由 DeskPage 自己派生自 useInboxList（参数只含 source + search，**不含
 * unreadOnly**）。这里给它一份固定的「当前来源档位 + 搜索词下的全量行」——
 * 注意其中可以含已读行，因为按契约后端此时不受 unread_only 过滤。
 */
export function setInboxRows(rows: unknown[]) {
  hookMock.useInboxList.mockReturnValue({ data: rows, isLoading: false, error: null, refetch: vi.fn() })
}

/**
 * 统一渲染入口：DeskPage 的阶段状态存在 URL（?stage=），必须包在 Router 里。
 * 缺省 ``/material-prep?stage=todo`` —— 绝大多数用例验证的是材料包网格，
 * 而页面真实缺省阶段是「收件箱」（见 stages.ts），用例显式指明更清楚。
 */
/** 最近一次渲染时 router 的 search 串（用于断言 URL 参数是否被保留） */
const routeProbe = vi.hoisted(() => ({ search: '' }))

export function lastSearch(): string {
  return routeProbe.search
}

export function renderDesk(path = '/material-prep?stage=todo') {
  // 用 <Routes> 包一层：DeskPage 现在靠 useParams().id 判「详情意图」，
  // 裸挂载在 MemoryRouter 下拿不到参数（useParams 返回空对象），
  // 那条「首帧不渲染列表」的用例会假失败。
  /**
   * 探针：把当前 location.search 记下来。
   *
   * 需要它才能断言「切阶段时其它 query 没被抹掉」——DeskPage 自己把 location
   * 交给 MemoryRouter 管，测试里没有真实地址栏可读。
   * 定义在渲染入口内部（而不是文件顶层的 LocationProbe）：本文件要导出多个
   * 非组件辅助函数，顶层再放一个组件会触发 react-refresh 的「只导出组件」规则。
   */
  function SearchProbe() {
    const loc = useLocation()
    routeProbe.search = loc.search
    return null
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SearchProbe />
      <Routes>
        <Route path="/material-prep" element={<DeskPage />} />
        <Route path="/material-prep/:id" element={<DeskPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** 每个用例前重置全部桩与固定装置（原 DeskPage.dom.test 的 beforeEach 原样搬来） */
export function resetDeskPageMocks(): void {
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
}

export { dialogs, hookMock, navSpy, storeMock, syncMock, ui }
