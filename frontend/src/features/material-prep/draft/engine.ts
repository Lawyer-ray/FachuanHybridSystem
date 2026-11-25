import type { CloudEngine, EngineBlockRect, EngineDisagreement, EngineName, EngineVariant, Segment } from '../types'

/**
 * 双引擎交叉校验的纯逻辑：数据收窄、引擎命名、分组排序、「已核对」键、双框对照取框。
 *
 * ## 为什么单独一层
 *
 * 后端 `summary.engine_disagreements` 是自由字典数组（旧任务 / 单引擎路径根本没有这个键），
 * 而消费方有三处（抽屉清单、左栏计数、页面双框）。三处各自 `as EngineDisagreement[]`
 * 强转的话，只要后端多加一个字段或某一页坐标缺失，打开旧材料包就可能白屏。
 * 所以这里只做一件事：把不可信的 `unknown` 收窄成明确结构，再给几组派生量。
 *
 * ## 核心原则（不可动摇）
 *
 * **分歧 = 确定信号；一致 ≠ 正确。** 这里只回答「两个引擎在哪读得不一样」，
 * 绝不给出「哪个对」的结论——裁决权在律师。所以没有投票、没有自动采纳、
 * 也没有把某一引擎的文本标成「正确写法」的字段。
 */

/** 引擎码 → 人话。唯一一处把引擎码翻译成中文名的地方，抽屉与页面框轴标注共用。 */
export function engineLabel(engine: CloudEngine): string {
  switch (engine) {
    case 'mineru':
      return 'MinerU'
    case 'paddleocr_vl':
      return 'PaddleOCR-VL'
    case 'textin':
      return 'TextIn'
    case 'deepseek':
      return 'DeepSeek'
    default:
      // 后端将来加引擎时原样显示，不丢信息（也不至于整条分歧消失）
      return engine
  }
}

/**
 * 页面上框旁的小字标注。
 *
 * 用短名而不是全名：框宽可能只有几十像素，`PaddleOCR-VL` 会盖掉框本身的内容。
 * 而律师只需要知道「这条线是主引擎还是副引擎」，全名在抽屉里已经给过了。
 */
export function engineShortLabel(engine: CloudEngine): string {
  switch (engine) {
    case 'mineru':
      return 'MinerU'
    case 'paddleocr_vl':
      return 'VL'
    case 'textin':
      return 'TextIn'
    case 'deepseek':
      return 'DeepSeek'
    default:
      return engine
  }
}

const ENGINES: readonly EngineName[] = ['mineru', 'paddleocr_vl', 'textin']

function isEngine(v: unknown): v is EngineName {
  return typeof v === 'string' && (ENGINES as readonly string[]).includes(v)
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function readVariants(raw: unknown): EngineVariant[] {
  if (!Array.isArray(raw)) return []
  const out: EngineVariant[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    if (!isEngine(r.engine)) continue
    out.push({ engine: r.engine, text: str(r.text), full_text: str(r.full_text) || undefined })
  }
  return out
}

/** 严重度未知/缺失时的兜底：排在 low 之后（「不确定」不该排在「确定是排版差异」前面） */
const SEVERITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }
const SEVERITY_UNKNOWN = 3

function isSeverity(v: unknown): v is EngineDisagreement['severity'] {
  return v === 'high' || v === 'medium' || v === 'low'
}

function isKind(v: unknown): v is EngineDisagreement['kind'] {
  return v === 'char' || v === 'line' || v === 'missing'
}

/**
 * 把 `summary.engine_disagreements`（自由字典数组）收窄。
 *
 * 逐条校验：缺页号（≤0）或缺变体的条目直接丢——没有页号就跳不过去、没有两个变体
 * 就不构成分歧，留着只会在清单里制造一条点不动也看不懂的行。
 */
