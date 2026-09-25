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
  reviewFlag?: string
  confidence?: number
}

/** 后端 PDF 拆分接口返回的页段候选。 */
export interface PdfSplitSegmentSuggestion {
  page_start: number
  page_end: number
  segment_type: string
  segment_label: string
  filename: string
  confidence: number
  review_flag: string
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
  /** 列表分类：todo 待处理 / done 已归案 / filed 不接归档 */
  status?: PackStatus
  /** 归案信息：绑定到哪个案件/合同（办案模块消费） */
  assign?: AssignInfo
}

/** 材料包三态分类 */
export type PackStatus = 'todo' | 'done' | 'filed'

/** 归案归属信息（写入 draft_state.assign，办案端据此建案/挂合同） */
export interface AssignInfo {
  /** 归案方式：existing 追加已有案件 / new 新建案件(可挂已有合同或生成合同) */
  target: 'existing' | 'new'
  caseId?: number
  caseNo?: string
  caseTitle?: string
  /** 挂靠的既有合同（new + has 合同场景） */
  contractNo?: string
  contractTitle?: string
  /** new + 无合同场景：生成委托合同所需的字段 */
  contractFields?: Record<string, string>
}

/** OCR 识别出的文字块（坐标为归一化 0-1 相对值） */
export interface OcrBlock {
  x: number
  y: number
  w: number
  h: number
  text: string
  score: number
}

export interface OcrResult {
  width: number
  height: number
  blocks: OcrBlock[]
}

/** OCR 框选取字：页面上拖出的一个待确认框（坐标归一化 0-1） */
export interface OcrPending {
  mi: number
  p: number
  rect: { x: number; y: number; w: number; h: number }
  text: string
  loading: boolean
}

/** 案件搜索行（来自 /cases/search） */
export interface CaseRow {
  id: number
  name: string
  filing_number?: string | null
  case_numbers?: { number?: string }[]
}

/** 后端 /clients 检索命中的当事人（客户库），用于委托人/对方当事人填入 */
export interface ClientHit {
  id: number
  name: string
  is_our_client: boolean
  client_type?: string | null
  phone?: string | null
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
  status: PackStatus
  /** 分类进度：段数与已归类数 */
  segs: number
  named: number
  pages: number
  mats: number
  types: string[]
  compose: string
}

/** 收件箱消息详情 */
export interface InboxMessageDetail extends InboxMessage {
  body_text: string
  body_html: string
  attachments: AttachmentMeta[]
  draft_state: DraftState
}
