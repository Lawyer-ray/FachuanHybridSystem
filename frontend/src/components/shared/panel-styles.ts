/**
 * 跨 feature 共用的面板 / 行按钮 class 常量。
 *
 * 与 button-styles.ts 同口径：字符串常量而非组件，供各 feature 的 ui.ts
 * 作基底拼接。收敛到 shared 是因为 ≥2 个 feature（home / payment-intake）
 * 逐字同款——两份手抄必然漂移（提权规则见 frontend/CLAUDE.md）。
 */

/** 首页面板（白卡）：圆角 14px + 细边 + 极轻投影 */
export const PANEL = 'rounded-[14px] border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,.02)]'

/** 行内小按钮：描边风格（列表行操作 / 工具卡结果行） */
export const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'

/** 深色主操作按钮（确认 / 提交 / 计算） */
export const BTN_PRIMARY =
  'flex h-[32px] flex-none items-center justify-center gap-1.5 rounded-[8px] bg-foreground px-[14px] text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45'
