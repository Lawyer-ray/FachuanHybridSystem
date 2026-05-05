/**
 * 路由路径常量
 * 集中管理所有路由路径，避免硬编码
 */
export const PATHS = {
  // 认证页面
  LOGIN: '/login',
  REGISTER: '/register',
  FORGOT_PASSWORD: '/forgot-password',

  // 后台页面 - 使用 /admin 前缀
  ADMIN_DASHBOARD: '/admin/dashboard',
  ADMIN_INBOX: '/admin/inbox',
  ADMIN_INBOX_DETAIL: '/admin/inbox/:id',
  ADMIN_CASES: '/admin/cases',
  ADMIN_CASE_NEW: '/admin/cases/new',
  ADMIN_CASE_DETAIL: '/admin/cases/:id',
  ADMIN_CASE_EDIT: '/admin/cases/:id/edit',
  ADMIN_CONTRACTS: '/admin/contracts',
  ADMIN_CONTRACT_NEW: '/admin/contracts/new',
  ADMIN_CONTRACT_DETAIL: '/admin/contracts/:id',
  ADMIN_CONTRACT_EDIT: '/admin/contracts/:id/edit',
  ADMIN_CLIENTS: '/admin/clients',
  ADMIN_CLIENT_NEW: '/admin/clients/new',
  ADMIN_CLIENT_DETAIL: '/admin/clients/:id',
  ADMIN_CLIENT_EDIT: '/admin/clients/:id/edit',
  ADMIN_DOCUMENTS: '/admin/documents',
  ADMIN_REMINDERS: '/admin/reminders',

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

  // Phase 3: 新功能模块
  ADMIN_TEMPLATES: '/admin/templates',
  ADMIN_TEMPLATE_DETAIL: '/admin/templates/:id',
  ADMIN_TEMPLATE_NEW: '/admin/templates/new',
  ADMIN_MESSAGE_SOURCES: '/admin/message-sources',
  ADMIN_TASK_QUEUE: '/admin/task-queue',
  ADMIN_LOGS: '/admin/logs',
  ADMIN_TOOLS_COURT_SMS: '/admin/tools/court-sms',
  ADMIN_TOOLS_COURT_SMS_DETAIL: '/admin/tools/court-sms/:id',
  ADMIN_TOOLS_COURIER: '/admin/tools/courier-tracking',
  ADMIN_TOOLS_ELEMENT: '/admin/tools/element-convert',
  ADMIN_TOOLS_LPR: '/admin/tools/lpr-calculator',

  // Phase 4: 设置重构
  ADMIN_SETTINGS_LAW_FIRM: '/admin/settings/law-firm',
  ADMIN_SETTINGS_TEAM: '/admin/settings/team',
  ADMIN_SETTINGS_LAWYER: '/admin/settings/lawyer',
  ADMIN_SETTINGS_CONFIG: '/admin/settings/config/:category',

  // 外部链接
  GITHUB: 'https://github.com/huangsong/fachuanai',
} as const

/**
 * 生成带参数的路由路径
 */
export const generatePath = {
  inboxDetail: (id: string | number) => `/admin/inbox/${id}`,
  caseDetail: (id: string) => `/admin/cases/${id}`,
  caseEdit: (id: string) => `/admin/cases/${id}/edit`,
  contractDetail: (id: string | number) => `/admin/contracts/${id}`,
  contractEdit: (id: string | number) => `/admin/contracts/${id}/edit`,
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
  // 模板管理
  templateDetail: (id: string | number) => `/admin/templates/${id}`,
  // 法院短信
  courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}`,
} as const
