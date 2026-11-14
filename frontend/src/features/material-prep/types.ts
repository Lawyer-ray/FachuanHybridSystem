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
  /** 来源压缩包名（该素材是压缩包展开产物时有值，UI 悬浮展示） */
  from?: string
  /**
   * `pages` 是不是**真实数出来的**。
   *
   * 为何需要这个字段：PDF 页数读不出来时（未回填 page_count、下载/解析失败），
   * `resolveMat` 兜底给 `pages: 1`。但这个 1 是**猜的**，不是真的只有一页。
   *
   * 不给真实页数会让下游误判：归案时 `cases.ts` 用 `pages` 判断「这段是否
   * 已覆盖整份」，`pages=1` 配上任意 `pageStart=1,pageEnd=1` 的段就被当成
   * 「覆盖整份」→ 把 68MB 整卷当 1 页材料传上去，且标 `degraded:false` 不提示。
   *
   * 不能直接把兜底改成 `pages: 0`：`initialSegments` 里是
   * `for (p = 1; p <= pages; p++)`，0 会产出 **空 refs 的空段**，阅读器直接挂掉。
   * 所以保留 `pages: 1`（保证至少有一段），另用本标志告诉消费方
   * 「这个页数不可信，涉及按页切分的判断请走保守分支」。
   *
   * 缺省（undefined）= 页数可信（非 PDF 固定 1 页 / 后端回填 / pdf.js 数出）。
   */
  pagesUnknown?: boolean
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
  /** 系统最近一次分配的默认名；fn 与之相等即「仍是默认名」，切/并/改类型时会跟着刷新。
   *  用户手改过 fn 后两者不等，刷新就绕开它。老草稿没有此字段，按名字模式回退判定；
   *  后端序列化会把缺失回成 null */
  fnAuto?: string | null
  reviewFlag?: string
  confidence?: number
  /** 该段正文的 Markdown 重建（云端识别产出，供后续 AI 流程消费）；人工拆分 / 旧任务无 */
  md?: string
  /** 该段的可定位块（原文坐标索引）；无坐标的后端 / 旧任务为空
   *  rect 为归一化 0–1，rect.approx 为 true 时代表"整页近似框"而非精确位置 */
  blocks?: PositionedBlock[]
  /** 本段的质量标记（后端 SegmentOut.quality_flags 的项目）。旧任务 / 人工拆分没有该字段 */
  qualityFlags?: string[]
  /** 人工动过的痕迹：重跑自动识别时用它判断是否该弹窗询问 */
  manualEdit?: {
    /** 改过 Markdown 正文 */
    md?: boolean
    /** 改过段名 */
    name?: boolean
    /** 改过类型 */
    type?: boolean
    /** 最后修改时间（ISO） */
    at?: string
  }
}

/** 后端 PDF 拆分接口返回的页段候选。
 *  取生成物 SegmentOut 的消费子集（id/order 等字段本域不消费，收进投影反而
 *  逼测试夹具补无关字段） */
export type PdfSplitSegmentSuggestion = Pick<
  components['schemas']['SegmentOut'],
  | 'page_start'
  | 'page_end'
  | 'segment_type'
  | 'segment_label'
  | 'filename'
  | 'confidence'
  | 'review_flag'
  | 'content_md'
> & {
  /** 该段的质量标记（如图形页 / 稀疏页）。后端若要扩展新取值，前端按字符串兜底展示 */
  quality_flags?: string[]
  /** 全本页级质量统计：哪些页是图纸、哪些页几乎没字。旧任务没有该键 */
  page_quality?: PageQuality
  /** 全本跨页文字不一致（同一枚章/同一个字段被识别成两种写法） */
  inconsistencies?: Inconsistency[]
  // positioned 单独声明成可选：旧任务的 segments_md.json 没有该字段、后端回空数组，
  // 本域不消费坐标时（如规则引擎分流）也无须传。用独立可选字段而不是 Partial<>，
  // 因为 Partial<> 会把上面 8 个必填字段也一起变成可选。
  positioned?: PositionedBlock[]
}

/** 可定位的正文块（识别定位）：后端已把各家里标系统一成 0–1 矩形 */
export type PositionedBlock = components['schemas']['PositionedBlockOut']

