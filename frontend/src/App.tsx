import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { Loader2 } from 'lucide-react'
import { hasToken } from '@/lib/token'
import { ErrorBoundary, PageErrorBoundary } from '@/components/shared/ErrorBoundary'
import { BindingsPageLazy, LoginPage, SocialCallbackPage } from '@/features/auth'
import { HomePageLazy } from '@/features/home'
import { WorkbenchPageLazy } from '@/features/workbench'

// 材料预处理整域懒加载：它静态引入 pdfjs-dist（~1MB 级），不拆出去的话
// 登录页/首页的首屏包也要背上它。列表页与详情页共用同一 chunk，切换零成本。
const DeskPage = lazy(() =>
  import('@/features/material-prep').then((m) => ({ default: m.DeskPage })),
)

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!hasToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** 路由级懒加载 fallback：与各页面的 loading 分支同风格（居中细 spinner） */
function RouteFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center gap-2 text-sm text-secondary-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> 正在加载…
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
        {/* 首页 · 今日工作台（home 域含工具坞弹窗全家桶，懒加载拆出首屏包） */}
        <Route
          path="/"
          element={
            <RequireAuth>
              <PageErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <HomePageLazy />
                </Suspense>
              </PageErrorBoundary>
            </RequireAuth>
          }
        />
        <Route
          path="/material-prep"
          element={
            <RequireAuth>
              <PageErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <DeskPage />
                </Suspense>
              </PageErrorBoundary>
            </RequireAuth>
          }
        />
        {/* 详情页：/material-prep/:id —— 可刷新、可分享、支持前进后退 */}
        <Route
          path="/material-prep/:id"
          element={
            <RequireAuth>
              <PageErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <DeskPage />
                </Suspense>
              </PageErrorBoundary>
            </RequireAuth>
          }
        />
        {/* 办案主页：合同大行流 + 详情抽屉（/cases 对齐后端 cases 域，未来 /cases/:id 个案详情） */}
        <Route
          path="/cases"
          element={
            <RequireAuth>
              <PageErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <WorkbenchPageLazy />
                </Suspense>
              </PageErrorBoundary>
            </RequireAuth>
          }
        />
        {/* 个人设置 · 账号绑定：登录只放行已绑定的社交身份，绑定入口在这里 */}
        <Route
          path="/settings/bindings"
          element={
            <RequireAuth>
              <PageErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <BindingsPageLazy />
                </Suspense>
              </PageErrorBoundary>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
