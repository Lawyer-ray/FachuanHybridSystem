// @vitest-environment jsdom
/**
 * BindingsPage（账号绑定设置页）组件渲染单测（jsdom）。
 *
 * mock 边界：./social-api（socialBindingsApi 四个方法）、sonner（toast 断言）、
 * AppNavbar（子组件桩）。覆盖：加载/失败重载、三种行形态（已绑定/可绑定/未开放）、
 * 空目录、解绑确认流程（成功 toast + 失败 toast）、bound 回调参数清理（一次性提示）、
 * 绑定弹窗打开。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./social-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./social-api')>()
  return {
    ...actual,
    socialBindingsApi: {
      list: vi.fn(),
      catalog: vi.fn(),
      unbind: vi.fn(),
      createBindSession: vi.fn(),
    },
  }
})
vi.mock('sonner', () => {
  const toast = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() })
  return { toast }
})
vi.mock('@/components/shared/AppNavbar', () => ({
  AppNavbar: () => <nav>navbar-stub</nav>,
}))

import { socialBindingsApi, type BoundAccount, type SocialProviderInfo } from './social-api'
import { toast } from 'sonner'

import { BindingsPage } from './BindingsPage'

const listMock = vi.mocked(socialBindingsApi.list)
const catalogMock = vi.mocked(socialBindingsApi.catalog)
const unbindMock = vi.mocked(socialBindingsApi.unbind)

const feishu: SocialProviderInfo = {
  name: 'feishu',
  display_name: '飞书',
  login_mode: 'embedded_qr',
  client_config: { app_id: 'cli_x', authorize_url: 'https://open.feishu.cn/a', scope: 's' },
}
const github: SocialProviderInfo = {
  name: 'github',
  display_name: 'GitHub',
  login_mode: 'redirect',
  client_config: { app_id: 'gh', authorize_url: 'https://github.com/login/oauth/authorize' },
}
const dingtalk: SocialProviderInfo = {
  name: 'dingtalk',
  display_name: '钉钉',
  login_mode: 'redirect',
  client_config: null,
}

const boundFeishu: BoundAccount = {
  provider: 'feishu',
  display_name: '张三',
  avatar_url: '',
  bound_at: '2026-09-01T10:00:00',
}

/** 记录路由变化（观察 bound 参数清理是否走 replace 且不带残留 query） */
const locHistory: Array<{ pathname: string; search: string }> = []
function LocProbe() {
  const loc = useLocation()
  locHistory.push({ pathname: loc.pathname, search: loc.search })
  return null
}

function setupUi(initialEntry = '/settings/bindings') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocProbe />
        <Routes>
          <Route path="/settings/bindings" element={<BindingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  listMock.mockResolvedValue([boundFeishu])
  catalogMock.mockResolvedValue([feishu, github, dingtalk])
  unbindMock.mockResolvedValue({ success: true })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('BindingsPage 加载与错误态', () => {
  it('加载中：展示加载文案，不出列表行', () => {
    listMock.mockReturnValue(new Promise(() => {}))
    setupUi()
    expect(screen.getByText('正在加载…')).toBeTruthy()
    expect(screen.queryByText('飞书')).toBeNull()
  })

  it('接口失败：显式报错并给重新加载；点击后重新请求', async () => {
    listMock.mockRejectedValueOnce(new Error('500')).mockResolvedValue([boundFeishu])
    setupUi()
    expect(await screen.findByText('加载绑定信息失败，请检查网络后重试')).toBeTruthy()
    const calls = listMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))
    await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThan(calls))
  })

  it('目录为空：展示暂无可绑定的登录方式', async () => {
    listMock.mockResolvedValue([])
    catalogMock.mockResolvedValue([])
    setupUi()
    expect(await screen.findByText('暂无可绑定的登录方式')).toBeTruthy()
  })
})

describe('BindingsPage 行渲染三种形态', () => {
  it('已绑定：显示账号与绑定时间 + 解绑按钮；未绑定可用：给绑定按钮；未配置：灰态无按钮', async () => {
    setupUi()
    expect(await screen.findByText('飞书')).toBeTruthy()
    expect(screen.getByText('GitHub')).toBeTruthy()
    expect(screen.getByText('钉钉')).toBeTruthy()

    // 飞书：已绑定，展示账号名与绑定时间，操作 = 解绑
    expect(screen.getByText('张三', { exact: false })).toBeTruthy()
    expect(screen.getByText(/绑定于/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '解绑' })).toBeTruthy()

    // GitHub：未绑定且已配置 → 绑定入口
    expect(screen.getByText('未绑定')).toBeTruthy()
    expect(screen.getByRole('button', { name: '绑定' })).toBeTruthy()

    // 钉钉：client_config 为 null → 灰态说明，无任何操作按钮
    expect(screen.getByText('该登录方式暂未开放')).toBeTruthy()
    // 解绑 / 绑定按钮各只有一枚（来自飞书 / GitHub），钉钉无操作
    expect(screen.getAllByRole('button').filter((b) => b.textContent === '解绑')).toHaveLength(1)
    expect(screen.getAllByRole('button').filter((b) => b.textContent === '绑定')).toHaveLength(1)
  })
})

describe('BindingsPage 解绑流程', () => {
  it('点解绑先弹确认框；确认后调 unbind 并 toast 成功', async () => {
    setupUi()
    await screen.findByText('飞书')
    fireEvent.click(screen.getByRole('button', { name: '解绑' }))

    const dialog = await screen.findByRole('alertdialog')
    // 确认标题用 provider 标识名（feishu），不是展示名
    expect(within(dialog).getByText('确认解绑feishu？')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: '解绑' }))

    await waitFor(() => expect(unbindMock).toHaveBeenCalledWith('feishu'))
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledWith('已解绑'))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })

  it('解绑业务失败（success:false）：toast 错误信息，确认框关闭', async () => {
    unbindMock.mockResolvedValue({ success: false, message: '尚未绑定该平台' })
    setupUi()
    await screen.findByText('飞书')
    fireEvent.click(screen.getByRole('button', { name: '解绑' }))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '解绑' }))
    await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalledWith('尚未绑定该平台'))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  })
})

describe('BindingsPage 绑定入口与回调参数', () => {
  it('点绑定打开绑定弹窗（redirect 型展示对应平台名）', async () => {
    setupUi()
    await screen.findByText('GitHub')
    fireEvent.click(screen.getByRole('button', { name: '绑定' }))
    expect(await screen.findByText('绑定GitHub')).toBeTruthy()
  })

  it('回调带 bound 参数：一次性成功提示 + replace 清掉参数', async () => {
    setupUi('/settings/bindings?bound=feishu')
    await waitFor(() =>
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('绑定成功，现在可以用它登录了'),
    )
    await waitFor(() => {
      const last = locHistory.at(-1)
      expect(last?.pathname).toBe('/settings/bindings')
      expect(last?.search).toBe('')
    })
  })
})
