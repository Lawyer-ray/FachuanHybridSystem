/**
 * 材料预处理数据模型。
 * 一个「材料包」= 后端收件箱里的一条 manual_upload InboxMessage。
 * 拆分的中间态存在该消息的 draft_state（后端视为不透明 JSON，语义由此处定义）。
 *
 * 后端端点形状取自 openapi-typescript 生成物（src/types/api-schema.d.ts）；
 * draft_state 等前端自有语义与 schema 未覆盖处保留手写并注明原因。
 */

import type { components } from '@/types/api-schema'

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
  /** 稳定标识：列表 key 用。split/merge/删页后数组索引会漂移，不能用 si 当 key（会错绑状态） */
  id: string
  t: string
  fn: string
  refs: PageKey[]
  manual: boolean
  done?: boolean
  reviewFlag?: string
  confidence?: number
}

/** 后端 PDF 拆分接口返回的页段候选。
 *  取生成物 SegmentOut 的消费子集（id/order 等字段本域不消费，收进投影反而
 *  逼测试夹具补无关字段） */
export type PdfSplitSegmentSuggestion = Pick<
  components['schemas']['SegmentOut'],
  'page_start' | 'page_end' | 'segment_type' | 'segment_label' | 'filename' | 'confidence' | 'review_flag'
>

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

/** OCR 识别出的文字块（坐标为归一化 0-1 相对值；生成物 OcrBlockOut） */
export type OcrBlock = components['schemas']['OcrBlockOut']

/** OCR 整页结果（生成物 OcrResultOut） */
export type OcrResult = components['schemas']['OcrResultOut']

/** OCR 框选取字：页面上拖出的一个待确认框（坐标归一化 0-1） */
export interface OcrPending {
  mi: number
  p: number
  rect: { x: number; y: number; w: number; h: number }
  text: string
  loading: boolean
}

/** 案件搜索行（来自 /cases/search）。
 *  手写保留：生成物未给该端点声明响应 schema（裸响应），形状按真实返回维护 */
export interface CaseRow {
  id: number
  name: string
  filing_number?: string | null
  case_numbers?: { number?: string }[]
}

/** 后端 /clients 检索命中的当事人（客户库），用于委托人/对方当事人填入。
 *  基于生成物 PartyListOut；client_type 为 schema 未声明的额外字段，按可选保留 */
export type ClientHit = components['schemas']['PartyListOut'] & {
  client_type?: string | null
}

/** 收件箱附件元信息（生成物 AttachmentMeta）。
 *  PDF 页数（page_count）由后端上传时/详情读取时回填算好；缺失时前端下载 PDF 自行数页数兜底 */
export type AttachmentMeta = components['schemas']['AttachmentMeta']

/** 收件箱消息列表项（生成物 InboxMessageOut；status 收窄为材料包三态，
 *  后端实际取值即来自本域写入 draft_state 的枚举） */
export type InboxMessage = Omit<components['schemas']['InboxMessageOut'], 'status'> & {
  status: PackStatus
}

/** 收件箱消息详情（生成物 InboxMessageDetailOut，仅覆写两处）：
 *  · status 同 InboxMessage 收窄；
 *  · draft_state 是前端自有草稿语义。从未进过阅读器的包后端返回 {}
 *   （空对象，不满足 DraftState 形状），消费方必须按「可能没有有效草稿」处理
 *   （store.open / setPackStatusRemote 均如此）。 */
export type InboxMessageDetail = Omit<
  components['schemas']['InboxMessageDetailOut'],
  'status' | 'draft_state'
> & {
  status: PackStatus
  draft_state: DraftState | Record<string, never>
}
