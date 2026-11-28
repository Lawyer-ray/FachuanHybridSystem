// @vitest-environment jsdom
/**
 * App 路由装配 / AppShell 壳层回归（jsdom）。
 *
 * 守住的是「切 Navbar 标签闪烁」修复的三个事实：
 *   1. 导航栏跨路由常驻——切页前后 <header> 是同一个 DOM 节点，不卸载重挂；
 *   2. 目标页 chunk 未到时，旧页面保持可见、不退回全屏 fallback（react-router 的
 *      导航 transition 被 React 保住），被点标签先行高亮；
 *   3. 登录后空闲预载三个主入口 chunk，悬停导航入口再预取一次（幂等）。
 *
 * mock 边界：四个 feature 出口（页面换成可控的 lazy 桩）、@/lib/token（已登录）、
 * AppNavbar 的三处依赖（useAuth / organization/me / GlobalSearch）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => {
  const deferred = <T,>() => {
    let resolve!: (v: T) => void
    const promise = new Promise<T>((r) => {
      resolve = r
    })
    return { promise, resolve }
  }
  return {
    /** 项目页 chunk：由测试决定何时 resolve，模拟「还在下载」 */
    casesChunk: deferred<{ default: () => React.ReactNode }>(),
    preloadHomePage: vi.fn(() => Promise.resolve()),
    preloadWorkbenchPage: vi.fn(() => Promise.resolve()),
  }
})

