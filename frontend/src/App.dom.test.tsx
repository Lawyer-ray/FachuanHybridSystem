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
  BindingsPageLazy: () => <div>bindings-page</div>,
  useAuth: (sel: (s: unknown) => unknown) =>
    sel({ user: { id: 1, username: '张律师' }, setUser: vi.fn(), logout: vi.fn() }),
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
    DealDetailPageLazy: lazy(() => Promise.resolve({ default: () => <main>deal-detail-page</main> })),
    preloadDealDetailPage: vi.fn(() => Promise.resolve()),
  }
})
vi.mock('@/features/material-prep', () => ({ DeskPage: () => <main>desk-page</main> }))
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(() => ({ json: () => Promise.resolve({ id: 1, username: '张律师' }) })) },
}))
vi.mock('@/features/search', () => ({ GlobalSearch: () => null }))

import App from './App'

// 经 unknown 断言成独立形状：lib.dom 把 requestIdleCallback 声明为必选且回调带
// deadline 参数，直接交叉会让 delete / 无参调用都过不了类型检查
const idleWindow = window as unknown as {
  requestIdleCallback?: (cb: () => void) => number
  cancelIdleCallback?: (id: number) => void
}

function setupApp({ idleFiresNow }: { idleFiresNow: boolean }) {
  // jsdom 无 requestIdleCallback；按用例需要让空闲回调立刻执行或永不执行
  idleWindow.requestIdleCallback = (cb) => {
    if (idleFiresNow) cb()
    return 1
  }
  idleWindow.cancelIdleCallback = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const header = () => document.querySelector('header')
const current = (name: string) => screen.getByRole('link', { name }).getAttribute('aria-current')

beforeEach(() => {
  vi.clearAllMocks()
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

    fireEvent.click(screen.getByRole('link', { name: '材料预处理' }))
    expect(await screen.findByText('desk-page')).toBeTruthy()
    expect(screen.queryByText('home-page')).toBeNull()
    expect(header()).toBe(headerBefore)
    expect(current('材料预处理')).toBe('page')
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
