// @vitest-environment jsdom
/**
 * AppNavbar（全局顶层导航）组件渲染单测（jsdom）。
 *
 * mock 边界：@/features/auth（useAuth 桩）、@/lib/api（organization/me 补拉）、
 * @/features/search（GlobalSearch 桩）、@/features/material-prep 对外出口的
 * resetMaterialPrepState 与 @/lib/pdf（登出时的动态 import 清理点——调用断言的核心）。
 * 覆盖：品牌/导航渲染、检索按钮与 searchOpen 受控契约（⌘K 快捷键在壳层，
 * 见 App.dom.test）、无用户名时补拉 me 并回填 store、新建案件回调、
 * 登出全链路（store 登出 + query 缓存清空 + 阅读器/PDF 缓存清理 + 跳转 /login）、
 * 账号绑定入口跳转、导航入口的悬停预取与点击乐观高亮（目标页 chunk 未到、
 * 路由 transition 挂起期间被点的标签先行高亮，旧页面保持不退回 fallback）、
 * 手机端「…」溢出菜单（分组 / 可访问名区分 / 全局检索等入口的接线）。
 */
import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  authState: {
    user: null as { id: number; username: string } | null,
    setUser: vi.fn(),
    logout: vi.fn(),
  },
  resetAll: vi.fn(),
  clearPdfCache: vi.fn(),
  jsonMock: vi.fn(),
}))

vi.mock('@/features/auth', () => ({
  useAuth: (sel: (s: typeof stubs.authState) => unknown) => sel(stubs.authState),
}))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  // 只替换断言用到的 api；其余导出保持真实，否则任一 feature 新增客户端工厂都会打红本档。
  return { ...actual, api: { get: vi.fn(() => ({ json: stubs.jsonMock })) } }
})
vi.mock('@/features/search', () => ({
  GlobalSearch: ({ open }: { open: boolean }) => <div>{open ? 'gs-open' : 'gs-closed'}</div>,
}))
// AppNavbar 登出走 feature 出口的 resetMaterialPrepState（内部再动态 import store），
// mock 边界跟着上提到出口——不再穿透内部 store 路径
vi.mock('@/features/material-prep', () => ({
  resetMaterialPrepState: stubs.resetAll,
}))
vi.mock('@/lib/pdf', () => ({
  clearPdfCache: stubs.clearPdfCache,
}))

import { api } from '@/lib/api'

import { AppNavbar } from './AppNavbar'

const apiGetMock = vi.mocked(api.get)

const onNotify = vi.fn()
const onLogout = vi.fn()
const onSearchOpenChange = vi.fn()

function setupUi({ searchOpen = false }: { searchOpen?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const clearSpy = vi.spyOn(queryClient, 'clear')
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <AppNavbar
          onNotify={onNotify}
          onLogout={onLogout}
          searchOpen={searchOpen}
          onSearchOpenChange={onSearchOpenChange}
        />
        <Routes>
          <Route path="/" element={null} />
          <Route path="/login" element={<div>login-page</div>} />
          <Route path="/settings" element={<div>bindings-page</div>} />
          <Route path="/projects" element={<div>projects-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, clearSpy }
}

/** radix DropdownMenu 在 jsdom 下用 pointerDown(button=0) 打开 */
function openUserMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: '用户菜单' }), { button: 0, ctrlKey: false })
}

/** 手机端「…」溢出菜单的触发器（桌面端同名按钮被媒体查询隐藏，但 jsdom 仍找得到） */
function openMoreMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: '更多操作' }), { button: 0, ctrlKey: false })
}