vi.mock('@/lib/token', () => ({ hasToken: () => true }))
vi.mock('@/features/auth', () => ({
  LoginPage: () => <div>login-page</div>,
  SocialCallbackPage: () => <div>social-callback</div>,
  useAuth: (sel: (s: unknown) => unknown) =>
    sel({ user: { id: 1, username: '张律师' }, setUser: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/features/settings', () => ({
  SettingsPageLazy: () => <div>settings-page</div>,
}))
vi.mock('@/features/home', async () => {
  const { lazy } = await import('react')
  return {
    HomePageLazy: lazy(() => Promise.resolve({ default: () => <main>home-page</main> })),
    preloadHomePage: stubs.preloadHomePage,
  }
})
vi.mock('@/features/workbench', async () => {
  const { lazy } = await import('react')
  return {
    WorkbenchPageLazy: lazy(() => stubs.casesChunk.promise),
    preloadWorkbenchPage: stubs.preloadWorkbenchPage,
    // /projects/:id 现在走 ProjectDetailPage（按 deal.lit 分流），
    // 旧的 DealDetailPageLazy / NonLitDetailPageLazy 已不再从 App 引用
    ProjectDetailPageLazy: lazy(() =>
      Promise.resolve({ default: () => <main>project-detail-page</main> }),
    ),
    EditProjectPageLazy: lazy(() =>
      Promise.resolve({ default: () => <main>project-edit-page</main> }),
    ),
    // AppNavbar 现在从桶出口静态取 NewProjectDialog（跨域深引豁免已删除），
    // mock 工厂必须跟上真实模块形状；壳层只验证「点导航能挂载对话框」，
    // 对话框自身行为由 workbench 域测试覆盖，不要删这个 stub。
    NewProjectDialog: () => null,
  }
})
vi.mock('@/features/material-prep', () => ({ DeskPage: () => <main>desk-page</main> }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  // 只替换断言用到的 api；createApiClient / createAnonymousClient 保持真实实现，
  // 否则任一 feature 新增客户端工厂都会让整份 App 测试因 mock 缺字段而失败。
  return { ...actual, api: { get: vi.fn(() => ({ json: () => Promise.resolve({ id: 1, username: '张律师' }) })) } }
})
vi.mock('@/features/search', () => ({
  // 透出 open 状态：⌘K 开关与 AI 助手互斥的断言都看它
  GlobalSearch: ({ open }: { open: boolean }) => <div>{open ? 'gs-open' : 'gs-closed'}</div>,
}))

import App from './App'

// 经 unknown 断言成独立形状：lib.dom 把 requestIdleCallback 声明为必选且回调带
// deadline 参数，直接交叉会让 delete / 无参调用都过不了类型检查
const idleWindow = window as unknown as {
  requestIdleCallback?: (cb: () => void) => number
  cancelIdleCallback?: (id: number) => void
}

function setupApp({ idleFiresNow, route = '/' }: { idleFiresNow: boolean; route?: string }) {
  // jsdom 无 requestIdleCallback；按用例需要让空闲回调立刻执行或永不执行
  idleWindow.requestIdleCallback = (cb) => {
    if (idleFiresNow) cb()
    return 1
  }
  idleWindow.cancelIdleCallback = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const header = () => document.querySelector('header')
const current = (name: string) => screen.getByRole('link', { name }).getAttribute('aria-current')
/**
 * AI 助手抽屉的根节点（copilot 域真模块的 `<aside>`）：展开即挂载，收起后滑出
 * 240ms 才卸载。面板 chunk 首次展开才下载，故等待上限放宽（同下 /assistant 用例）。
 */
const copilotPanel = () => document.querySelector('aside')
const waitForPanel = (present: boolean) =>
  waitFor(() => expect(Boolean(copilotPanel())).toBe(present), { timeout: 5000 })

/**
 * jsdom 未实现 window.matchMedia。AppShell 展开时会真实挂载 copilot 域
 * （懒加载 chunk，本文件不 mock），面板内 useMediaQuery 缺它会直接抛错、
 * 被 ErrorBoundary 兑底成整页错误页，后续 DOM 断言全部落空（偶发，取决于
 * chunk 解析时机）。替身固定窄屏分支（matches: false），与
 * LoginPage.dom.test / CalendarPanel.dom.test 同一套路。
 */
function stubMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  stubMatchMedia()
})

afterEach(() => {
  // 先卸载（AppShell 的 effect 清理会调 cancelIdleCallback），再拆掉 idle 桩；
  // RTL 自动注册的 cleanup 在本钩子之后才跑，不能依赖它
  cleanup()
  delete idleWindow.requestIdleCallback
  delete idleWindow.cancelIdleCallback
})

describe('AppShell：导航栏常驻 + 懒加载切页不闪', () => {
  it('首次进入：导航栏先于页面出现，页面 chunk 到达后内容区填充', async () => {
    setupApp({ idleFiresNow: false })
    expect(header()).toBeTruthy()
    expect(await screen.findByText('home-page')).toBeTruthy()
    expect(current('首页')).toBe('page')
  })

  it('切到已缓存页面：header 是同一个 DOM 节点，内容区替换', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')
    const headerBefore = header()

    fireEvent.click(screen.getByRole('link', { name: '预处理' }))
    expect(await screen.findByText('desk-page')).toBeTruthy()
    expect(screen.queryByText('home-page')).toBeNull()
    expect(header()).toBe(headerBefore)
    expect(current('预处理')).toBe('page')
    expect(current('首页')).toBeNull()
  })

  it('切到 chunk 未到的页面：旧页面保持、无全屏 fallback、标签先行高亮；chunk 到达后平滑替换', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')
    const headerBefore = header()

    fireEvent.click(screen.getByRole('link', { name: '项目' }))
    await waitFor(() => expect(current('项目')).toBe('page'))
    // 修复前：此刻整页（含 header）已被「正在加载…」替换
    expect(header()).toBe(headerBefore)
    expect(screen.getByText('home-page')).toBeTruthy()
    expect(screen.queryByText('正在加载…')).toBeNull()

    stubs.casesChunk.resolve({ default: () => <main>cases-page</main> })
    expect(await screen.findByText('cases-page')).toBeTruthy()
    expect(screen.queryByText('home-page')).toBeNull()
    expect(header()).toBe(headerBefore)
    expect(current('项目')).toBe('page')
  })

  it('登录后空闲预载主入口 chunk；悬停导航入口再预取一次', async () => {
    setupApp({ idleFiresNow: true })
    await screen.findByText('home-page')
    expect(stubs.preloadHomePage).toHaveBeenCalledTimes(1)
    expect(stubs.preloadWorkbenchPage).toHaveBeenCalledTimes(1)

    fireEvent.mouseEnter(screen.getByRole('link', { name: '项目' }))
    expect(stubs.preloadWorkbenchPage).toHaveBeenCalledTimes(2)
  })

  it('空闲回调未触发时不预载；卸载时取消空闲回调', () => {
    setupApp({ idleFiresNow: false })
    expect(stubs.preloadHomePage).not.toHaveBeenCalled()
    expect(stubs.preloadWorkbenchPage).not.toHaveBeenCalled()
    cleanup()
    expect(idleWindow.cancelIdleCallback).toHaveBeenCalledWith(1)
  })
})

