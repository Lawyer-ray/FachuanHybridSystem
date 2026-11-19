// @vitest-environment jsdom
/**
 * 路由表里两条**有语义**的行为（jsdom）。
 *
 * 只测这两处、不测整张路由表：其余路由都是「路径 → 页面组件」的直连，
 * 真正行为在页面自己身上（各自有测试）。而下面两条藏着真故障：
 *
 * 1. `LegacyBindingsRedirect` 必须**保留 query**。旧账号绑定链接是
 *    `/settings/bindings?bound=1`，`bound=` 由设置页里的绑定面板消费；前转时
 *    丢掉 query，用户授权回来看到的是一个静默的设置页——「我到底绑上没有？」
 * 2. `BankLitigationCaseRoute` 用 `Number()` 而非 `parseInt`。
 *    `parseInt('12abc')` 得到 **12**，于是 `/bank-litigation/12abc` 悄悄打开
 *    第 12 个案子（合同/案件两套 id 各自独立自增，传错不报错、可能打开到
 *    别人家的案子）。`Number()` 给 NaN，走「案件不存在」分支才对。
 *
 * 两个被测函数是模块内私有的，所以用真实路由表驱动：
 * - `./shell/AppShell` 换成带 `<Outlet />` 的薄桩（用它自己的 `<Routes>` 会把
 *   子路由吃掉，父路由上的页面根本渲染不出来）；
 * - `./preload` 与 `@/features/auth` 也换桩：真实懒加载 chunk 会拉 pdfjs 等
 *   重依赖，而本文件只关心路由算出来的值；
 * - **ErrorBoundary 保留真实实现**：它的 `useLocation()` 需要跑在 router 上下文
 *   里，mock 掉反而会让整棵树在 context 缺失时抛错并显示「页面出错了」。
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/token', () => ({ hasToken: () => true }))
vi.mock('@/features/auth', () => ({
  LoginPage: () => <div data-testid="login">登录页</div>,
  SocialCallbackPage: () => <div data-testid="social">回调页</div>,
}))

/** 路由实际交给页面的入参（每次挂载追加一条） */
const seen = vi.hoisted(() => ({ caseIds: [] as Array<number | null> }))

vi.mock('./preload', () => ({
  AssistantPageLazy: () => <div data-testid="assistant">助手页</div>,
  HomePageLazy: () => <div data-testid="home">首页</div>,
  ClientUploadPageLazy: () => <div data-testid="upload">上传页</div>,
  DeskPageLazy: () => <div data-testid="desk">预处理页</div>,
  ProjectDetailPageLazy: () => <div data-testid="project">项目详情</div>,
  WorkbenchPageLazy: () => <div data-testid="workbench">工作台</div>,
  SettingsPageLazy: () => <LocationTag testid="settings" />,
  ReviewWorkbenchPageLazy: () => <div data-testid="review">复审台</div>,
  BankLitigationPageLazy: ({ initialCaseId }: { initialCaseId?: number | null }) => {
    seen.caseIds.push(initialCaseId ?? null)
    return <div data-testid="bank-litigation">{String(initialCaseId ?? 'null')}</div>
  },
}))

vi.mock('./shell/AppShell', () => ({
  // 必须渲染 <Outlet />：父路由上的页面（本文件测的这几条）靠它出现
  AppShell: () => (
    <div data-testid="shell">
      <Outlet />
    </div>
  ),
}))

/**
 * 把当前 location（含 search）打到页面上，用于验证前转保留了 query。
 *
 * 必须用 `useLocation()` 而不是 `window.location`：MemoryRouter 不碰真实
 * history，只有 router 内部的 location 反映前转结果。
 */
function LocationTag({ testid }: { testid: string }) {
  const loc = useLocation()
  return <div data-testid={testid}>{`${loc.pathname}${loc.search}`}</div>
}

import { ROUTES } from './paths'
import { AppRouter } from './router'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  seen.caseIds.length = 0
})

describe('未知路径兜底', () => {
  it('未知路径回首页（不能白屏）', () => {
    renderAt('/some/unknown/path')
    expect(screen.getByTestId('home')).toBeTruthy()
  })
})

describe('AI 助手独立页路由', () => {
  it('ROUTES.assistant 渲染助手页（路径模板只在 paths.ts 里定义）', () => {
    renderAt(ROUTES.assistant)
    expect(screen.getByTestId('assistant')).toBeTruthy()
  })
})

describe('LegacyBindingsRedirect', () => {
  it('保留 query 前转到 /settings（bound=1 丢了就不弹绑定成功提示）', () => {
    renderAt('/settings/bindings?bound=1')
    // 断言最终 location 而不是「有没有调用 navigate」：query 是否保留是用户
    // 可见的结果，也是这条前转唯一容易写错的地方
    expect(screen.getByTestId('settings').textContent).toBe('/settings?bound=1')
  })

  it('没有 query 时前转成干净路径，不留孤零零的 ?', () => {
    renderAt('/settings/bindings')
    expect(screen.getByTestId('settings').textContent).toBe('/settings')
  })
})

describe('BankLitigationCaseRoute', () => {
  it('/bank-litigation/12 把 12 传给页面', () => {
    renderAt('/bank-litigation/12')
    expect(screen.getByTestId('bank-litigation').textContent).toBe('12')
  })

  it("'12abc' 解出 null 而不是 12（parseInt 会悄悄打开第 12 个案子）", () => {
    renderAt('/bank-litigation/12abc')
    // 注释里点名的真实故障：parseInt('12abc') === 12。两套 id 各自独立自增，
    // 传错不一定报错、可能打开到别人家的合同/案件
    expect(screen.getByTestId('bank-litigation').textContent).toBe('null')
    expect(seen.caseIds).toEqual([null])
  })

  it('纯非数字同样为 null（走「案件不存在」分支）', () => {
    renderAt('/bank-litigation/abc')
    expect(seen.caseIds).toEqual([null])
  })
})
