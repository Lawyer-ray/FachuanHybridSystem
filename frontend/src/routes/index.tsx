import { createBrowserRouter } from 'react-router'
import { PublicLayout } from '@/layouts/PublicLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { AdminLayout } from '@/layouts/AdminLayout'
import { PATHS } from './paths'
import { AuthGuard, GuestGuard } from './guards'

// 懒加载页面组件
import { lazy } from 'react'

const HomePage = lazy(() =>
  import('@/pages/public/HomePage').then((m) => ({ default: m.HomePage }))
)

const PricingPage = lazy(() =>
  import('@/pages/public/PricingPage').then((m) => ({ default: m.PricingPage }))
)

const TutorialPage = lazy(() =>
  import('@/pages/public/TutorialPage').then((m) => ({ default: m.TutorialPage }))
)

// 认证页面懒加载
const LoginPage = lazy(() =>
  import('@/pages/auth/LoginPage').then((m) => ({ default: m.LoginPage }))
)

const RegisterPage = lazy(() =>
  import('@/pages/auth/RegisterPage').then((m) => ({ default: m.RegisterPage }))
)

// 后台页面懒加载
// @validates Requirements 8.6 - THE 路由 SHALL 使用 React Router v7 的懒加载功能
const DashboardPage = lazy(() => import('@/pages/dashboard/DashboardPage'))

// 当事人管理页面
const ClientListPage = lazy(() => import('@/pages/dashboard/clients/ClientListPage'))
const ClientNewPage = lazy(() => import('@/pages/dashboard/clients/ClientNewPage'))
const ClientDetailPage = lazy(() => import('@/pages/dashboard/clients/ClientDetailPage'))
const ClientEditPage = lazy(() => import('@/pages/dashboard/clients/ClientEditPage'))

// 提醒管理页面
const RemindersPage = lazy(() => import('@/pages/dashboard/reminders'))

// 组织管理页面
const OrganizationPage = lazy(() => import('@/pages/dashboard/organization/OrganizationPage'))
const LawFirmNewPage = lazy(() => import('@/pages/dashboard/organization/lawfirms/LawFirmNewPage'))
const LawFirmDetailPage = lazy(() => import('@/pages/dashboard/organization/lawfirms/LawFirmDetailPage'))
const LawFirmEditPage = lazy(() => import('@/pages/dashboard/organization/lawfirms/LawFirmEditPage'))
const LawyerNewPage = lazy(() => import('@/pages/dashboard/organization/lawyers/LawyerNewPage'))
const LawyerDetailPage = lazy(() => import('@/pages/dashboard/organization/lawyers/LawyerDetailPage'))
const LawyerEditPage = lazy(() => import('@/pages/dashboard/organization/lawyers/LawyerEditPage'))

// 自动化工具页面
// @validates Requirements 1.3, 1.4, 1.5, 1.6 - 自动化工具路由
const AutomationIndexPage = lazy(() => import('@/pages/dashboard/automation/AutomationIndexPage'))
const QuoteListPage = lazy(() => import('@/pages/dashboard/automation/preservation-quotes/QuoteListPage'))
const QuoteDetailPage = lazy(() => import('@/pages/dashboard/automation/preservation-quotes/QuoteDetailPage'))
const RecognitionListPage = lazy(() => import('@/pages/dashboard/automation/document-recognition/RecognitionListPage'))
const RecognitionDetailPage = lazy(() => import('@/pages/dashboard/automation/document-recognition/RecognitionDetailPage'))

/**
 * 应用路由配置
 */
