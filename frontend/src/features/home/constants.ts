/** 类别中文名（用于徽章与抽屉） */
export const KIND_LABEL: Record<string, string> = {
  court: '庭期',
  deadline: '期限',
  meeting: '日程',
  follow: '跟进',
}

/** 类别 → tailwind 徽章类名（紧要=红，常规=灰） */
export const KIND_BADGE: Record<string, string> = {
  court: 'border-status-red/30 bg-status-red-bg text-status-red',
  deadline: 'border-status-red/30 bg-status-red-bg text-status-red',
  meeting: 'border-border bg-secondary text-secondary-foreground',
  follow: 'border-border bg-secondary text-secondary-foreground',
}

/** 类别 → 日历事件行的 tailwind 类名 */
// 紧要事项（庭期/期限）用近黑底白字：原先用 status-red 实底白字，
// 在浅色主题下字显得发虚、不清晰。深底白字对比度更高，也和 navbar 的
// 「新建案件」按钮、深色主按钮同一套语言。左侧仍用红色圆点标示紧要。
export const KIND_ROW: Record<string, string> = {
  court: 'bg-foreground text-background',
  deadline: 'bg-foreground text-background',
  meeting: 'text-foreground',
  follow: 'text-foreground',
}

/** 快捷工具展示用的端点注释（与后端真实路径一致，便于核对） */
export const TOOL_ENDPOINT = {
  courtSms: 'POST /automation/court-sms',
  docConvert: 'POST /doc-convert/convert',
  docConverter: 'POST /doc-converter/jobs',
  lpr: 'POST /lpr/calculate',
} as const

/** 周一起始的星期标题 */
export const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'] as const
