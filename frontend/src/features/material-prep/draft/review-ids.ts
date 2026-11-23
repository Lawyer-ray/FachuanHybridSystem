/**
 * 复核项的 **id 契约**：`ReviewItem` 的形状 + `reviewItemId` 的生成规则。
 *
 * 单独成文件是因为这两样东西会进草稿 JSON（`DraftState.reviewChecked`），
 * 属于持久化契约：改形状或改 id 拼法都会让律师已勾的「已核对」失效。
 * 信号归一（`review-items.ts`）与排序分组（`review-sort.ts`）都能自由演进，
 * 唯独这里动一次就要想清楚兼容。
 */

/** 复核项的类型，决定颜色与图标 */
export type ReviewItemKind =
  | 'disagreement'
  | 'doc_missing'
  | 'graphic'
  | 'sparse'
  | 'inconsistency'
  | 'quality'

/** 一条待复核项。所有信号源最终都归一成这个形状。 */
export interface ReviewItem {
  /** 稳定 key，用于「已核对」持久化。见 `reviewItemId` */
  id: string
  kind: ReviewItemKind
  /** 绝对页号 */
  page: number
  /** 严重度：决定排序与颜色 */
  severity: 'high' | 'medium' | 'low'
  /** 一句话标题，如「引擎分歧：曾妙焮 / 曾妙焱」 */
  title: string
  /** 明细（可空），如两个引擎的原文对照 */
  detail?: string
  /** 原文片段，用于在 Markdown 正文里定位 */
  needle?: string
  /** 原图上的位置（归一化 0-1），用于画框；没有就不画 */
  rect?: { x: number; y: number; w: number; h: number }
  /** 是否含身份证号等锚点，优先展示 */
  anchor?: boolean
}

/**
 * 多段文本拼成 id 签名。
 *
 * 只在段间加分隔符、去掉空白与空段：**不做排序**——同一处文字的原文/明细谁在前
 * 是有语义的（原文定位优先），而顺序本身是稳定的。会随重跑漂移的东西（引擎变体的
 * 给出顺序）在调用处就**先排序**再传进来，见 `disagreementNeedle`。
 */
function signatureOf(parts: string[]): string {
  return parts
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .join('|')
}

/**
 * kind → id 短码。
 *
 * 写死成短串而不是直接拼 kind 全名：这些键会进草稿的 `reviewChecked`，要能一眼读懂；
 * 也正因为它进了持久化数据，**改动任一短码就等于让已存的「已核对」全部失效**，
 * 所以这份映射是持久化契约，不是随手可调的文案。
 */
const ID_PREFIX: Record<ReviewItemKind, string> = {
  disagreement: 'dis',
  doc_missing: 'docmiss',
  graphic: 'graphic',
  sparse: 'sparse',
  inconsistency: 'incon',
  quality: 'quality',
}

/**
 * 生成一条复核项的稳定 id：`<kind 短码>:<页号>:<内容签名>`。
 *
 * 签名取自**内容**（原文片段 → 明细 → 标题，取第一个非空的），不用数组下标：
 * 后端重跑一次识别、顺序一换，按下标存的勾就挂到别的条目上了——律师会以为
 * 自己核对过，而这恰恰是复核清单唯一不能出的错。
 *
 * 为什么不用哈希：id 会进草稿 JSON，可读的键在排查「勾错了哪条」时能直接看懂，
 * 而 `<页号>:<原文>` 本身已经足够唯一。
 */
export function reviewItemId(item: Omit<ReviewItem, 'id'>): string {
  const short = ID_PREFIX[item.kind] ?? item.kind
  // 只取「原文片段」与「标题」：`detail` 是对照文案（"mineru=X / paddleocr_vl=Y"），
  // 引擎给出顺序一变它就变，拿它做 id 会让同一处分歧重跑后算成两条。
  const sig = signatureOf([item.needle ?? '', item.title])
  return sig ? `${short}:${item.page}:${sig}` : `${short}:${item.page}`
}
