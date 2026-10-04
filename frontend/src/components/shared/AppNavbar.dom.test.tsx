// @vitest-environment jsdom
/**
 * AppNavbar（全局顶层导航）组件渲染单测（jsdom）。
 *
 * mock 边界：@/features/auth（useAuth 桩）、@/lib/api（organization/me 补拉）、
 * @/features/search（GlobalSearch 桩）、@/features/material-prep/store 与 @/lib/pdf
 * （登出时的动态 import 清理点——调用断言的核心）。覆盖：品牌/导航渲染、
 * ⌘K 唤起检索、无用户名时补拉 me 并回填 store、新建案件回调、
 * 登出全链路（store 登出 + query 缓存清空 + 阅读器/PDF 缓存清理 + 跳转 /login）、
 * 账号绑定入口跳转。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
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
vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(() => ({ json: stubs.jsonMock })),
  },
}))
vi.mock('@/features/search', () => ({
  GlobalSearch: ({ open }: { open: boolean }) => <div>{open ? 'gs-open' : 'gs-closed'}</div>,
}))
vi.mock('@/features/material-prep/store', () => ({
  useReader: {
    getState: () => ({ resetAll: stubs.resetAll }),
  },
}))
vi.mock('@/lib/pdf', () => ({
  clearPdfCache: stubs.clearPdfCache,
}))

import { api } from '@/lib/api'

import { AppNavbar } from './AppNavbar'

const apiGetMock = vi.mocked(api.get)

const onNotify = vi.fn()
const onLogout = vi.fn()

function setupUi() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const clearSpy = vi.spyOn(queryClient, 'clear')
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <AppNavbar onNotify={onNotify} onLogout={onLogout} />
        <Routes>
          <Route path="/" element={null} />
          <Route path="/login" element={<div>login-page</div>} />
          <Route path="/settings/bindings" element={<div>bindings-page</div>} />
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

beforeEach(() => {
  vi.clearAllMocks()
  stubs.authState.user = { id: 1, username: '张律师' }
  stubs.jsonMock.mockResolvedValue({ id: 1, username: '张律师' })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('AppNavbar 渲染与全局检索', () => {
  it('渲染品牌、三个导航入口与检索按钮', () => {
    setupUi()
    expect(screen.getByText('法穿')).toBeTruthy()
    expect(screen.getByText('SI Copilot')).toBeTruthy()
    expect(screen.getByRole('link', { name: '首页' })).toBeTruthy()
    expect(screen.getByRole('link', { name: '材料预处理' })).toBeTruthy()
    expect(screen.getByRole('link', { name: '办案' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /检索/ })).toBeTruthy()
    expect(screen.getByText('张律师')).toBeTruthy()
  })

  it('⌘K 唤起全局检索，未触发时保持关闭', () => {
    setupUi()
    expect(screen.getByText('gs-closed')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(screen.getByText('gs-open')).toBeTruthy()
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

  it('新建案件：走 onNotify 提示回调', () => {
    setupUi()
    fireEvent.click(screen.getByRole('button', { name: /新建案件/ }))
    expect(onNotify).toHaveBeenCalledWith('新建案件：可先把材料上传到「材料预处理」归案')
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

  it('菜单「账号绑定」跳转 /settings/bindings', async () => {
    setupUi()
    openUserMenu()
    fireEvent.click(await screen.findByText('账号绑定', { selector: '[role="menuitem"]' }))
    expect(await screen.findByText('bindings-page')).toBeTruthy()
  })
})
