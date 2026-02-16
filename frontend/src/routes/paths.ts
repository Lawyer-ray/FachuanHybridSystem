/**
 * 路由路径常量
 * 集中管理所有路由路径，避免硬编码
 */
export const PATHS = {
  // 公开页面
  HOME: '/',
  ABOUT: '/about',
  PRICING: '/pricing',
  TUTORIAL: '/tutorial',
  PORTAL: '/portal/:token',

  // 认证页面
  LOGIN: '/login',
  REGISTER: '/register',
  FORGOT_PASSWORD: '/forgot-password',

  // 后台页面 - 使用 /admin 前缀
  ADMIN_DASHBOARD: '/admin/dashboard',
  ADMIN_CASES: '/admin/cases',
  ADMIN_CASE_NEW: '/admin/cases/new',
  ADMIN_CASE_DETAIL: '/admin/cases/:id',
  ADMIN_CASE_EDIT: '/admin/cases/:id/edit',
  ADMIN_CONTRACTS: '/admin/contracts',
  ADMIN_CLIENTS: '/admin/clients',
  ADMIN_CLIENT_NEW: '/admin/clients/new',
  ADMIN_CLIENT_DETAIL: '/admin/clients/:id',
  ADMIN_CLIENT_EDIT: '/admin/clients/:id/edit',
  ADMIN_DOCUMENTS: '/admin/documents',
  ADMIN_REMINDERS: '/admin/reminders',
  ADMIN_SETTINGS: '/admin/settings',

  // 组织管理
  ADMIN_ORGANIZATION: '/admin/organization',
  // 律所管理
  ADMIN_LAWFIRMS: '/admin/organization/lawfirms',
  ADMIN_LAWFIRM_NEW: '/admin/organization/lawfirms/new',
  ADMIN_LAWFIRM_DETAIL: '/admin/organization/lawfirms/:id',
  ADMIN_LAWFIRM_EDIT: '/admin/organization/lawfirms/:id/edit',
  // 律师管理
  ADMIN_LAWYERS: '/admin/organization/lawyers',
  ADMIN_LAWYER_NEW: '/admin/organization/lawyers/new',
  ADMIN_LAWYER_DETAIL: '/admin/organization/lawyers/:id',
  ADMIN_LAWYER_EDIT: '/admin/organization/lawyers/:id/edit',
  // 团队管理
  ADMIN_TEAMS: '/admin/organization/teams',
  // 凭证管理
  ADMIN_CREDENTIALS: '/admin/organization/credentials',

  // 设置
  ADMIN_SETTINGS: '/admin/settings',
  ADMIN_SETTINGS_USER: '/admin/settings/user',
  ADMIN_SETTINGS_SYSTEM: '/admin/settings/system',

  // 自动化工具
  ADMIN_AUTOMATION: '/admin/automation',
  ADMIN_AUTOMATION_QUOTES: '/admin/automation/preservation-quotes',
  ADMIN_AUTOMATION_QUOTE_DETAIL: '/admin/automation/preservation-quotes/:id',
  ADMIN_AUTOMATION_RECOGNITION: '/admin/automation/document-recognition',
  ADMIN_AUTOMATION_RECOGNITION_DETAIL: '/admin/automation/document-recognition/:id',

  // 外部链接
  GITHUB: 'https://github.com/huangsong/fachuanai',
} as const

/**
 * 生成带参数的路由路径
 */
export const generatePath = {
  portal: (token: string) => `/portal/${token}`,
  caseDetail: (id: string) => `/admin/cases/${id}`,
  caseEdit: (id: string) => `/admin/cases/${id}/edit`,
  clientDetail: (id: string | number) => `/admin/clients/${id}`,
  clientEdit: (id: string | number) => `/admin/clients/${id}/edit`,
  // 律所管理
  lawFirmDetail: (id: string | number) => `/admin/organization/lawfirms/${id}`,
  lawFirmEdit: (id: string | number) => `/admin/organization/lawfirms/${id}/edit`,
  // 律师管理
  lawyerDetail: (id: string | number) => `/admin/organization/lawyers/${id}`,
  lawyerEdit: (id: string | number) => `/admin/organization/lawyers/${id}/edit`,
  // 自动化工具
  quoteDetail: (id: string | number) => `/admin/automation/preservation-quotes/${id}`,
  recognitionDetail: (id: string | number) => `/admin/automation/document-recognition/${id}`,
} as const