export function readEngineDisagreements(raw: unknown): EngineDisagreement[] {
  if (!Array.isArray(raw)) return []
  const out: EngineDisagreement[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const pageNo = num(r.page_no)
    const variants = readVariants(r.variants)
    if (pageNo <= 0 || variants.length < 2) continue
    out.push({
      page_no: pageNo,
      kind: isKind(r.kind) ? r.kind : 'char',
      severity: isSeverity(r.severity) ? r.severity : 'low',
      variants,
      context: str(r.context),
      anchor_hit: r.anchor_hit === true,
      similarity: num(r.similarity),
      blocks: readEngineBlocks(r.blocks),
    })
  }
  return out
}

/** 把一条分歧里的 `blocks`（各引擎块框，自由字典）收窄；坐标不全的条目丢弃（画不出框） */
export function readEngineBlocks(raw: unknown): EngineBlockRect[] {
  if (!Array.isArray(raw)) return []
  const out: EngineBlockRect[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    if (!isEngine(r.engine)) continue
    const pageNo = num(r.page_no)
    if (pageNo <= 0) continue
    const rect = readRect(r.rect)
    if (!rect) continue
    out.push({
      engine: r.engine,
      page_no: pageNo,
      text: str(r.text),
      rect,
      block_type: str(r.block_type),
      approx: r.approx === true || rect.approx === true,
    })
  }
  return out
}

function readRect(raw: unknown): EngineBlockRect['rect'] | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const x = num(r.x)
  const y = num(r.y)
  const w = num(r.w)
  const h = num(r.h)
  // 零面积框画出来是一条看不见的线，等于没画
  if (w <= 0 || h <= 0) return null
  return { x, y, w, h, approx: r.approx === true }
}

/**
 * 一条分歧的稳定键：`<页号>:<kind>:<各引擎归一化后的文本>`。
 *
 * 为什么不用数组下标：`compare_pages` 每次跑出来的顺序可能变（相似度微调就会重排），
 * 「已核对」若按下标存，重跑一次就把勾全挂到别的条目上——律师会以为自己核对过。
 * 用内容做键，同一条分歧重跑后仍认得出来；内容真变了，本来就该重新看。
 */
export function disagreementKey(d: EngineDisagreement): string {
  const sig = d.variants
    .map((v) => `${v.engine}=${v.text.trim()}`)
    .sort()
    .join('|')
  return `${d.page_no}:${d.kind}:${sig}`
}

/**
 * 全卷唯一的键：在 `disagreementKey` 基础上给撞车的那几条加序号。
 *
 * ## 为什么必须加
 *
 * `disagreementKey` 只用页号 + kind + 两引擎文本。文本被 `_truncate` 截到 120 字后，
 * 同一页上内容相近的几条会算出**同一个键**。实测 164 页卷宗的 332 条分歧里，
 * 有 9 组共 27 条撞车（第 56 页一组就 6 条）。浅车有两个实际后果：
 *
 * 1. 「已核对」勾选按 key 存，勾一条会把同键的其他几条一起置灰；
 * 2. 高亮按 key 定位，点第 3 条却高亮到第 1 条（`find` 拿到第一个匹配）。
 *
 * 序号用**同键内的出现次序**而不是全量下标：重跑后同一条分歧若仍在同键组里，
 * 它的相对次序通常稳定，勾选不会跳；真的变了就该重新看。
 */
export function uniqueDisagreementKey(d: EngineDisagreement, occurrence: number): string {
  const base = disagreementKey(d)
  return occurrence > 0 ? `${base}#${occurrence}` : base
}

/**
 * 给一整份分歧清单算出「一条一份」的唯一键，与它一一对应。
 *
 * 用 Map 计数而不是 O(n²) 双循环：332 条时两者差不多，但清单是律师随手
 * 重复打开的，没必要在每次渲染里做平方级比较。
 */
export function uniqueDisagreementKeys(list: EngineDisagreement[]): string[] {
  const seen = new Map<string, number>()
  return list.map((d) => {
    const base = disagreementKey(d)
    const n = seen.get(base) ?? 0
    seen.set(base, n + 1)
    return n > 0 ? `${base}#${n}` : base
  })
}

/**
 * 清单排序：严重度 → 锚点命中 → 相似度低 → 页号。
 *
 * 锚点（身份证号/账号邻域）排在相似度之前：绑定到具体人的错字比一行普通正文的
 * 分歧致命得多，哪怕普通那处相似度更低。
 */
