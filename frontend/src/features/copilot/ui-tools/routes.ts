/**
 * 参数 → 站内路径：**整条链路上唯一的安全边界**。
 *
 * 模型给的 path 是不可信输入（它可能被提示注入、也可能自己编），而 `navigate` 直接
 * 改地址栏。所以这里不「清洗」输入——只做**白名单匹配**：能匹配 `@/app/paths` 的
 * ROUTES 模板才算合法，其余一律返回 null，由调用方落 `route_unreachable`。
 *
 * **为什么必须是白名单而不是黑名单**：黑名单永远漏一类（今天挡了 `javascript:`，
 * 明天有人手拼 `/u/<token>` 就绕过了）；而白名单只放行路由表里真实存在、且已经
 * 评估过「AI 跳过去无害」的那几条。
 *
 * 三道明确的排除（不能靠「模板里没有所以匹配不上」来兜）：
 * 1. `ROUTES.clientUpload`（`/u/:token`）——**链接即凭证**，AI 把它写进地址栏等于
 *    泄露客户上传入口；它不是登录态页面，校验兜不住；
 * 2. `ROUTES.login` / `ROUTES.socialCallback` —— 未登录态页面，AI 把律师甩到登录页
 *    会当场丢掉他手上的会话；
 * 3. 一切带 query 的路径，除材料预处理页的 `stage`——query 是模型夹带参数的天然
 *    缝隙（`?message=` 是深链接直达能力，不该由模型设）。
 */

import { ROUTES } from '@/app/paths'

/**
 * 预处理四阶段。与 `features/material-prep/stages.ts` 的 `PrepStage` 是同一个概念，
 * 但那里是另一个 feature 的内部文件（跨 feature 禁止直接 import），这里复制一份并在
 * `registry.node.test.ts` 里断言它与生成物 `argsSchema.properties.stage.enum` 逐项相等：
 * 三处（后端清单 / 本文件 / 材料预处理页）任一处偷偷改枚举，测试就红。
 */
export const MATERIAL_PREP_STAGES = ['inbox', 'todo', 'done', 'filed'] as const
export type MaterialPrepStage = (typeof MATERIAL_PREP_STAGES)[number]

/** 判断任意值是否是预处理阶段（用于 query 与动作参数的第二道守卫） */
export function isMaterialPrepStage(value: unknown): value is MaterialPrepStage {
  return typeof value === 'string' && (MATERIAL_PREP_STAGES as readonly string[]).includes(value)
}

/**
 * 明确排除的路由模板：链接即凭证的公开上传页，与两个未登录态页面。
 * 用模板而不是实例正则来排除——`ROUTES` 改名时这里跟着红，不会静默放行。
 */
const DENIED_ROUTE_TEMPLATES: ReadonlySet<string> = new Set([
  ROUTES.clientUpload,
  ROUTES.login,
  ROUTES.socialCallback,
])

/**
 * 模板里的 `:id` 只当**单段 id**：数字 / UUID / 任务号都由它覆盖，且天然排除
 * `/`、`.`、`%`、空白——于是 `/projects/..%2fadmin`、`/projects/%2e%2e` 这类编码
 * 穿越在匹配阶段就出局，不需要再单列解码规则。
 */
const ID_SEGMENT = '[A-Za-z0-9_-]+'

/** 模板 → 精确匹配的正则（`/projects/:id` → `^/projects/[A-Za-z0-9_-]+$`） */
function templateToPattern(template: string): RegExp {
  const segments = template
    .split('/')
    .filter(Boolean)
    .map((segment) => {
      if (segment.startsWith(':')) return ID_SEGMENT
      // 字面段里的 `.` 等正则元字符要转义（`/settings/bindings` 目前没有，但模板会变）
      return segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    })
  return new RegExp(`^/${segments.join('/')}$`)
}

/** 白名单：ROUTES 去掉三个排除项后逐个编译，路由表改了这里自动跟着改 */
const NAVIGATE_PATTERNS: readonly RegExp[] = Object.values(ROUTES)
  .filter((template) => !DENIED_ROUTE_TEMPLATES.has(template))
  .map(templateToPattern)

