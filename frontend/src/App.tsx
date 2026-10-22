import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { hasToken } from '@/lib/token'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { ErrorBoundary, PageErrorBoundary } from '@/components/shared/ErrorBoundary'
import { BindingsPageLazy, LoginPage, SocialCallbackPage } from '@/features/auth'
import { HomePageLazy, preloadHomePage } from '@/features/home'
import { DealDetailPageLazy, preloadWorkbenchPage, WorkbenchPageLazy } from '@/features/workbench'

// 材料预处理整域懒加载：它静态引入 pdfjs-dist（~1MB 级），不拆出去的话
// 登录页/首页的首屏包也要背上它。列表页与详情页共用同一 chunk，切换零成本。
const preloadDeskPage = () => import('@/features/material-prep')
const DeskPage = lazy(() => preloadDeskPage().then((m) => ({ default: m.DeskPage })))

// AI 助手面板懒加载：只在首次展开时加载 copilot 域；挂壳层、跨路由常驻，
// 收起面板不卸载状态（流式收发在 store，见 features/copilot）。
const CopilotPanelLazy = lazy(() => import('@/features/copilot').then((m) => ({ default: m.CopilotPanel })))

const COPILOT_OPEN_KEY = 'copilot:open'

/**
 * 导航入口 → 页面 chunk 加载器。悬停预取（AppNavbar onPrefetch）与登录后的
 * 空闲预载共用；import() 幂等，重复调用只命中浏览器模块缓存。
 * 账号绑定页走用户菜单、访问频率低，不在预载之列。
 */
const ROUTE_PRELOADERS: Record<string, () => Promise<unknown>> = {
  '/': preloadHomePage,
  '/material-prep': preloadDeskPage,
  '/cases': preloadWorkbenchPage,
}

function preloadRoute(to: string) {
  // 预取失败不用管：真正导航时 lazy 会再拉一次，失败由 ErrorBoundary 兜底
  void ROUTE_PRELOADERS[to]?.().catch(() => {})
}

/** 浏览器空闲时执行（Safari 无 requestIdleCallback，退化为短延时） */
function whenIdle(cb: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(cb, { timeout: 3000 })
    return () => window.cancelIdleCallback(id)
  }
  const id = window.setTimeout(cb, 1500)
  return () => window.clearTimeout(id)
}

function RequireAuth({ children }: { children: ReactNode }) {
  if (!hasToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** 路由级懒加载 fallback：与各页面的 loading 分支同风格（居中细 spinner） */
function RouteFallback() {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-secondary-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> 正在加载…
    </div>
  )
}

/**
 * 已登录区域的持久壳层：导航栏跨页面常驻，只有 <Outlet /> 里的内容区随路由换。
 *
 * 此前每个页面各自渲染一份 AppNavbar，且路由级 Suspense 的 fallback 是全屏
 * spinner——首次点开一个未缓存的标签，整页（含导航栏）先被替换成转圈，chunk
 * 到了再整页重挂，肉眼就是一次闪烁。现在：
 * - AppNavbar 在壳层，任何路由切换都不碰它；
 * - Suspense 边界常驻且已显示内容，react-router 把导航包在 startTransition 里，
 *   React 会保住旧页面直到新 chunk 可渲染，不再退回 fallback（fallback 只在
 *   壳层首次挂载、首个页面 chunk 还没到时出现一次）；
 * - PageErrorBoundary 以 pathname 作 resetKey 而非 key，健康页面不随 pathname
 *   重挂，/material-prep ↔ /material-prep/:id 保持同一个 DeskPage 实例。
 * 入场过渡由各页面自己的 <main className="app-page-enter"> 承担：换页=组件
 * 换类型=main 重挂=播一次；同页子路由=实例不变=不重播。
 *
 * 壳层是普通块级布局（不用 flex 列：flex item 上的 mx-auto 会让 main 收缩到
 * 内容宽度，max-w 失效）。需要撑满导航栏以下视口的页面（DeskPage 拖放）用
 * --app-navbar-h 自己算最小高度。
 */
function AppShell() {
  // 登录后空闲时把三个主入口的 chunk 预载进来：切标签不再等下载。
  // 悬停预取（AppNavbar）兜住预载还没完成就点进来的情况。
  useEffect(() => whenIdle(() => Object.keys(ROUTE_PRELOADERS).forEach(preloadRoute)), [])

  // AI 助手面板开关：展开状态跨会话记忆（localStorage），首次展开才加载 chunk。
  const [copilotOpen, setCopilotOpen] = useState(() => {
    try {
      return localStorage.getItem(COPILOT_OPEN_KEY) === '1'
    } catch {
      return false
    }
  })
  // 滑出动画期间保持挂载：收起时先播 animate-out，240ms 后再卸载（与面板
  // duration-200 对齐留余量）。重新展开会取消定时器，面板无缝回到 animate-in。
  const [copilotMounted, setCopilotMounted] = useState(copilotOpen)
  useEffect(() => {
    if (copilotOpen) {
      setCopilotMounted(true)
      return
    }
    const timer = setTimeout(() => setCopilotMounted(false), 240)
    return () => clearTimeout(timer)
  }, [copilotOpen])
  const toggleCopilot = () => {
    setCopilotOpen((v) => {
      try {
        localStorage.setItem(COPILOT_OPEN_KEY, v ? '0' : '1')
      } catch {
        /* 忽略持久化失败 */
      }
      return !v
    })
  }

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={(msg) => toast.info(msg)} onPrefetch={preloadRoute} onToggleCopilot={toggleCopilot} />
      {copilotMounted && (
        <Suspense fallback={null}>
          <CopilotPanelLazy open={copilotOpen} onClose={toggleCopilot} />
        </Suspense>
      )}
      <PageErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </PageErrorBoundary>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* 社交登录回调：飞书/微信授权后由后端 302 到此，用一次性码换 JWT */}
        <Route path="/social-callback" element={<SocialCallbackPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          {/* 首页 · 今日工作台（home 域含工具坞弹窗全家桶，懒加载拆出首屏包） */}
          <Route path="/" element={<HomePageLazy />} />
          <Route path="/material-prep" element={<DeskPage />} />
          {/* 详情页：/material-prep/:id —— 可刷新、可分享、支持前进后退 */}
          <Route path="/material-prep/:id" element={<DeskPage />} />
          {/* 办案主页：合同大行流 + 详情抽屉（/cases 对齐后端 cases 域） */}
          <Route path="/cases" element={<WorkbenchPageLazy />} />
          {/* 争议解决详情页：一页一委托（:id = 委托合同 id），合同与案件链在页内融合呈现 */}
          <Route path="/cases/:id" element={<DealDetailPageLazy />} />
          {/* 个人设置 · 账号绑定：登录只放行已绑定的社交身份，绑定入口在这里 */}
          <Route path="/settings/bindings" element={<BindingsPageLazy />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
