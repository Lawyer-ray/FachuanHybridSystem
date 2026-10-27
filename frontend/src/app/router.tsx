import { Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import { Loader2 } from 'lucide-react'

import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { hasToken } from '@/lib/token'
import { LoginPage, SocialCallbackPage } from '@/features/auth'
import { AppShell } from './shell/AppShell'
import {
  ClientUploadPageLazy,
  DeskPageLazy,
  HomePageLazy,
  ProjectDetailPageLazy,
  ReviewWorkbenchPageLazy,
  SettingsPageLazy,
  WorkbenchPageLazy,
} from './preload'
import { ROUTES, settings } from './paths'

/**
 * 顶层路由表：聚合各 feature 的页面（页面 chunk 在 ./preload 里 lazy 声明）。
 *
 * 路径字面量只允许出现在 ./paths.ts 的 ROUTES 里，这里一律引模板——改路由时
 * 想漏改一处都难。
 */

function RequireAuth({ children }: { children: ReactNode }) {
  if (!hasToken()) return <Navigate to={ROUTES.login} replace />
  return <>{children}</>
}

/** 路由级懒加载 fallback：与各页面的 loading 分支同风格（居中细 spinner） */
export function RouteFallback() {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-secondary-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> 正在加载…
    </div>
  )
}

/** /settings/bindings → /settings：账号绑定页并入设置页后的旧路径前转（保留 query） */
function LegacyBindingsRedirect() {
  const { search } = useLocation()
  return <Navigate to={`${settings()}${search}`} replace />
}

/** 懒加载页统一包一层 RouteFallback（fallback 由 Suspense 兜） */
function lazyPage(node: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>
}

export function AppRouter() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path={ROUTES.login} element={<LoginPage />} />
        {/* 社交登录回调：飞书/微信授权后由后端 302 到此，用一次性码换 JWT */}
        <Route path={ROUTES.socialCallback} element={<SocialCallbackPage />} />
        {/* 客户材料上传（公开）：链接即凭证，不进 RequireAuth */}
        <Route path={ROUTES.clientUpload} element={lazyPage(<ClientUploadPageLazy />)} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          {/* 首页 · 今日工作台（home 域含工具坞弹窗全家桶，懒加载拆出首屏包） */}
          <Route path={ROUTES.home} element={<HomePageLazy />} />
          <Route path={ROUTES.materialPrep} element={<DeskPageLazy />} />
          {/* 详情页：/material-prep/:id —— 可刷新、可分享、支持前进后退 */}
          <Route path={ROUTES.materialPrepDetail} element={<DeskPageLazy />} />
          {/* 项目主页：合同大行流 + 详情抽屉。路由用 projects 而非 cases——本页是
              合同与案件融合展示，单说合同或案件都不准确；cases 在后端已明确指案件。 */}
          <Route path={ROUTES.projects} element={<WorkbenchPageLazy />} />
          {/* 项目详情：一条 URL（:id = 委托合同 id），按 deal.lit 分流左栏——
              诉讼走案件程序链、非诉走合同文件夹。不再用 /nonlit 后缀暴露分类词。 */}
          <Route path={ROUTES.projectDetail} element={<ProjectDetailPageLazy />} />
          {/* 合同复审工作台（发起审查后跳入；参数与 ReviewWorkbenchPage 的 useParams 对齐） */}
          <Route path={ROUTES.projectReview} element={<ReviewWorkbenchPageLazy />} />
          {/* 设置：系统状态 + 账号绑定 */}
          <Route path={ROUTES.settings} element={<SettingsPageLazy />} />
          {/* 旧路径迁移：账号绑定已并入设置页。保留 query 前转（bound= 绑定成功
              标记由设置页里的绑定面板消费，丢了就不弹成功提示） */}
          <Route path={ROUTES.legacyBindings} element={<LegacyBindingsRedirect />} />
        </Route>
        <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