export const router = createBrowserRouter([
  // 公开页面
  {
    element: <PublicLayout />,
    children: [
      {
        path: PATHS.HOME,
        element: <HomePage />,
      },
      {
        path: PATHS.PRICING,
        element: <PricingPage />,
      },
      {
        path: PATHS.TUTORIAL,
        element: <TutorialPage />,
      },
      // 其他公开页面后续添加...
    ],
  },
  // 认证页面（已登录则跳转到 dashboard）
  {
    element: <GuestGuard />,
    children: [
      {
        element: <AuthLayout />,
        children: [
          {
            path: PATHS.LOGIN,
            element: <LoginPage />,
          },
          {
            path: PATHS.REGISTER,
            element: <RegisterPage />,
          },
        ],
      },
    ],
  },
  // 后台页面（需登录）
  // @validates Requirements 8.5 - WHEN 未登录用户访问 `/admin/*` 路径 THEN THE System SHALL 重定向到登录页
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AdminLayout />,
        children: [
          // Dashboard 首页
          {
            path: PATHS.ADMIN_DASHBOARD,
            element: <DashboardPage />,
          },
          // 当事人管理路由
          // @validates Requirements 8.1 - THE System SHALL 在 `/admin/clients` 路径显示当事人列表页
          {
            path: PATHS.ADMIN_CLIENTS,
            element: <ClientListPage />,
          },
          // @validates Requirements 8.4 - THE System SHALL 在 `/admin/clients/new` 路径显示新建当事人页
          // 注意：/new 路由必须在 /:id 之前，避免路由冲突
          {
            path: PATHS.ADMIN_CLIENT_NEW,
            element: <ClientNewPage />,
          },
          // @validates Requirements 8.2 - THE System SHALL 在 `/admin/clients/:id` 路径显示当事人详情页
          {
            path: PATHS.ADMIN_CLIENT_DETAIL,
            element: <ClientDetailPage />,
          },
          // @validates Requirements 8.3 - THE System SHALL 在 `/admin/clients/:id/edit` 路径显示当事人编辑页
          {
            path: PATHS.ADMIN_CLIENT_EDIT,
            element: <ClientEditPage />,
          },
          // 提醒管理路由
          // @validates Requirements 1.1 - WHEN 用户访问 /admin/reminders 页面 THEN 展示提醒列表
          {
            path: PATHS.ADMIN_REMINDERS,
            element: <RemindersPage />,
          },
          // 组织管理路由
          // @validates Requirements 7.1 - THE System SHALL 在 `/admin/organization` 路径显示组织管理主页面
          {
            path: PATHS.ADMIN_ORGANIZATION,
            element: <OrganizationPage />,
          },
          // @validates Requirements 7.2 - THE System SHALL 在 `/admin/organization/lawfirms` 路径显示律所列表（Tab 切换）
          {
            path: PATHS.ADMIN_LAWFIRMS,
            element: <OrganizationPage />,
          },
          // @validates Requirements 7.3 - THE System SHALL 在 `/admin/organization/lawfirms/new` 路径显示新建律所页面
          {
            path: PATHS.ADMIN_LAWFIRM_NEW,
            element: <LawFirmNewPage />,
          },
          // @validates Requirements 7.4 - THE System SHALL 在 `/admin/organization/lawfirms/:id` 路径显示律所详情页面
          {
            path: PATHS.ADMIN_LAWFIRM_DETAIL,
            element: <LawFirmDetailPage />,
          },
          // @validates Requirements 7.5 - THE System SHALL 在 `/admin/organization/lawfirms/:id/edit` 路径显示编辑律所页面
          {
            path: PATHS.ADMIN_LAWFIRM_EDIT,
            element: <LawFirmEditPage />,
          },
          // @validates Requirements 7.6 - THE System SHALL 在 `/admin/organization/lawyers` 路径显示律师列表（Tab 切换）
          {
            path: PATHS.ADMIN_LAWYERS,
            element: <OrganizationPage />,
          },
          // @validates Requirements 7.7 - THE System SHALL 在 `/admin/organization/lawyers/new` 路径显示新建律师页面
          {
            path: PATHS.ADMIN_LAWYER_NEW,
            element: <LawyerNewPage />,
          },
          // @validates Requirements 7.8 - THE System SHALL 在 `/admin/organization/lawyers/:id` 路径显示律师详情页面
          {
            path: PATHS.ADMIN_LAWYER_DETAIL,
            element: <LawyerDetailPage />,
          },
          // @validates Requirements 7.9 - THE System SHALL 在 `/admin/organization/lawyers/:id/edit` 路径显示编辑律师页面
          {
            path: PATHS.ADMIN_LAWYER_EDIT,
            element: <LawyerEditPage />,
          },
          // @validates Requirements 7.10 - THE System SHALL 在 `/admin/organization/teams` 路径显示团队列表（Tab 切换）
          {
            path: PATHS.ADMIN_TEAMS,
            element: <OrganizationPage />,
          },
          // @validates Requirements 7.11 - THE System SHALL 在 `/admin/organization/credentials` 路径显示凭证列表（Tab 切换）
          {
            path: PATHS.ADMIN_CREDENTIALS,
            element: <OrganizationPage />,
          },
          // 自动化工具路由
          // @validates Requirements 1.3 - THE System SHALL 在 `/admin/automation/preservation-quotes` 路径显示财产保全询价列表页
          {
            path: PATHS.ADMIN_AUTOMATION,
            element: <AutomationIndexPage />,
          },
          {
            path: PATHS.ADMIN_AUTOMATION_QUOTES,
            element: <QuoteListPage />,
          },
          // @validates Requirements 1.4 - THE System SHALL 在 `/admin/automation/preservation-quotes/:id` 路径显示询价任务详情页
          {
            path: PATHS.ADMIN_AUTOMATION_QUOTE_DETAIL,
            element: <QuoteDetailPage />,
          },
          // @validates Requirements 1.5 - THE System SHALL 在 `/admin/automation/document-recognition` 路径显示文书识别列表页
          {
            path: PATHS.ADMIN_AUTOMATION_RECOGNITION,
            element: <RecognitionListPage />,
          },
          // @validates Requirements 1.6 - THE System SHALL 在 `/admin/automation/document-recognition/:id` 路径显示识别任务详情页
          {
            path: PATHS.ADMIN_AUTOMATION_RECOGNITION_DETAIL,
            element: <RecognitionDetailPage />,
          },
        ],
      },
    ],
  },
])
