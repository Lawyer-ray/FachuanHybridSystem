// @vitest-environment jsdom
/**
 * AppShell 手机端 AI 入口（composer 形状 pill）的壳层契约（jsdom）。
 *
 * 只钉**状态条件**：pill 是整枚可点的按钮（aria-label=打开 AI 助手）、点击走
 * toggleCopilot、copilot 展开 / 助手独立页时淡出隐藏、内容区留出 pill 高度。
 * jsdom 不跑媒体查询：`min-[760px]:hidden` 在这里不会真的隐藏任何东西，
 * 「只有手机上才显示」由 tailwind 断点类（沿用仓里的 max-[760px] 约定）保证，
 * 不在 jsdom 里硬凑——同 App.dom.test 的 matchMedia 注释。
 *
 * mock 边界：AppNavbar（本文件不测导航栏）、../preload（避免拉起全部懒加载
 * 页面）、./use-copilot-shell（直接摆布 copilotOpen）、copilot 域的 store /
 * domain（AppShell 只动态 import 它们写页面描述）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const shell = vi.hoisted(() => ({ copilotOpen: false, toggleCopilot: vi.fn() }))

vi.mock('@/components/shared/AppNavbar', () => ({ AppNavbar: () => null }))
vi.mock('../preload', () => ({
  CopilotPanelLazy: () => null,
  preloadAllRoutes: vi.fn(),
  preloadRoute: vi.fn(),
  whenIdle: () => () => {},
}))
vi.mock('./use-copilot-shell', () => ({
  useCopilotShell: () => ({
    copilotOpen: shell.copilotOpen,
    copilotMounted: shell.copilotOpen,
    effectiveDocked: false,
    isXlUp: false,
    toggleCopilot: shell.toggleCopilot,
    toggleCopilotDock: vi.fn(),
    searchOpen: false,
    setSearchOpen: vi.fn(),
  }),
}))
vi.mock('@/features/copilot/store', () => ({
  useCopilot: { getState: () => ({ setPageHint: vi.fn() }) },
}))
vi.mock('@/features/copilot/domain', () => ({ describeLocation: () => '首页' }))

import { AppShell } from './AppShell'

function setup(route = '/') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<div>home-content</div>} />
          <Route path="assistant" element={<div>assistant-content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

const pill = () => screen.getByRole('button', { name: '打开 AI 助手' })

beforeEach(() => {
  vi.clearAllMocks()
  shell.copilotOpen = false
})

describe('AppShell 手机端 AI 入口（composer pill）', () => {
  it('整枚 pill 是一个按钮：点击走 toggleCopilot，文案不承诺语音输入', () => {
    setup()
    const button = pill()
    expect(button.textContent).toContain('问 AI…')
    // 我们没有语音输入：不许出现「按住说话」这类抄来的文案
    expect(button.textContent).not.toContain('按住说话')
    fireEvent.click(button)
    expect(shell.toggleCopilot).toHaveBeenCalledTimes(1)
  })

  it('形状与层级：inset-x-4 / 0.75rem + safe-area 底距 / z-[75] / 圆角 pill', () => {
    setup()
    const cls = pill().className
    expect(cls).toContain('inset-x-4')
    expect(cls).toContain('bottom-[calc(0.75rem+env(safe-area-inset-bottom))]')
    expect(cls).toContain('z-[75]')
    expect(cls).toContain('rounded-full')
    expect(cls).toContain('bg-foreground')
  })

  it('copilot 展开时淡出隐藏（状态条件，不是媒体查询）', () => {
    shell.copilotOpen = true
    setup()
    expect(pill().className).toContain('opacity-0')
    expect(pill().className).toContain('pointer-events-none')
  })

  it('/assistant 助手独立页：pill 同样隐藏（与抽屉同一例外）', () => {
    setup('/assistant')
    expect(pill().className).toContain('opacity-0')
  })

  it('内容区留出 pill 高度：包 <Outlet /> 的容器带 max-[760px] 底部 padding', () => {
    setup()
    // Outlet 里的路由节点直接挂在壳层容器下（ErrorBoundary / Suspense 不产 DOM）
    const wrapper = screen.getByText('home-content').parentElement
    expect(wrapper?.className).toContain(
      'max-[760px]:pb-[calc(76px+env(safe-area-inset-bottom))]',
    )
  })
})
