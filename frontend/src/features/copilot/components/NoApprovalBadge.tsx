import { ShieldOff } from 'lucide-react'

/**
 * 「这个后端没有人工审批闸门」标记。
 *
 * ## 为什么要有它
 *
 * 三个后端里**只有 pi** 会把高危工具拦下来问人。另外两个：
 *
 * - **dsh**：fail-closed —— 收到 `approval/request` 一律回 `rejected`，
 *   高危调用**被直接拒绝**（安全方向对，但律师看不到审批卡）；
 * - **openai-agents**：根本不接 SDK 的 `require_approval`，高危调用**照常执行**。
 *
 * 两者行为相反，共同点是**不会弹审批卡**。后端在 `capabilities.approval` 里
 * 如实声明这一位（`BackendCapabilities` 的注释写着「`False` 的后端在高危动作上
 * 没有人工闸门，启用前必须先由合规确认」），前端只读它——不写死
 * `if (kind === 'dsh')`，新后端注册后自动跟上。
 *
 * ## 为什么必须显示在「选择之前」
 *
 * 这是合规信息，不是体验信息。只在事后（工具已经被拒/已经执行）说就失去了意义，
 * 所以多选菜单的每一行、后端切换列表的每一行、以及已发出的那一栏栏头都挂上。
 *
 * ## 文案为什么不说「谁会被拒、谁会执行」
 *
 * 那句话写在前端就等于又抄了一份后端行为表，第四、五个后端接进来时会立刻过期。
 * 标记只说事实（没有审批闸门）+ 后果（不会弹卡、由后端自己决定），具体行为回到
 * 后端代码/合规文档里查。
 */
export const NO_APPROVAL_TITLE =
  '该后端没有人工审批闸门：高危工具不会弹审批卡请求你确认，是否执行由后端自己决定。启用前请确认。'

/**
 * 红色小徽标（合规风险色，与「含身份证号」那类提示同一语义层）。
 *
 * `role="img"` + `aria-label`：它不带文字标签（只有「无审批」三字），屏幕阅读器
 * 需要读到完整语义，所以把 title 的内容同时给到 `aria-label`。
 */
export function NoApprovalBadge({ className = '' }: { className?: string }) {
  return (
    <span
      data-no-approval-badge
      role="img"
      aria-label={NO_APPROVAL_TITLE}
      title={NO_APPROVAL_TITLE}
      className={`inline-flex flex-none items-center gap-0.5 rounded-[4px] border border-red-200 bg-red-50 px-1 text-[10px] leading-4 font-normal text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300 ${className}`}
    >
      <ShieldOff className="h-2.5 w-2.5 flex-none" aria-hidden />
      无审批
    </span>
  )
}
