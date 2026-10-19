/**
 * 跨 feature 共用的按钮 class 常量（home / material-prep 两域逐字同款）。
 *
 * 字符串常量而非组件：这些样式只在两域的 ui.ts 里作基底（拼接 / 直接引用），
 * 收敛到 shared 是为了两份手抄不再漂移（shared 提权规则：≥2 feature 共用）。
 */

/** 30px 高的小描边按钮（阅读器工具组 / 首页面板头部同款） */
export const SMALL_OUTLINE_BTN =
  'flex h-[30px] flex-none items-center gap-1 rounded-[7px] border border-border bg-transparent px-[13px] text-[12.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground hover:border-zinc-300'