export function sortDisagreements(list: EngineDisagreement[]): EngineDisagreement[] {
  return [...list].sort((a, b) => {
    const ra = SEVERITY_RANK[a.severity] ?? SEVERITY_UNKNOWN
    const rb = SEVERITY_RANK[b.severity] ?? SEVERITY_UNKNOWN
    if (ra !== rb) return ra - rb
    if (a.anchor_hit !== b.anchor_hit) return a.anchor_hit ? -1 : 1
    if (a.similarity !== b.similarity) return a.similarity - b.similarity
    return a.page_no - b.page_no
  })
}

/**
 * 按严重度分组（low 另给一份，抽屉里默认折叠）。
 *
 * 分组内部沿用 `sortDisagreements` 的顺序，不重排：清单里律师已经认熟了
 * 「最上面那条最急」，换个分组就换一次顺序只会让人重新找。
 */
export function groupBySeverity(
  list: EngineDisagreement[],
  checked: ReadonlySet<string>,
): {
  high: EngineDisagreement[]
  medium: EngineDisagreement[]
  low: EngineDisagreement[]
  /** 未核对条数（已核对的仍然留在清单里但置灰，计数只算还没看的） */
  unchecked: number
} {
  const sorted = sortDisagreements(list)
  const unchecked = sorted.filter((d) => !checked.has(disagreementKey(d))).length
  return {
    high: sorted.filter((d) => d.severity === 'high'),
    medium: sorted.filter((d) => d.severity === 'medium'),
    low: sorted.filter((d) => d.severity === 'low'),
    unchecked,
  }
}

/** 分歧类型码 → 清单里的短标签。未知码原样显示，不丢信息 */
export function disagreementKindLabel(kind: EngineDisagreement['kind']): string {
  switch (kind) {
    case 'char':
      return '差一字'
    case 'line':
      return '整行不同'
    case 'missing':
      return '仅一侧有'
    default:
      return kind
  }
}

/**
 * 某段某一页上，某个引擎的块框（按页组合后的产物，供 PageCell 直接画）。
 *
 * 口径与 `Flow.hitsByPage` 完全一致：`seg.blocks[].page` 是**文档内绝对页号**，
 * 段内的 refs 只覆盖自己的页范围，所以要按「段起始页」偏移回段内下标。
 * 两处若不一致，双框会画到别的页上——这正是必须抽成纯函数、并在这里解释的原因。
 */
export function engineBlocksOfPage(
  seg: Pick<Segment, 'blocks' | 'refs'>,
  pageNo: number,
  blocks: EngineBlockRect[],
): EngineBlockRect[] {
  if (blocks.length === 0) return []
  // 先确认这一页确实在这段的 refs 里（段边界之外的页不画，否则会画到邻段页卡上）
  const firstPage = seg.refs[0]?.p ?? 1
  const ref = seg.refs[pageNo - firstPage]
  if (!ref || ref.p !== pageNo) return []
  return blocks.filter((b) => b.page_no === pageNo)
}

/**
 * 从分歧的变体里取「某引擎的文本」。
 *
 * `missing` 类的变体可能带空串（该引擎没有这一行），空串仍然要显示成
 * 「（无此行）」而不是留白——留白会让律师以为是前端漏渲染。
 */
export function variantTextOf(d: EngineDisagreement, engine: EngineName): string {
  return d.variants.find((v) => v.engine === engine)?.text ?? ''
}

/**
 * 该变体的**完整原文**（旧产物没有 `full_text` 时退回摘要）。
 *
 * 凡是「要拿去和正文块比对/写入」的地方都必须用这个，不能用 `variantTextOf`：
 * 摘要是截断的（带 `…`），拿它去 `includes` 匹配完整正文必然失败。
 */
export function variantFullTextOf(d: EngineDisagreement, engine: EngineName): string {
  const v = d.variants.find((x) => x.engine === engine)
  return v?.full_text || v?.text || ''
}