beforeEach(() => {
  vi.clearAllMocks()
  stubs.authState.user = { id: 1, username: '张律师' }
  stubs.jsonMock.mockResolvedValue({ id: 1, username: '张律师' })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('AppNavbar 渲染与全局检索', () => {
  it('渲染品牌、三个导航入口（首页/预处理/项目）与检索按钮', () => {
    setupUi()
    expect(screen.getByText('法穿')).toBeTruthy()
    expect(screen.getByText('SI Copilot')).toBeTruthy()
    expect(screen.getByRole('link', { name: '首页' })).toBeTruthy()
    expect(screen.getByRole('link', { name: '预处理' })).toBeTruthy()
    expect(screen.getByRole('link', { name: '项目' })).toBeTruthy()
    // 收件箱已并入预处理：不应再出现独立的一级入口
    expect(screen.queryByRole('link', { name: '收件箱' })).toBeNull()
    expect(screen.getByRole('button', { name: /检索/ })).toBeTruthy()
    expect(screen.getByText('张律师')).toBeTruthy()
  })

  it('检索受控契约：searchOpen 驱动 GlobalSearch，点按钮回调 onSearchOpenChange(true)', () => {
    // ⌘K 快捷键已上提壳层（与 AI 助手互斥）；导航栏只负责按钮入口与透传 open
    setupUi({ searchOpen: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /检索/ }))
    expect(onSearchOpenChange).toHaveBeenCalledWith(true)

    cleanup()
    setupUi()
    expect(screen.getByText('gs-closed')).toBeTruthy()
  })

  it('store 无用户名时：补拉 organization/me 并回填（setUser）', async () => {
    stubs.authState.user = { id: 0, username: '' }
    stubs.jsonMock.mockResolvedValue({ id: 7, username: '李律师' })
    setupUi()
    await waitFor(() => expect(apiGetMock).toHaveBeenCalledWith('organization/me'))
    await waitFor(() => expect(stubs.authState.setUser).toHaveBeenCalledWith({ id: 7, username: '李律师' }))
  })

  it('已有用户名时：不再补拉 organization/me', () => {
    setupUi()
    expect(apiGetMock).not.toHaveBeenCalled()
  })

  it('新建项目：打开新建对话框（不再是 toast 占位）', async () => {
    setupUi()
    fireEvent.click(screen.getByRole('button', { name: /新建项目/ }))
    // 此前这个按钮只弹一句「可先把材料上传到材料预处理归案」——等于告诉用户这里做不了。
    // 现在是真对话框：能建空白项目，也能从示例模板开始。
    expect(await screen.findByText('新建项目', { selector: '[role="dialog"] *' })).toBeTruthy()
    // 用精确文本：说明段落里也有「从示例开始」四个字，正则匹配会撞到两个
    expect(screen.getByText('从示例开始（可选）')).toBeTruthy()
  })
})

describe('AppNavbar 手机端溢出菜单', () => {
  it('按 导航 / 动作 / 账户 三组列出全部手机入口，条目与组间分隔符合规范', async () => {
    setupUi()
    // 桌面按钮保持原名（先在菜单打开前确认；菜单展开后 radix 会把外部内容
    // 标记 aria-hidden，按名字就查不到了）
    expect(screen.getByRole('button', { name: '全局检索' })).toBeTruthy()
    openMoreMenu()

    // 三组小标题
    for (const title of ['导航', '动作', '账户']) {
      expect(await screen.findByText(title, { selector: '[data-slot="dropdown-menu-label"]' })).toBeTruthy()
    }

    // 每条目的可访问名都带「（菜单）」：桌面按钮同时在 DOM 里（jsdom 不跑媒体查询），
    // 同名会 getByRole 命中两个。这里把名字显式钉死。
    const items = [
      '首页（菜单）',
      '预处理（菜单）',
      '项目（菜单）',
      '新建项目（菜单）',
      '全局检索（菜单）',
      '设置（菜单）',
      '退出登录（菜单）',
    ]
    for (const name of items) {
      const item = screen.getByRole('menuitem', { name })
      // 触控目标 ≥44px：手机上没有 hover，条目太窄会点错
      expect(item.className).toContain('min-h-11')
    }
    // 菜单项必须带后缀，不能撞上桌面按钮的无后缀名
    expect(screen.queryByRole('menuitem', { name: '全局检索' })).toBeNull()

    // 组间分隔：两条 border-t 细线
    const dividers = document.querySelectorAll('[data-slot="dropdown-menu-separator"]')
    expect(dividers).toHaveLength(2)
    dividers.forEach((el) => expect(el.className).toContain('border-t border-border'))
  })

  it('「全局检索」是手机唯一入口：点击打开检索面板', async () => {
    setupUi()
    openMoreMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: '全局检索（菜单）' }))
    expect(onSearchOpenChange).toHaveBeenCalledWith(true)
  })

  it('「设置」跳转 /settings', async () => {
    setupUi()
    openMoreMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: '设置（菜单）' }))
    expect(await screen.findByText('bindings-page')).toBeTruthy()
  })

  it('「新建项目」打开真实新建对话框', async () => {
    setupUi()
    openMoreMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: '新建项目（菜单）' }))
    expect(await screen.findByText('新建项目', { selector: '[role="dialog"] *' })).toBeTruthy()
  })

  it('「退出登录」走现有确认弹窗（不能点一下直接登出）', async () => {
    setupUi()
    openMoreMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: '退出登录（菜单）' }))
    expect(await screen.findByText('确认退出登录？')).toBeTruthy()
    expect(stubs.authState.logout).not.toHaveBeenCalled()
  })

  it('导航组条目复用桌面导航的跳转与乐观高亮', async () => {
    setupUi()
    openMoreMenu()
    fireEvent.click(await screen.findByRole('menuitem', { name: '项目（菜单）' }))
    expect(await screen.findByText('projects-page')).toBeTruthy()
    // 路由提交后桌面导航的对应标签也高亮（同一个 navPath）
    expect(screen.getByRole('link', { name: '项目' }).getAttribute('aria-current')).toBe('page')
  })
})

