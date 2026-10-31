import { Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { hasToken } from '@/lib/token'
import { LoginPage, SocialCallbackPage } from '@/features/auth'
import { AppShell } from './shell/AppShell'
import {
  BankLitigationPageLazy,
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

/**
 * 旧收件箱路径 → 预处理页。收件箱现在是该页的默认阶段，故丢掉 search 也不会
 * 落错阶段（?stage=todo 之类的旧链接仍会由 materialPrep 的解析器兼容）。
 */
function LegacyInboxRedirect() {
  return <Navigate to={ROUTES.materialPrep} replace />
}

/**
 * 立案工作台（带案件 id）：把 URL 里的 `:id` 解出来交给页面。
 *
 * 页面对「id 从哪来」无感 —— 列表模式下它自己 setState，URL 模式下由这里注入。
 * 用 Number() 而非 parseInt：`parseInt('12abc')` 会得到 12，
 * 悄悄打开了另一个案子；Number 给 NaN，走「案件不存在」分支。
 */
function BankLitigationCaseRoute() {
  const { id } = useParams()
  const caseId = Number(id)
  return <BankLitigationPageLazy initialCaseId={Number.isFinite(caseId) ? caseId : null} />
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
          {/* 收件箱已并入预处理页的「收件箱」阶段（流水线第一段）。旧路径保留
              前转：收件箱正是该页的默认阶段，故不需要透传 query 也不会落错。 */}
          <Route path={ROUTES.inbox} element={<LegacyInboxRedirect />} />
          <Route path={ROUTES.materialPrep} element={<DeskPageLazy />} />
          {/* 详情页：/material-prep/:id —— 可刷新、可分享、支持前进后退 */}
          <Route path={ROUTES.materialPrepDetail} element={<DeskPageLazy />} />
          {/* 项目主页：合同大行流 + 详情抽屉。路由用 projects 而非 cases——本页是
              合同与案件融合展示，单说合同或案件都不准确；cases 在后端已明确指案件。 */}
          <Route path={ROUTES.projects} element={<WorkbenchPageLazy />} />
          {/* 项目详情：一条 URL（:id = 委托合同 id），按 deal.lit 分流左栏——
              诉讼走案件程序链、非诉走合同文件夹。不再用 /nonlit 后缀暴露分类词。 */}
          <Route path={ROUTES.projectDetail} element={<ProjectDetailPageLazy />} />
          {/* 银行批量诉讼（场景 2）：列表与立案工作台共用同一页组件，
              `:id` 有值时打开指定案件的工作台。两者必须同一条组件 ——
              工作台内的四个分区（起诉条件/要素式转换/OA/一张网）都依赖
              同一个 caseId 状态，拆成两个页面会让「从列表点进 B 案、
              另一个标签页还停在 A 案」成为可能。 */}
          <Route path={ROUTES.bankLitigation} element={lazyPage(<BankLitigationPageLazy />)} />
          <Route path={ROUTES.bankLitigationCase} element={lazyPage(<BankLitigationCaseRoute />)} />
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
