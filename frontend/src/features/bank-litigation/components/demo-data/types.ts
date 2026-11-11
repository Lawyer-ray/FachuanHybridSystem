/**
 * 演示数据 · **跨模块共享的类型**
 *
 * 这些类型被两个以上 `*-demo.ts` 用到（或使用方直接从 barrel 引类型），
 * 所以集中在这里，避免模块之间互相 import 形成环。
 * 使用方仍从 `../demo-data` 引类型，不要深引本文件。
 */

export interface SplitHistoryRow {
  id: string
  fileName: string
  pages: number
  materials: number
  /** 复核结果：全部确认 / 有需复核项 / 有未识别项 */
  result: 'confirmed' | 'review' | 'unrecognized'
  /** 归案数量（0 表示未归案） */
  imported: number
  at: string
  by: string
}

export interface OASiteRow {
  name: string
  credential: boolean
  /** 最近一次立案时间 */
  lastUsed: string
  /** 本月立案件数 */
  filedThisMonth: number
  /** 平均单件耗时（人读量级） */
  avgMs: string
  /** 最近一次登录成功时间 */
  loginAt: string
  /** 凭证体检结果：正常 / 凭证过期 */
  status: 'ok' | 'expired'
}

export type GapSource = '合同类' | '催收类' | '身份类' | '担保类'

export type GapTimelineKind = 'system' | 'sms' | 'mail' | 'wechat' | 'customer' | 'recognize'

export interface GapTimelineEvent {
  item: string
  at: string
  kind: GapTimelineKind
  channel: string
  title: string
  detail: string
}

export interface ScanMailboxConfig {
  addr: string
  note: string
  count: number
  interval: string
  folder: string
  whitelist: string
}

export interface AssignCandidate {
  name: string
  caseNo: string
  court: string
  party: string
  slots: string[]
}

export interface MailAttachment {
  subject: string
  name: string
  size: string
  kind: 'pdf' | 'image'
  pages: number
  slot: string
}

export type ClaimFilter = '全部' | '自动归案' | '待人工' | '已标记无关'

/** 扫描件预览里「版式行」的类型：用 div 模拟真实扫描件的视觉节奏 */
export type X1DocLineKind =
  | 'title' // 居中大标题
  | 'meta' // 居中编号/日期这类小字
  | 'heading' // 条款小标题
  | 'para' // 正文段落
  | 'field' // 半行字段（金额/期限）
  | 'table' // 表格行
  | 'seal' // 印章圆圈
  | 'sign' // 落款
export interface X1PageBox {
  /** 百分位定位（相对整页宽高），与真实系统的归一化坐标同口径 */
  top: number
  left: number
  width: number
  height: number
  label: string
}

export interface X1PreviewPage {
  pageNo: number
  lines: { kind: X1DocLineKind; text: string }[]
  boxes: X1PageBox[]
}