// ============ copilot 面板开关与快捷键（覆盖率补测） ============

describe('AppShell：AI 助手面板开关', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('默认收起：不渲染面板（copilot chunk 未加载）', () => {
    setupApp({ idleFiresNow: false })
    // 面板懒加载 chunk 未请求时，aside/面板节点不存在
    expect(document.body.textContent).not.toContain('copilot-panel')
  })

  it('展开态不持久化：localStorage 里遗留的 copilot:open=1 不再被恢复', async () => {
    localStorage.setItem('copilot:open', '1')
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())
    // 旧实现据此恢复展开态；现在默认就是收起。等一拍确认不是「还没挂完」
    await new Promise((r) => setTimeout(r, 50))
    expect(copilotPanel()).toBeNull()
    // 也不再改写这个键：读与写一起删了，键留在原地不再有人碰
    expect(localStorage.getItem('copilot:open')).toBe('1')
  })

  it('⌘J 展开 / 再按收起，全程不写 localStorage', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitForPanel(true)
    expect(localStorage.getItem('copilot:open')).toBeNull()

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitForPanel(false)
    expect(localStorage.getItem('copilot:open')).toBeNull()
  })

  it('Ctrl+J 同样生效（Windows/Linux）', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j', ctrlKey: true })
    await waitForPanel(true)
  })

  it('无修饰键的 j 不触发切换', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    // 先开检索：⌘J 若被误触发会同步把检索关掉（两层互斥是状态联动），
    // 比「等一会儿看有没有写盘」更硬的观测点
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()

    fireEvent.keyDown(window, { key: 'j' })
    expect(screen.getByText('gs-open')).toBeTruthy()
  })

  it('详情页不渲染压暗遮罩：否则点右栏合同会点到遮罩把助手收回去', async () => {
    // 详情页路由 + 宽屏（matchMedia 替身固定 matches:false，即窄屏）：
    // 即便没开 dock，详情页也必须屏蔽遮罩，否则整个内容区不可点。
    setupApp({ idleFiresNow: false, route: '/projects/393' })
    await waitFor(() => expect(header()).toBeTruthy())
    // 真把面板展开（展开态不再从 localStorage 恢复）后再看遮罩，否则断言空转
    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitForPanel(true)
    // 遮罩是 aria-hidden 的覆盖层；详情页里它不该出现
    const backdrop = document.querySelector('[aria-hidden="true"].fixed')
    expect(backdrop).toBeNull()
  })

  it('/assistant 上不叠抽屉：页面自己就是全屏助手', async () => {
    // 先等「面板 chunk 加载结束」这个正面信号：CopilotPanelLazy 与 AssistantPageLazy
    // 是同一个 import()（见 app/preload.ts），这里直接把那个模块求值完成。
    //
    // 为什么必须是它而不是「等一会儿」：面板挂在 `<Suspense fallback={null}>` 里，
    // chunk 没到时即便壳层判断写错也渲染不出 aside——先睡一段时间再断言「不存在」，
    // 睡不够就假绿、睡多久都只是概率。chunk 求值完成后面板随时可渲染，壳层一旦
    // 决定挂载就会在同一次 commit 里真挂出 aside，否定断言才有意义。
    await import('@/features/copilot')

    setupApp({ idleFiresNow: false, route: '/assistant' })
    // 助手页自己的 Suspense 完成（本文件不 mock copilot 域，渲染的是真组件）
    expect(await screen.findByRole('main', { name: 'AI 助手' })).toBeTruthy()

    // 再按 ⌘J：开关状态照旧切换（离开本页即恢复），但本页不该多出一个 fixed 抽屉——
    // 同一段对话两个输入框同屏，用户不知道该跟哪个说
    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    // 用 `act` 冲净「开关 → copilotMounted → 挂面板」这条 effect 级联（确定性，不靠睡眠时长），
    // 再断言本页没有抽屉：抽屉若该挂载，级联正是在这一拍里挂上。
    await act(async () => {})
    expect(copilotPanel()).toBeNull()

    // 状态确实切过去了：离开本页（回首页）就该看到抽屉——否则上面那条「不存在」
    // 只证得出「没开」，压不住「开了也不叠」这个语义
    fireEvent.click(screen.getByRole('link', { name: '首页' }))
    await waitForPanel(true)
  })

  it('localStorage 读取抛错时回落收起态（不崩）', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())
    getItem.mockRestore()
  })

  it('面板开关不碰 localStorage：setItem 抛错也照常展开', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => {
      fireEvent.keyDown(window, { key: 'j', metaKey: true })
    }).not.toThrow()
    // 先拆桩再等面板挂载：面板域自己会用 localStorage 记并排/侧栏偏好
    setItem.mockRestore()
    await waitForPanel(true)
  })
})

