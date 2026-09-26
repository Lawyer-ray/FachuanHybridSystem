/**
 * 首页 · 今日工作台的本地类型。
 *
 * 日历事件本身用 api.ts 里的 CalendarEvent（直接对应后端 GET /reminders/calendar
 * 的返回）。以前这里放 DayEvent 并前端自己做归一化 / 合并 / 统计，现在这些都移到
 * 后端（与 Django admin 日历共用同一 service），两份定义必然漂移，故删除。
 */

/** 待处理流入项（来自收件箱 /inbox/messages） */
export interface InboxItem {
  id: number
  kind: 'sms' | 'mat' | 'mail'
  sourceLabel: string
  who: string
  title: string
  at: string
  status: string
  action: string
  /** 是否紧急（法院短信）——用于图标与状态的红色强调 */
  hot: boolean
}

/** 快捷工具：要素式转换的文书模板项 */
export interface ConvertTemplate {
  mbid: string
  name: string
}

/** LPR 计算结果（/lpr/calculate 的响应节选） */
export interface LprResult {
  success: boolean
  totalInterest: string
  totalDays: number | null
  startDate: string | null
  endDate: string | null
  message: string | null
  /** 分档明细概要：如「3.10% × 19 天」 */
  summary: string
}
