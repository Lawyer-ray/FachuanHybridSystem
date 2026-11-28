/**
 * 路由覆盖门禁：`ROUTES` 里的每一条，要么「AI 能打开」，要么「明确排除并写明理由」。
 *
 * ## 这条门禁拦的是什么
 *
 * `ui_navigate` 的白名单由 `ROUTES` 编译而来（`routes.ts` 的 `NAVIGATE_PATTERNS`），
 * 所以**新增一条路由本身就会自动可打开**。真正会漏的是另一头：有人以为「加了路由
 * AI 就能用」，结果这条路由被 `DENIED_ROUTE_TEMPLATES` 或 query 规则挡掉了，而
 * **没人发现**——直到律师让 AI 打开它时得到一句「跳转被拒」。
 *
 * 这里把「每条路由的归属」变成可执行断言：新增一个键、既没进排除表、又打不开，
 * 这个文件就红，失败信息直接给出两条出路（补白名单 / 加排除表并写理由）。
 *
 * ## 为什么用「构造具体样例」而不是「拿模板去问」
 *
 * `pathForNavigate` 的入参是**实例路径**（`/projects/393`），不是模板
 * （`/projects/:id`）：模板带 `:` 与 `*`，直接喂进去必然被拒，测出来的红是假的。
 */

import { describe, expect, it } from 'vitest'

import { ROUTES } from '@/app/paths'
import { pathForNavigate } from './routes'

type RouteKey = keyof typeof ROUTES

/**
 * 占位段 → 具体样例。四个已知占位各给一个取值（任务口径的 `:id`→1、`:sessionId`→s1、
 * `:token`→t1、`:taskId`→t1）；未来新增的别的占位统一落到 `1`——
 * `routes.ts` 的 `ID_SEGMENT` 接受任意 `[A-Za-z0-9_-]+`，`1` 一定合法。
 */
const SAMPLE_SEGMENTS: Readonly<Record<string, string>> = {
  id: '1',
  sessionId: 's1',
  token: 't1',
  taskId: 't1',
}

/** 模板 → 具体样例路径（`/projects/:id/review/:taskId` → `/projects/1/review/t1`） */
function sampleFor(template: string): string {
  return template
    .split('/')
    .map((segment) => (segment.startsWith(':') ? (SAMPLE_SEGMENTS[segment.slice(1)] ?? '1') : segment))
    .join('/')
}

interface DeniedRoute {
  key: RouteKey
  reason: string
}

/**
 * 明确不打算让 AI 打开的页面。`key` 用 `keyof typeof ROUTES` 而不是字面量路径：
 * `ROUTES` 改名时这里**编译**就红，不会留下一条「排除的是一个已经不存在的模板」的死条目；
 * 反过来，新增路由不在这里又打不开时，下面的用例会红。
 *
 * 三条理由都不是「顺手排掉」，是三条不同的边界（见 `routes.ts` 文件头）：
 */
const DENIED_BY_DESIGN: readonly DeniedRoute[] = [
  {
    key: 'login',
    reason: '未登录态页面：把律师甩到登录页会当场丢掉他手上的会话',
  },
  {
    key: 'socialCallback',
    reason: '未登录态页面（飞书/微信授权回调）：它是一次性码的落点，不是可导航的页面',
  },
  {
    key: 'clientUpload',
    reason: '链接即凭证（/u/:token）：AI 把客户上传入口写进地址栏等于泄露它',
  },
]

/** 排除表的快速查表版（顺便把理由带进失败信息里） */
const deniedReason = new Map<string, string>(DENIED_BY_DESIGN.map((entry) => [entry.key, entry.reason]))

describe('路由覆盖门禁：ROUTES 的每个键要么能被 AI 打开，要么在排除表里写明理由', () => {
  it.each(Object.entries(ROUTES))('%s（%s）', (key, template) => {
    const sample = sampleFor(template)
    const reason = deniedReason.get(key)
    if (reason !== undefined) {
      expect(
        pathForNavigate(sample),
        `路由 ${key}（${template}）在排除表里却仍能被 AI 打开——排除理由写在 route-coverage.node.test.ts：${reason}`,
      ).toBeNull()
      return
    }
    // 失败信息就是这条门禁的「使用说明」：新人看到它应该知道下一步做什么
    expect(
      pathForNavigate(sample),
      `路由 ${key}（${template}）不能被 AI 打开，要么补白名单、要么加进排除表并写理由`,
    ).not.toBeNull()
  })

  it('排除表里的每个键都真的还在 ROUTES 里（不留过期条目）', () => {
    for (const { key } of DENIED_BY_DESIGN) {
      expect(Object.hasOwn(ROUTES, key), `排除表里的 ${key} 已不在 ROUTES 中，请删掉这条`).toBe(true)
    }
  })

  it('排除理由不许留空（没有理由的排除就是下一次被误删的对象）', () => {
    for (const { key, reason } of DENIED_BY_DESIGN) {
      expect(reason.trim().length, `排除项 ${key} 缺少理由`).toBeGreaterThan(0)
    }
  })

  it('样例构造真的把占位符换掉了（否则上面那条「能打开」是拿模板骗出来的假绿）', () => {
    for (const [key, template] of Object.entries(ROUTES)) {
      expect(sampleFor(template), `路由 ${key} 的样例仍带占位符：${sampleFor(template)}`).not.toContain(':')
    }
  })
})
