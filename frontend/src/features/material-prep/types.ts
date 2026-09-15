/**
 * 材料预处理数据模型。
 * 一个「材料包」= 后端收件箱里的一条 manual_upload InboxMessage。
 * 拆分的中间态存在该消息的 draft_state（后端视为不透明 JSON，语义由此处定义）。
 */

export type MaterialKind = 'pdf' | 'photo' | 'office'

/** 源素材（对应收件箱消息的一个附件） */
export interface BundleMat {
  partIndex: number
  n: string
  k: MaterialKind
  pages: number
  customName?: string
}

/** 页坐标：第几个来源素材 + 第几页（1 起） */
export interface PageKey {
  mi: number
  p: number
}

/** 一段材料 */
export interface Segment {
  t: string
  fn: string
  refs: PageKey[]
  manual: boolean
  done?: boolean
}

/** 标来源：页码（可选框选矩形，归一化 0-1） */
export interface SrcRef {
  mi: number
  p: number
  rect?: { x: number; y: number; w: number; h: number }
}

/** 右栏材料信息便签字段 */
export interface InfoField {
  k: string
  v: string
  src: string
  srcRef: SrcRef | null
  opts?: string[]
  ph?: string
  hint?: string
  ta?: boolean
}

/** 拆分草稿本体（持久化到后端 draft_state） */
export interface DraftState {
  mats: BundleMat[]
  segs: Segment[]
  infos: InfoField[]
}

/** 收件箱附件元信息（来自后端 AttachmentMeta） */
export interface AttachmentMeta {
  filename: string
  original_filename: string | null
  custom_filename: string | null
  size: number
  content_type: string
  part_index: number
}

/** 收件箱消息列表项 */
export interface InboxMessage {
  id: number
  source_name: string
  source_type: string
  subject: string
  sender: string
  recipient: string
  received_at: string
  has_attachments: boolean
  attachment_count: number
  uploaded_by_id: number | null
  uploaded_by_name: string
  created_at: string
}

/** 收件箱消息详情 */
export interface InboxMessageDetail extends InboxMessage {
  body_text: string
  body_html: string
  attachments: AttachmentMeta[]
  draft_state: DraftState
}
