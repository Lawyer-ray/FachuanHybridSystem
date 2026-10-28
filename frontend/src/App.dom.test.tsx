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
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    /** 办案页 chunk：由测试决定何时 resolve，模拟「还在下载」 */
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
  }
})
vi.mock('@/features/material-prep', () => ({ DeskPage: () => <main>desk-page</main> }))
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(() => ({ json: () => Promise.resolve({ id: 1, username: '张律师' }) })) },
}))
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

    fireEvent.click(screen.getByRole('link', { name: '办案' }))
    await waitFor(() => expect(current('办案')).toBe('page'))
    // 修复前：此刻整页（含 header）已被「正在加载…」替换
    expect(header()).toBe(headerBefore)
    expect(screen.getByText('home-page')).toBeTruthy()
    expect(screen.queryByText('正在加载…')).toBeNull()

    stubs.casesChunk.resolve({ default: () => <main>cases-page</main> })
    expect(await screen.findByText('cases-page')).toBeTruthy()
    expect(screen.queryByText('home-page')).toBeNull()
    expect(header()).toBe(headerBefore)
    expect(current('办案')).toBe('page')
  })

  it('登录后空闲预载主入口 chunk；悬停导航入口再预取一次', async () => {
    setupApp({ idleFiresNow: true })
    await screen.findByText('home-page')
    expect(stubs.preloadHomePage).toHaveBeenCalledTimes(1)
    expect(stubs.preloadWorkbenchPage).toHaveBeenCalledTimes(1)

    fireEvent.mouseEnter(screen.getByRole('link', { name: '办案' }))
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

  it('localStorage 记忆为展开时初始即挂载', async () => {
    localStorage.setItem('copilot:open', '1')
    setupApp({ idleFiresNow: false })
    // copilot 域是真实模块（未 mock），展开后会尝试渲染；这里只验证不抛错
    await waitFor(() => expect(header()).toBeTruthy())
  })

  it('⌘J 切换面板并把状态写入 localStorage', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('1'))

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('0'))
  })

  it('Ctrl+J 同样生效（Windows/Linux）', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j', ctrlKey: true })
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('1'))
  })

  it('无修饰键的 j 不触发切换', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j' })
    await new Promise((r) => setTimeout(r, 30))
    expect(localStorage.getItem('copilot:open')).toBeNull()
  })

  it('详情页不渲染压暗遮罩：否则点右栏合同会点到遮罩把助手收回去', async () => {
    localStorage.setItem('copilot:open', '1')
    // 详情页路由 + 宽屏（matchMedia 替身固定 matches:false，即窄屏）：
    // 即便没开 dock，详情页也必须屏蔽遮罩，否则整个内容区不可点。
    setupApp({ idleFiresNow: false, route: '/projects/393' })
    await waitFor(() => expect(header()).toBeTruthy())
    // 遮罩是 aria-hidden 的覆盖层；详情页里它不该出现
    await waitFor(() => {
      const backdrop = document.querySelector('[aria-hidden="true"].fixed')
      expect(backdrop).toBeNull()
    })
  })

  it('localStorage 读取抛错时回落收起态（不崩）', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())
    getItem.mockRestore()
  })

  it('localStorage 写入抛错时仍能切换（仅不持久化）', async () => {
    setupApp({ idleFiresNow: false })
    await waitFor(() => expect(header()).toBeTruthy())

    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => {
      fireEvent.keyDown(window, { key: 'j', metaKey: true })
    }).not.toThrow()
    setItem.mockRestore()
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
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('1'))
  })

  it('AI 助手展开时按 ⌘K：收起面板（含持久化）、打开检索（反向互斥）', async () => {
    setupApp({ idleFiresNow: false })
    await screen.findByText('home-page')

    fireEvent.keyDown(window, { key: 'j', metaKey: true })
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('1'))

    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
    await waitFor(() => expect(localStorage.getItem('copilot:open')).toBe('0'))
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
