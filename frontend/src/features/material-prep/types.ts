/**
 * 材料预处理数据模型。
 * 一个「材料包」= 后端收件箱里的一条 manual_upload InboxMessage。
 * 拆分的中间态存在该消息的 draft_state（后端视为不透明 JSON，语义由此处定义）。
 *
 * 后端端点形状取自 openapi-typescript 生成物（src/types/api-schema.d.ts）；
 * draft_state 等前端自有语义与 schema 未覆盖处保留手写并注明原因。
 */

import type { components } from '@/types/api-schema'
import type { EngineDisagreement, EngineName } from './engine-types'
import type { Inconsistency, PageQuality } from './quality-types'

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

/**
 * 一页正文在段 md 里的字符区间（左闭右开，**不含**后端注入的段标题行）。
 *
 * 与后端 `segments_md.json` 的 `page_spans` 同口径（API 字段 snake_case，
 * 映射到 `Segment.pageSpans`）。切段/并段靠它把正文按页精确搬走——没有它只能
 * 按 blocks 页号近似圈范围，表格页必然圈不准。
 */
export interface PageSpan {
  page: number
  start: number
  end: number
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
  /** 后端的复核标记中文名（`SegmentOut.review_flag_label`）；旧草稿没有，前端按 reviewFlag 兜底 */
  reviewFlagLabel?: string
  /** 这一段是怎么分出来的（`SegmentOut.source_method`）：rule / layout_title / llm …。
   *  复核原因要看它——同样是低置信度，起因不同、该核对的东西也不同 */
  sourceMethod?: string
  confidence?: number
  /** 该段正文的 Markdown 重建（云端识别产出，供后续 AI 流程消费）；人工拆分 / 旧任务无 */
  md?: string
  /**
   * 每页正文在 `md` 里的字符区间（后端 `page_spans`）。切/并段按它精确搬运正文。
   * 旧任务没有该字段时按 blocks 页号近似兜底；律师整段改写 md 后偏移失效，置空。
   */
  pageSpans?: PageSpan[]
  /**
   * 有一处块改动没能同步进 md（改前的原文在 md 里锚不到）。
   * 两视图不同步必须让律师看见——静默留旧值正是「以为改好了其实没改」的来源。
   * 整段改写 md 后清除（律师已给出权威正文）。
   */
  mdDrift?: boolean
  /** 该段的可定位块（原文坐标索引）；无坐标的后端 / 旧任务为空
   *  rect 为归一化 0–1，rect.approx 为 true 时代表"整页近似框"而非精确位置 */
  blocks?: PositionedBlock[]
  /** 本段的质量标记（后端 SegmentOut.quality_flags 的项目）。旧任务 / 人工拆分没有该字段 */
  qualityFlags?: string[]
  /**
   * 这一段在后端的出处：拆分任务号 + 分段主键（`PdfSplitSegment.id`）。
   *
   * 为什么必须随身带："下载已经转好的 Markdown / 分好段的 PDF" 两个端点都是
   * `/pdf-splitting/jobs/{job_id}/segments/{segment_id}/...`，而本地的段是前端自己
   * 切的（`id` 是 `seg-3` 这种本地串，跟后端主键毫无关系），草稿里也不存任务号。
   * 不带这两个值就只能靠"按页范围去猜后端是哪一段"，切/并过一次就错位。
   *
   * 什么时候**没有**：人工切段/并段/旧草稿——这些段后端根本没有产物，缺省时
   * 下载 UI 整块不渲染（不给"点了一定失败"的入口）。
   */
  splitRef?: SegmentSplitRef
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

/** 段的后端坐标：哪个拆分任务产出的、在那边的主键是多少。见 `Segment.splitRef` */
export interface SegmentSplitRef {
  jobId: string
  /** `PdfSplitSegment.id`（自增主键）。**不是**本地列表下标，也不是 `Segment.id` */
  pk: number
}

/** 后端 PDF 拆分接口返回的页段候选。
 *  取生成物 SegmentOut 的消费子集（order 等字段本域不消费，收进投影反而逼测试
 *  夹具补无关字段）。`id` 单独在下面声明成**可选**：它只在"下载已切好的产物"
 *  时需要，规则引擎分流等构造点拿不到真实主键，逼它们补一个假 id 只会更糟 */
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
  // 段级分段来源（llm/rule）：summary.segment_backend 说 mixed 时，靠它数出**哪几段**
  // 是规则引擎兜的，提示律师重点复核（宁可说规则，也不能把规则引擎说成 LLM）
  | 'source_method'
> & {
  /** 后端分段主键（`SegmentOut.id`）：下载该段已切好的 pdf/md 靠它定位（→ `Segment.splitRef`） */
  id?: number
  /** 该段的质量标记（如图形页 / 稀疏页）。后端若要扩展新取值，前端按字符串兜底展示 */
  quality_flags?: string[]
  /** 复核标记的中文名（SegmentOut 必带；这里声明成可选，免得测试夹具被迫补无关字段） */
  review_flag_label?: string
  /** 每页正文在 content_md 里的字符区间（与 content_md 同口径的 snake_case）。旧任务没有该键 */
  page_spans?: PageSpan[]
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
 * 识别质量统计与双引擎分歧的类型已按关注点拆到 `quality-types.ts` / `engine-types.ts`
 * （本文件曾顶到 450 行硬红线）。这里 re-export，消费方的 `../types` 引法不变。
 */
export type { PageQuality, DocMissing, Inconsistency } from './quality-types'
export type { EngineName, EngineVariant, EngineDisagreement, EngineBlockRect, RectPrecision } from './engine-types'
export { rectPrecisionOf } from './engine-types'

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

/** 页旋转角度：顺时针增量（相对 PDF 自身 `/Rotate`），只允许 90 的倍数 */
export type RotDeg = 0 | 90 | 180 | 270

/**
 * 页旋转覆盖表：key = `${partIndex}:${page}`（page 从 1 起）。
 *
 * 见 `draft/page-rotation.ts` 的模块文档：旋转记在草稿里、由各「材料化边界」
 * 在生成 PDF 时烧入，源附件一个字节都不改。
 */
export type PageRotMap = Record<string, RotDeg>

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
   * 页旋转覆盖（人工前置，随草稿持久化）。
   *
   * 为什么它是「律师的动作」而不是机器事实：倒着送纸扫描会得到 180° 的页，
   * 律师转正是为了自己看得懂，并把正方向一路带到归案/归档/下载的 PDF 里。
   * 键是 `partIndex:page`，与切段无关，所以切/并/删段都不会让旋转错位。
   *
   * 缺省（存量草稿没有该键）= 全部按原方向，与本字段加入前的行为一致。
   * 口径与烧入点见 `draft/page-rotation.ts`。
   */
  pageRot?: PageRotMap
  /**
   * 页级质量统计（哪些页是图纸 / 稀疏 / 空白）。
   *
   * 描述的是「这次识别产出了什么」，但**随草稿持久化**：消费方（`graphicPagesOf` /
   * `docHintPagesOf`）拿 `seg.refs` 与它实时求交集，律师切段/删页后提示跟着变，
   * 不存在错位；不落盘反而会让刷新一次提示就没了。口径见 `DraftStateToSave`。
   */
  pageQuality?: PageQuality
  /**
   * 双引擎分歧清单（`summary.engine_disagreements`，默认关闭双引擎时为空/缺省）。
   *
   * 与 pageQuality 同级、同生命周期：它也是「这次识别产出了什么」的附带事实，
   * 律师的切段/合段不改变它描述的东西。
   */
  engineDisagreements?: EngineDisagreement[]
  /**
   * 已经人工核对过的分歧（键为 `draft/engine.ts` 的 `disagreementKey`）。
   *
   * 为什么落草稿而不是组件 state：律师核对到一半按 Esc / 刷新一次就得从头再来一遍，
   * 而这些分歧动辄几十条。它记录的是**律师的判断**（“这处我已经看过了”），
   * 不是识别结果，所以与 pageQuality 那种机器事实区分开、随草稿持久化。
   */
  engineChecked?: string[]
  /**
   * 本包的识别成本选择（版面策略 + 引擎勾选），**按包持久化**。
   *
   * 为什么落草稿而不是只留会话态：这两项直接决定这一包要不要多付云端费用，
   * 律师对「银行流水包开双引擎、对电子合同包只抽文本层」的判断是**按包**做的，
   * 换包复位、重开同一包又得重选一遍等于把他的判断丢掉。
   *
   * 缺省（存量草稿没有该键）= 仅文本层 + 自动容灾，与本字段加入前的行为一致；
   * 新建包的默认值由 `buildInitialDraft` 写入（见该函数注释里的计费说明）。
   */
  recognition?: RecognitionPrefs
}

/**
 * 自动分段的可选解析引擎（勾选集合的元素）。
 *
 * 取值与后端 `cloud_backend` / `dual_engines` 的字符串逐字一致，也与
 * `EngineName`（双引擎分歧数据里的引擎码）同一套拼写——两处若不一致，
 * 「勾了 PaddleOCR-VL」与「分歧里出现 paddleocr_vl」就对不上。
 *
 * 定义在域根 types.ts 而不是 `components/reader/platform-selection.ts`：
 * 阅读器会话契约（reader-state.ts）与 store 都在域根层，根层不该反向指向子目录。
 */
export type CloudEngine = EngineName

/** 勾选的引擎集合。**空数组 = 自动容灾**（不勾任何引擎时的默认行为） */
export type CloudSelection = CloudEngine[]

/** 菜单里的固定顺序：MinerU 在最前，因为它也是双引擎的正主（见 `resolveBackendRequest`） */
export const CLOUD_ENGINES: readonly CloudEngine[] = ['mineru', 'paddleocr_vl', 'textin']

function isCloudEngine(v: unknown): v is CloudEngine {
  return typeof v === 'string' && (CLOUD_ENGINES as readonly string[]).includes(v)
}

/**
 * 把任意来源的值收窄成引擎集合。
 *
 * 为什么要收窄：选择集来自 store（`localStorage` 持久化 / 旧会话留下的单值 `'auto'`），
 * 不是可信形状。旧值 `'auto'`、`null`、未知引擎名一律当「没勾」（= 容灾）——
 * 宁可回到安全的默认行为，也不要带着一个不存在的引擎去请求云端。
 *
 * 同时去重并按 `CLOUD_ENGINES` 固定排序：勾选顺序不该影响标题文案与正主选择。
 *
 * 定义在域根而不是 `components/reader/platform-selection.ts`：store 与
 * reader-state 都在域根层，根层不该反向指向子目录（E6）。
 */
export function normalizeCloudSelection(raw: unknown): CloudSelection {
  if (!Array.isArray(raw)) return []
  const picked = new Set(raw.filter(isCloudEngine))
  return CLOUD_ENGINES.filter((e) => picked.has(e))
}

/** 勾上 / 取消一个引擎。返回**新数组**（zustand 靠引用变化触发订阅） */
export function toggleCloudEngine(selection: CloudSelection, engine: CloudEngine): CloudSelection {
  const has = selection.includes(engine)
  const next = has ? selection.filter((e) => e !== engine) : [...selection, engine]
  return normalizeCloudSelection(next)
}

/** 材料包级的识别成本选择（`DraftState.recognition`） */
export interface RecognitionPrefs {
  /** fast_text = 电子页只抽文本层（不计费、无坐标）；layout = 电子页也上云（更准、更慢、按页计费） */
  layoutMode?: 'fast_text' | 'layout'
  /** 勾选的云端引擎：空 = 自动容灾；1 个 = 锁定；≥2 个 = 交叉比对（多付一次云端费用） */
  engines?: EngineName[]
}

/**
 * 会回写到后端 draft_state 的草稿形状。
 *
 * 原先这里 `Omit<DraftState, 'pageQuality'>`——理由是「质量统计是这次识别的附带事实，
 * 落盘后会和律师后来的切段/合段/删页错位，刷新就变成假提示」。
 *
 * 但那个担心代码里已经天然解决了：`graphicPagesOf` / `docHintPagesOf` 都是拿
 * `seg.refs` 与 `quality.*_pages` **实时求交集**，段变了提示跟着变，不存在错位。
 * 而不落库的代价很实在——**刷新一次提示就没了**，律师得重新点「自动识别」才看得到，
 * 而这个功能的意义恰恰是「打开就知道哪页要核对」。
 *
 * 所以改回完整形状，pageQuality 随草稿一起持久化。
 */
export type DraftStateToSave = DraftState

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