/**
 * 页级质量统计（`PdfSplitJobOut.summary.page_quality`）。
 *
 * 真实痛点：164 页卷宗里 p147 是宗地图、p148 是平面图，OCR 只出 6 个字和 47 个字。
 * 律师在正文里看到几行零散字符，根本不知道那是图纸——而图纸恰恰是抵押案件的关键证据。
 *
 * 后端把三类「正文不可信」的页分开给：图形页（图纸/印章/照片）、稀疏页（字太少）、
 * 空白页。前端只消费前两类做提示，空白页不打扰律师（删页是另一条交互）。
 *
 * 全部字段按可选读取：旧任务的 summary 里没有这个键，缺了不能崩。
 */
export interface PageQuality {
  graphic_pages?: number[]
  sparse_pages?: number[]
  blank_pages?: number[]
  /** 逐页说明，键是页号字符串（"147": "疑似图形页…"） */
  details?: Record<string, string>
  /**
   * 证件页标识：键是页号字符串（"23"），值是证件类型码（`id_card` / `household` /
   * `marriage` / `property_cert` / `license` / `income_proof`）。旧任务没有该键。
   *
   * 与 `graphic_pages` 的区别：「图纸看不出内容」是**没有**内容，
   * 「证件页关键字段未读出」是**该有的内容在那儿但没读出来**——
   * 姓名、身份证号、住址是律师必须抄进卷宗的东西，指着「这页是图纸」没用。
   */
  doc_hints?: Record<string, string>
  /**
   * 证件页未读出的字段（`summary.page_quality.doc_missing`，键=页号）。
   *
   * 只有 `doc_hints` 非空的页才出现在这里。`missing` 为空数组不代表「没问题」：
   * 它表示工程上认得出类型、预期字段也都命中，但整页内容可疑（如满是乱码），
   * 律师看一眼类型就该去核对原页。
   */
  doc_missing?: Record<string, DocMissing>
}

/** 一页证件材料的缺字段记录（`PageQuality.doc_missing` 的条目） */
export interface DocMissing {
  /** 证件类型码（与 `doc_hints` 同口径） */
  doc?: string
  /** 未读出的字段名（原样展示，不翻译）；空数组 = 字段都在但内容可疑 */
  missing?: string[]
}

/**
 * 跨页文字不一致（`PdfSplitJobOut.summary.inconsistencies`）。
 *
 * 真实痛点：同一枚章被识别 150+ 次，其中 5 次错成「罗问文」（应为「罗向文」）。
 * 逐页翻不可能发现，所以列成全局清单，按 confidence 把最可疑的排在最前。
 */
export interface Inconsistency {
  /** 出现次数多的那个写法（视为正确写法） */
  canonical: string
  /** 出现次数少的那个写法（疑似错字） */
  variant: string
  canonical_count: number
  variant_count: number
  /** 不一致出现的页号（绝对页号） */
  pages: number[]
  /** 置信度：high 排最前；后端可能给空串或其他等级，按 low 兜底排序 */
  confidence: string
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
  /**
   * 页级质量统计（哪些页是图纸 / 稀疏 / 空白）。
   *
   * **只用于展示，不入库**：它描述的是「这次识别产出了什么」，落盘后会与之后的
   * 切段 / 删页错位。持久化口径见 `DraftStateToSave`（draft-persistence 与 api 剔除该字段）。
   */
  pageQuality?: PageQuality
}

/** 会回写到后端 draft_state 的草稿形状：剔除 "这次识别"才成立的展示型字段 */
export type DraftStateToSave = Omit<DraftState, 'pageQuality'>

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

/** 案件搜索行（来自 /cases/search，生成物 CaseOut）。
 *  消费子集投影；id 覆写为必有（生成物按 ModelSchema 口径可选可空）。 */
export type CaseRow = Pick<
  components['schemas']['CaseOut'],
  'name' | 'filing_number' | 'case_numbers'
> & { id: number }

/** 后端 /clients 检索命中的当事人（客户库），用于委托人/对方当事人填入。
 *  基于生成物 PartyListOut；client_type 为 schema 未声明的额外字段，按可选保留 */
export type ClientHit = components['schemas']['PartyListOut'] & {
  client_type?: string | null
}

/** 收件箱附件元信息（生成物 AttachmentMeta）。
 *  PDF 页数（page_count）由后端上传时/详情读取时回填算好；缺失时前端下载 PDF 自行数页数兜底 */
// expanded_from：压缩包展开产物的来源压缩包名（后端 get_public_attachments_meta
// 透出，openapi 生成物未覆盖该字段，这里本地扩展）
export type AttachmentMeta = components['schemas']['AttachmentMeta'] & {
  expanded_from?: string | null
}

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
