/**
 * `manifest.route` ↔ `ROUTES` 的机械门禁：后端声明的期望路由，必须真的对应一个前端路由。
 *
 * ## 这条门禁拦的是什么
 *
 * `runUiTool` 拿 `spec.route` 做两件**按字面量**的事：判断「是不是已经在目标页」，
 * 以及作为跨页续跑的队列键（`pending.ts` 的 page）。所以 `manifest.py` 里写错一个字母、
 * 或 `paths.ts` 改名后没同步后端，表现都是「AI 说已打开并继续执行，结果页面毫无反应」
 * ——不报错、不 toast，是整条链路上最难查的静默失效。
 *
 * ## 判定口径
 *
 * `spec.route` 必须满足其一：
 * 1. **等于** `ROUTES` 里某个值（`/material-prep` = `ROUTES.materialPrep`）；
 * 2. 等于某个 `ROUTES` 模板的**静态前缀**，即去掉第一个占位段及其后所有段
 *    （`/material-prep/:id` → `/material-prep`：列表页与详情页共用同一个 route）。
 *
 * 不做前缀 `startsWith`、不做尾斜杠归一：队列键是逐字比较的，`/material-prep/`
 * 看起来等价，实际会让页面取不到队（`/material-prep` ≠ `/material-prep/`），
 * 所以这里必须也按字面量判，宁可红得早。
 *
 * 反向也要有牙齿：`/material-pre`（少一个字母）、`/material-prep-x`（看起来像子路径）
 * 都必须判红，否则本文件只是把「反正都能过」写了一遍。
 */

import { describe, expect, it } from 'vitest'

import { ROUTES } from '@/app/paths'
import { UI_TOOL_SPECS } from './generated'

/** 路由表里的模板（`/projects/:id` 也在这份里，占位段由 literalPrefix 处理） */
const ROUTE_TEMPLATES: readonly string[] = Object.values(ROUTES)

/**
 * 模板去掉第一个占位段及其后的一切：`/projects/:id/review/:taskId` → `/projects`。
 * 只认 `:` 开头的段（与 `routes.ts` 的 `ID_SEGMENT` 同一套模板写法）。
 */
function literalPrefix(template: string): string {
  const segments = template.split('/').filter(Boolean)
  const firstPlaceholder = segments.findIndex((segment) => segment.startsWith(':'))
  const literal = firstPlaceholder === -1 ? segments : segments.slice(0, firstPlaceholder)
  return literal.length === 0 ? '/' : `/${literal.join('/')}`
}

/**
 * `spec.route` 是否对应前端路由表里的某条（口径见文件头）。
 *
 * `templates` 可注入只为一个目的：真实 `ROUTES` 里每个「模板静态前缀」恰好也等于某个值
 * （`/material-prep` 既是 `materialPrep` 也是 `materialPrepDetail` 的前缀），只喂真数据
 * 无法证明 OR 的第二条还活着——删掉它测试也不会红，那就不是门禁了。
 */
function hasFrontendRoute(route: string, templates: readonly string[] = ROUTE_TEMPLATES): boolean {
  return templates.some((template) => template === route || literalPrefix(template) === route)
}

/** 只测声明了 route 的动作：`null` = 任意页面，不参与路由对齐 */
const ROUTED_SPECS = UI_TOOL_SPECS.flatMap((spec) =>
  spec.route === null ? [] : [{ action: spec.name, route: spec.route }],
)

describe('manifest.route ↔ ROUTES 门禁', () => {
  it('清单里至少有一条带 route 的动作（否则本文件整个空转，绿得毫无意义）', () => {
    expect(ROUTED_SPECS.length).toBeGreaterThan(0)
  })

  it.each(ROUTED_SPECS)('$action 的 route $route 在前端 ROUTES 里找得到对应', ({ action, route }) => {
    expect(
      hasFrontendRoute(route),
      `manifest 声明的 route ${route}（动作 ${action}）在前端 ROUTES 里找不到对应，检查 backend/apps/agent/services/ui_action/manifest.py 与 src/app/paths.ts 是否漂移`,
    ).toBe(true)
  })

  it('口径本身有牙齿：拼错字母、假子路径、尾斜杠都判红', () => {
    // 少写一个字母（最典型的漂移形态：像对的，但页面永远取不到队）
    expect(hasFrontendRoute('/material-pre')).toBe(false)
    // 看起来像子路径，但静态前缀是按段比的：`/material-prep-x` 不是 `/material-prep` 的实例
    expect(hasFrontendRoute('/material-prep-x')).toBe(false)
    // 尾斜杠不是等价写法：队列键逐字比较，`/material-prep/` 会让目标页取不到队
    expect(hasFrontendRoute(`${ROUTES.materialPrep}/`)).toBe(false)
  })

  it('模板的静态前缀确实被认（/material-prep 同时对应列表页与详情页模板）', () => {
    expect(literalPrefix(ROUTES.materialPrepDetail)).toBe(ROUTES.materialPrep)
    expect(hasFrontendRoute(ROUTES.materialPrep)).toBe(true)
  })

  it('OR 的第二条单独成立：只有「模板静态前缀」命中时也放行（/demo ← /demo/:id）', () => {
    expect(hasFrontendRoute('/demo', ['/demo/:id'])).toBe(true)
    // 少一个字母仍判红：前缀是整段比，不是 startsWith
    expect(hasFrontendRoute('/dem', ['/demo/:id'])).toBe(false)
  })
})
