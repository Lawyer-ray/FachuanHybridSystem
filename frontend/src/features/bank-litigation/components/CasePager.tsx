/**
 * 案件列表分页条：`‹ 上一页` / `第 x / y 页 · 共 N 个` / `下一页 ›`。
 *
 * 视觉口径与项目主页（`workbench/components/WorkbenchPage.tsx`）的分页条逐类一致
 * ——同一串 `rounded-[9px] px-2.5 py-1`、`tabular-nums` 数字、禁用态 `opacity-35`。
 * 两处都是「服务端分页的列表」，律师在同一套界面里翻页，控件不该有两种长相。
 *
 * 无障碍：
 * - 外层 `<nav aria-label="分页">`：读屏的地标列表里能直接跳到翻页；
 * - 位置文本 `aria-live="polite"`：点「下一页」后焦点留在按钮上，不播报就等于
 *   没有任何反馈（这里同时报了位置与总数，翻页/搜索两个变化都能念到）；
 * - 禁用一律用原生 `disabled`（不是 `aria-disabled`）：原生禁用按钮自动退出
 *   Tab 序列，也点不动；请求在飞时一并禁用，避免连点翻过头。
 *
 * 只有一页时不渲染（`totalPages <= 1`）：翻不动的按钮只是噪音。
 */
export function CasePager({
  page,
  totalPages,
  total,
  loading,
  onGoto,
}: {
  page: number
  totalPages: number
  /** 命中总数（已应用关键词过滤） */
  total: number
  /** 请求在飞：保留旧列表期间禁用两侧按钮 */
  loading: boolean
  onGoto: (page: number) => void
}) {
  if (totalPages <= 1) return null

  const btnCls =
    'rounded-[9px] px-2.5 py-1 transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-35'

  return (
    <nav aria-label="分页" className="flex items-center justify-center gap-5 text-xs text-muted-foreground">
      <button type="button" disabled={loading || page <= 1} className={btnCls} onClick={() => onGoto(page - 1)}>
        ‹ 上一页
      </button>
      <span className="tabular-nums" aria-live="polite">
        第 {page} / {totalPages} 页 · 共 {total} 个
      </span>
      <button
        type="button"
        disabled={loading || page >= totalPages}
        className={btnCls}
        onClick={() => onGoto(page + 1)}
      >
        下一页 ›
      </button>
    </nav>
  )
}
