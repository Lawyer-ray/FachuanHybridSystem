/**
 * 核对结果的**覆盖度口径**：后端 `coverage` 字段 → 「覆盖率 8/10 页 · 3 页无文本层」。
 *
 * 为什么单独成文件（而不是和 `run-display.tsx` 的组件放一起）：一份 `coverage` 在两个
 * 界面（待裁决清单 / 历史卡）都要说成同一句话；`CaseVerifyCard` 里原来那句
 * 「照抄一份——改任何一处都要两处一起改」，就是这里被抽出来的原因。
 *
 * 纯函数、不引 React：`react-refresh` 要求「组件文件只导出组件」，混在一起会让
 * 热更新退化并触发 lint。
 */

import type { VerifyRunOut } from './api'

/** 覆盖度（后端 `domain/compare.py` 写、`services/verify/query.py` 原样回传；缺键按「不知道」处理）。 */
interface PageCoverage {
  total: number | null
  withText: number | null
  noText: number
}

function countOf(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function pageCoverageOf(coverage: VerifyRunOut['coverage']): PageCoverage {
  const total = countOf(coverage.pages_total)
  const noText = countOf(coverage.pages_no_text)
  return {
    total,
    // 后端总会给 pages_with_text；缺的时候按总页数减缺文本页推，总页数也没有就承认不知道
    withText: countOf(coverage.pages_with_text) ?? (total != null && noText != null ? total - noText : null),
    noText: noText ?? 0,
  }
}

/**
 * 覆盖率一句话。
 *
 * `pages_no_text > 0` 必须显式写出来：那几页是图片/无文本层，比对根本没看到内容，
 * 只写「覆盖率 8/10 页」会让律师以为是随便抽了 8 页看看。
 */
export function coverageTextOf(page: PageCoverage): string {
  if (page.total == null || page.withText == null) return '覆盖度：未知'
  const base = `覆盖率 ${page.withText}/${page.total} 页`
  return page.noText > 0 ? `${base} · ${page.noText} 页无文本层，未核对` : base
}