/**
 * query 白名单：只有材料预处理页的 `stage` 是「页面自己的状态」。
 *
 * 其余 query 一律拒——`?message=<id>` 是后端深链接直达某条消息的能力，
 * 由模型自由设置等于让 AI 替律师挑「打开哪条消息」，收益为零、误伤很大。
 */
function hasAllowedSearch(pathname: string, params: URLSearchParams): boolean {
  const keys = [...params.keys()]
  // 重复 key（`?stage=todo&stage=done`）语义取决于解析方，直接拒，别赌哪边赢
  if (new Set(keys).size !== keys.length) return false
  if (keys.length === 0) return true
  if (pathname !== ROUTES.materialPrep) return false
  return keys.every((key) => key === 'stage') && isMaterialPrepStage(params.get('stage'))
}

/**
 * 模型给的 `path` → 可安全 `navigate` 的站内路径；不合法返回 `null`。
 *
 * 拒绝顺序是有讲究的：先挡「根本不是路径」的（协议、协议相对、空串），再挡
 * 「像路径但含危险字符」的（`..`、反斜杠、锚点、空白），最后才做白名单匹配。
 * 这样每条测试用例的失败原因都能在代码里一眼对上。
 */
export function pathForNavigate(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  // 先 trim：`" /material-prep "` 与 `"\n/material-prep"` 在浏览器里都可能被当作
  // 有效地址，放行等于白名单被空白绕过
  const path = raw.trim()
  if (!path) return null
  // 站内路径必须以单个 `/` 开头：顺带挡掉 `http://`、`https://`、`//evil.com`
  // （协议相对 = 跳到外站）与 `javascript:`/`data:` 这类无斜杠方案
  if (!path.startsWith('/') || path.startsWith('//')) return null
  // 反斜杠在浏览器里等价于 '/'（`/\evil.com` 会被解析成协议相对地址），与 '//' 同级封死；
  // 空白与锚点同样不认——站内没有需要它们的路径，放行只会扩大攻击面
  if (/[\s\\#]/.test(path)) return null
  // `..` 出现在任何位置都拒：不需要先解码就能穿越，而合法路径里不存在它
  if (path.includes('..')) return null

  const queryAt = path.indexOf('?')
  const pathname = queryAt === -1 ? path : path.slice(0, queryAt)
  const search = queryAt === -1 ? '' : path.slice(queryAt + 1)

  if (!NAVIGATE_PATTERNS.some((pattern) => pattern.test(pathname))) return null
  const params = new URLSearchParams(search)
  if (!hasAllowedSearch(pathname, params)) return null
  // 回填重建后的地址（而不是原串）：query 的写法被规整为唯一一种，
  // 下游看到的永远是我们确认过的那串字符
  return search ? `${pathname}?${params.toString()}` : pathname
}

/**
 * `ui_material_prep_set_stage` → `/material-prep[?message=…][&stage=…]`。
 *
 * `replace: true` 由调用方给（切筛选是原地改状态，塞进历史栈会让「后退」变成
 * 一步步退回上一个筛选，而不是回上一页）。
 *
 * 两个细节都对着一处既有实现：`?message=` 必须保住（深链接直达某条消息），
 * `inbox` 不写 `stage` 参数（它是默认阶段，`@/app/paths` 的 `materialPrep()` 同样
 * 为保持 URL 干净而省略）。
 */
export function pathForMaterialPrepStage(stage: unknown, currentPath: string): string | null {
  if (!isMaterialPrepStage(stage)) return null
  const queryAt = currentPath.indexOf('?')
  const current = new URLSearchParams(queryAt === -1 ? '' : currentPath.slice(queryAt + 1))
  const next = new URLSearchParams()
  const message = current.get('message')
  if (message) next.set('message', message)
  if (stage !== 'inbox') next.set('stage', stage)
  const search = next.toString()
  return search ? `${ROUTES.materialPrep}?${search}` : ROUTES.materialPrep
}
