import type { components } from '@/types/api-schema'

/**
 * 收件箱页数据模型。
 *
 * 一律取 openapi 生成物再按需要收窄，不手抄字段（与 material-prep/types.ts 同口径）。
 */

/** 收件箱列表行（生成物 InboxMessageOut）。
 *
 *  att/转材料包等字段在生成物里已声明；生成物对后端带默认值的字段标成可选，
 *  这里统一归一化为必有——后端 Schema 有默认值即恒返回，前端不必到处 `?? `。
 */
export type InboxRow = components['schemas']['InboxMessageOut']

/** 消息详情（含正文纯文本/HTML 与附件元信息） */
export type InboxDetail = components['schemas']['InboxMessageDetailOut']

/** 单个附件元信息 */
export type InboxAttachment = components['schemas']['AttachmentMeta']

/** 标记已读接口的返回 */
export interface ReadStateResult {
  ok: boolean
  message_id: number
  is_read: boolean
  read_at: string | null
}

/** 转材料包接口的返回：pack_id 即新生成（或已存在）的材料包消息 id */
export interface ConvertResult {
  ok: boolean
  message_id: number
  pack_id: number
}

/**
 * 来源筛选（左侧筛选条）。
 *
 * 值是后端 source_type 的多值串（逗号分隔），后端 list_messages 已支持多值。
 * `pack` 把律师手动包与客户链接包合成一档：对律师而言它们都是「当事人交来的材料」，
 * 没必要在收件箱里分成两行。
 */
export type InboxSourceFilter = 'all' | 'court_inbox' | 'imap' | 'court_sms' | 'manual_upload,client_upload'

/** 来源筛选档位定义（顺序即筛选条渲染顺序） */
export interface InboxSourceTab {
  key: InboxSourceFilter
  label: string
}

/**
 * 单条消息的「可进入材料预处理」判定。
 *
 * manual_upload / client_upload 本身就是材料包 → 直接进阅读器；
 * 其余来源需先走 /convert 把附件搬成材料包。已转过（converted_message_id 非空）
 * 的也直接进，不重复搬运。
 *
 * 参数只收三个判定真正需要的字段（`PackJudgement`），不收完整 InboxRow：
 * 首页收件箱卡用的是一份 Pick 投影（只声明得用到的字段），让这些函数接受
 * 结构兼容的最小类型，比让调用方 `as` 成一条假完整行安全得多。
 */
export interface PackJudgement {
  id: number
  source_type: string
  has_attachments: boolean
  converted_message_id?: number | null
}

export function packIdOf(row: PackJudgement): number | null {
  const isPack = row.source_type === 'manual_upload' || row.source_type === 'client_upload'
  if (isPack) return row.id
  return row.converted_message_id ?? null
}

/** 消息是否属于「已有材料包」（无需转换即可进材料预处理） */
export function isPackSource(row: PackJudgement): boolean {
  return row.source_type === 'manual_upload' || row.source_type === 'client_upload'
}

/** 能否转材料包：有附件 + 非材料包来源 + 尚未转过 */
export function canConvert(row: PackJudgement): boolean {
  return row.has_attachments && !isPackSource(row) && !row.converted_message_id
}
