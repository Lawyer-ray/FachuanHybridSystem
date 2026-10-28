/**
 * 全局路由路径常量（唯一权威）。
 *
 * **为什么要收拢**：`/projects/:id/review/:taskId` 曾在 Reader 与
 * ContractFileOverlays 里各手拼一遍，`/projects/:id` 也拼了三处。路由一改
 * （比如详情页从 `/projects/:id/nonlit` 收敛成单条 URL 那次），漏改的那处
 * 不会报错——它只是静默跳到通配重定向，用户看到「点了没反应、回到首页」。
 * 所有跨文件可达的路径一律从这里取，禁止再手拼。
 *
 * - `ROUTES`：路由表用的**模板**（含 `:id` 等占位），只给 router 消费；
 * - `xxx(id)` 等函数：代码里跳转用的**实例路径**。
 */

/** 路由模板：只用于 App 路由表声明，不要在跳转里用（会带上 `:id` 字面量） */
export const ROUTES = {
  login: '/login',
  socialCallback: '/social-callback',
  /** 客户材料上传（公开，链接即凭证） */
  clientUpload: '/u/:token',
  home: '/',
  /** 收件箱：已并入预处理页的「收件箱」阶段；保留路由只做前转 */
  inbox: '/inbox',
  materialPrep: '/material-prep',
  materialPrepDetail: '/material-prep/:id',
  projects: '/projects',
  projectDetail: '/projects/:id',
  projectReview: '/projects/:id/review/:taskId',
  settings: '/settings',
  /** 账号绑定并入设置页后的旧路径，只做前转 */
  legacyBindings: '/settings/bindings',
} as const

/** 登录页（退出登录后跳这里） */
export function loginPath(): string {
  return ROUTES.login
}

/** 客户上传单页：token 由后端签发，原样透传（不做 encodeURIComponent，链接是后端给的） */
export function publicUpload(token: string): string {
  return `/u/${token}`
}

/** 预处理页（不带具体材料包）；`stage` 缺省即收件箱阶段 */
export function materialPrep(stage?: 'inbox' | 'todo' | 'done' | 'filed'): string {
  // 收件箱是默认阶段，不写冗余参数，保持 /material-prep 干净
  return !stage || stage === 'inbox' ? ROUTES.materialPrep : `${ROUTES.materialPrep}?stage=${stage}`
}

/**
 * 收件箱页 —— **已并入预处理页的「收件箱」阶段**（见 frontend/src/features/material-prep/stages.ts）。
 *
 * 保留此函数只为前转：旧书签、控制台里的旧链接、首页收件箱卡的「查看全部」
 * 都还指向 /inbox。直接返回预处理页地址，让调用点不需要知道重定向的存在。
 */
export function inboxPath(): string {
  return ROUTES.materialPrep
}

/** 材料包详情：可刷新、可分享、支持前进后退 */
export function materialPrepDetail(id: number | string): string {
  return `/material-prep/${id}`
}

/** 项目列表（合同大行流 + 详情抽屉） */
export function projectList(): string {
  return ROUTES.projects
}

/**
 * 项目详情：一条 URL（`:id` = 委托合同 id），诉讼/非诉由详情页按 `deal.lit` 分流。
 *
 * 传 `undefined` 回落到项目列表——调用方常拿到「可能没有」的归属 id，
 * 这里兜住比让它拼出 `/projects/undefined` 强。
 */
export function projectDetail(id: number | string | undefined | null): string {
  return id == null ? ROUTES.projects : `/projects/${id}`
}

/**
 * 合同复审工作台：发起审查后跳入（`:id` 为项目/合同 id，`:taskId` 为审查任务 id）。
 *
 * 两处调用方（材料预处理 Reader、合同文件夹 ContractFileOverlays）必须共用这一条，
 * 免得路由改名时断掉其中一处。
 */
export function projectReview(projectId: number | string, taskId: string): string {
  return `/projects/${projectId}/review/${taskId}`
}

/** 设置页（系统状态 + 账号绑定） */
export function settings(): string {
  return ROUTES.settings
}