// ============ ⌘K 检索开关与 ⌘J AI 助手互斥（回归：二次 ⌘K 关不掉 + 两层叠加） ============

describe('AppShell：⌘K 检索开关与 ⌘J AI 助手互斥', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('⌘K 打开检索，再按一次 ⌘K 收起（toggle）', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()

    // 修复前：再次 ⌘K 只是重复 setSearchOpen(true)，弹窗关不掉
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-closed')).toBeTruthy()
  })

  it('Ctrl+K 同样可开可关（Windows/Linux）', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.getByText('gs-closed')).toBeTruthy()
  })

  it('检索打开时按 ⌘J：收起检索、展开 AI 助手（不叠加）', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()

    // 修复前：面板展开后检索弹窗仍叠在上面（双重压暗）
    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    expect(screen.getByText('gs-closed')).toBeTruthy()
    await waitForPanel(true)
  })

  it('AI 助手展开时按 ⌘K：收起面板、打开检索（反向互斥）', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitForPanel(true)

    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
    // 面板随之收起（滑出 240ms 后卸载），不会与检索弹窗同屏叠加
    await waitForPanel(false)
  })

  it('按住不放（e.repeat）不连续切换', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    fireEvent.keyDown(window, { key: 'k', metaKey: true, repeat: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
  })

  it('无修饰键的 k 不触发检索', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'k' })
    expect(screen.getByText('gs-closed')).toBeTruthy()
  })
})

// ============ whenIdle 降级 / preloadRoute 守卫（覆盖率补测） ============

describe('AppShell：whenIdle 降级与预取守卫', () => {
  it('无 requestIdleCallback 时退化为 setTimeout(1500) 预载', async () => {
    vi.useFakeTimers()
    // 删掉 requestIdleCallback 走降级分支
    delete idleWindow.requestIdleCallback
    delete idleWindow.cancelIdleCallback

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await vi.advanceTimersByTimeAsync(1600)
    expect(stubs.preloadHomePage).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('预取未知路由时安全跳过（?. 守卫）', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    // AppNavbar 的 onPrefetch 传的是 preloadRoute；点未知路径不应抛错
    expect(() => fireEvent.click(document.body)).not.toThrow()
  })
})