describe('AppNavbar 用户菜单与登出', () => {
  it('登出全链路：确认弹窗 → store 登出 + 三处缓存清理 + 跳转 /login + onLogout', async () => {
    const { clearSpy } = setupUi()
    openUserMenu()
    fireEvent.click(await screen.findByText('退出登录', { selector: '[role="menuitem"]' }))

    expect(await screen.findByText('确认退出登录？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))

    await waitFor(() => expect(stubs.authState.logout).toHaveBeenCalled())
    expect(clearSpy).toHaveBeenCalled()
    // 动态 import 的两个清理点：阅读器状态 + PDF 缓存
    await waitFor(() => expect(stubs.resetAll).toHaveBeenCalled())
    await waitFor(() => expect(stubs.clearPdfCache).toHaveBeenCalled())
    expect(await screen.findByText('login-page')).toBeTruthy()
    expect(onLogout).toHaveBeenCalled()
  })

  it('登出确认弹窗可取消：不触发任何登出副作用', async () => {
    const { clearSpy } = setupUi()
    openUserMenu()
    fireEvent.click(await screen.findByText('退出登录', { selector: '[role="menuitem"]' }))

    expect(await screen.findByText('确认退出登录？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => expect(screen.queryByText('确认退出登录？')).toBeNull())
    expect(stubs.authState.logout).not.toHaveBeenCalled()
    expect(clearSpy).not.toHaveBeenCalled()
    expect(stubs.resetAll).not.toHaveBeenCalled()
    expect(screen.queryByText('login-page')).toBeNull()
  })

  it('菜单「设置」跳转 /settings', async () => {
    setupUi()
    openUserMenu()
    fireEvent.click(await screen.findByText('设置', { selector: '[role="menuitem"]' }))
    expect(await screen.findByText('bindings-page')).toBeTruthy()
  })
})

/** 当前路由探针：把 pathname 打到 DOM 上，区分「乐观高亮」与「路由真正提交」 */
function PathProbe() {
  return <div>path:{useLocation().pathname}</div>
}

/** 永不 resolve 的懒加载页：模拟目标 chunk 还在下载，路由 transition 一直挂起 */
const NeverReadyPage = lazy(() => new Promise<{ default: () => null }>(() => {}))

function setupNav() {
  const onPrefetch = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <AppNavbar
          onPrefetch={onPrefetch}
          searchOpen={false}
          onSearchOpenChange={onSearchOpenChange}
        />
        <PathProbe />
        <Suspense fallback={<div>route-fallback</div>}>
          <Routes>
            <Route path="/" element={<div>home-page</div>} />
            <Route path="/material-prep" element={<div>desk-page</div>} />
            <Route path="/projects" element={<NeverReadyPage />} />
          </Routes>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { onPrefetch }
}

const current = (name: string) => screen.getByRole('link', { name }).getAttribute('aria-current')

describe('AppNavbar 导航入口：预取与乐观高亮', () => {
  it('悬停 / 聚焦导航入口即回调 onPrefetch(目标路径)', () => {
    const { onPrefetch } = setupNav()
    fireEvent.mouseEnter(screen.getByRole('link', { name: '预处理' }))
    expect(onPrefetch).toHaveBeenCalledWith('/material-prep')
    fireEvent.focus(screen.getByRole('link', { name: '项目' }))
    expect(onPrefetch).toHaveBeenCalledWith('/projects')
  })

  it('点击导航入口：路由跳转并高亮目标，原入口取消高亮', async () => {
    setupNav()
    expect(current('首页')).toBe('page')
    fireEvent.click(screen.getByRole('link', { name: '预处理' }))
    expect(await screen.findByText('desk-page')).toBeTruthy()
    expect(screen.getByText('path:/material-prep')).toBeTruthy()
    expect(current('预处理')).toBe('page')
    expect(current('首页')).toBeNull()
  })

  it('目标页 chunk 未到：被点标签先行高亮，旧页面保持、不退回 fallback、pathname 未变', async () => {
    setupNav()
    fireEvent.click(screen.getByRole('link', { name: '项目' }))
    // 乐观高亮是同步提交的高优先级更新，transition 挂起期间就应生效
    await waitFor(() => expect(current('项目')).toBe('page'))
    expect(current('首页')).toBeNull()
    // transition 被 React 保住：旧内容仍在、fallback 不出现、真实路由尚未提交
    expect(screen.getByText('home-page')).toBeTruthy()
    expect(screen.queryByText('route-fallback')).toBeNull()
    expect(screen.getByText('path:/')).toBeTruthy()
  })

  it('带修饰键点击（开新标签等）不接管：不跳转、不抢先高亮', () => {
    // 交给浏览器默认行为后，jsdom 会报「navigation not implemented」，与断言无关
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    setupNav()
    fireEvent.click(screen.getByRole('link', { name: '预处理' }), { metaKey: true })
    expect(screen.getByText('home-page')).toBeTruthy()
    expect(screen.getByText('path:/')).toBeTruthy()
    expect(current('首页')).toBe('page')
    expect(current('预处理')).toBeNull()
    errorSpy.mockRestore()
  })
})
