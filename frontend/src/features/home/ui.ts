import { SMALL_OUTLINE_BTN } from '@/components/shared/button-styles'

/** 阅读器风格的小描边按钮（与 material-prep reader/ui.ts 的 PBTN 同款，上提 shared 共用） */
export const BTN = SMALL_OUTLINE_BTN

/**
 * 纯图标的小描边按钮（日历上/下月切换）。
 * 这里必须单独定义而不能在 BTN 后面拼 'px-0'：BTN 自带 px-[13px]，
 * 后拼的 px-0 会被它覆盖（Tailwind 不保证后拼接者优先），padding 仍是 13px，
 * 28px 宽的按钮内容区只剩 2px，图标（本应 14px）被压成 0 宽——表现为"图标丢了"。
 */
export const BTN_ICON =
  'flex h-[30px] w-[28px] flex-none items-center justify-center rounded-[7px] border border-border bg-transparent text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground hover:border-zinc-300'

/** 深色主操作按钮（记一笔 / 提交 / 转换 / 计算） */
export const BTN_PRIMARY =
  'flex h-[32px] flex-none items-center justify-center gap-1.5 rounded-[8px] bg-foreground px-[14px] text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45'

/** 危险操作描边按钮（停止并删除任务等破坏性动作，配两段确认使用） */
export const BTN_DANGER =
  'flex h-[30px] flex-none items-center gap-1.5 rounded-[7px] border border-status-red/40 bg-status-red-bg px-[12px] text-[12.5px] font-medium text-status-red transition-colors hover:border-status-red/60 hover:bg-status-red/10 disabled:cursor-not-allowed disabled:opacity-45'

/** 首页面板（白卡） */
export const PANEL = 'rounded-[14px] border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,.02)]'

/** 工具卡内的输入控件 */
export const FIELD =
  'w-full rounded-[8px] border border-input bg-background px-[9px] py-[7px] text-[12px] text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground focus:border-ring/40 focus:shadow-[0_0_0_3px_rgba(24,24,27,.05)]'

/** 面板标题行的小胶囊（计数） */
export const COUNT_PILL =
  'rounded-[99px] border border-border bg-secondary px-[8px] py-[1px] text-[11px] font-semibold text-muted-foreground'

/** 行内小按钮：描边风格（工具卡结果行 / 历史弹窗行操作 / 法院短信成功弹窗四家同款）。
 *  disabled 工具类对不带 disabled 属性的按钮是纯 no-op，取并集一份即可。 */
export const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'
