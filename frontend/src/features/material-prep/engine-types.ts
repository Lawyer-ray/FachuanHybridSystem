/**
 * 双引擎交叉校验的类型（引擎码 / 变体 / 分歧 / 双框 / 定位框精度）。
 *
 * 从 types.ts 拆出：这一组只服务「两个引擎读得不一样」这条链路，与草稿本体
 * 是两个关注点；types.ts 已顶到规模硬红线。消费方仍从 `../types` 引（那里 re-export）。
 */

/**
 * 双引擎交叉校验：某个 OCR 引擎对一处文字的识别结果。
 *
 * 引擎码与后端 `dual_engine.ENGINE_*` 逐字一致；中文名见 `draft/engine.ts` 的
 * `engineLabel`（唯一一处把引擎码转成人话的地方）。
 */
export type EngineName = 'mineru' | 'paddleocr_vl' | 'textin'

export interface EngineVariant {
  engine: EngineName
  /** 摘要（截到 120 字，带省略号）。列表扫读用；不能拿它去做正文定位。 */
  text: string
  /**
   * 完整原文。缺省时（旧任务产物）退回 `text`。
   *
   * 两个用途：① 律师要看全文才能判断哪侧对；② 按完整文本定位到正文块——
   * 摘要带省略号，`includes` 必然失败，表现就是「点了采用/修改没反应」。
   */
  full_text?: string
}

/**
 * 一处引擎分歧（`PdfSplitJobOut.summary.engine_disagreements`）。
 *
 * 核心原则：**分歧 = 确定信号；一致 ≠ 正确**。两个引擎都认成「测试甲」不代表就是测试甲
 * （实测存在两引擎一致地错），所以这里只列**分歧**，不投票、不自动采信。
 *
 * 与 `Inconsistency` 的区别：那张清单是「同一枚章在本卷里被写成两种」，是**页与页之间**
 * 的矛盾，靠出现次数判断哪个是基准；这里是「同一页同一处两个引擎读得不一样」，
 * 没有次数可数，裁决权只能在律师手上。两套数据模型不复用。
 */
export interface EngineDisagreement {
  /** 绝对页号（后端 page.page_no） */
  page_no: number
  /** char = 差一个字（形近字/漏笔）；line = 同一行差多个字；missing = 只有一方有这一行 */
  kind: 'char' | 'line' | 'missing'
  severity: 'high' | 'medium' | 'low'
  /** 各引擎的识别结果；missing 类里空字符串代表该引擎没有这一行 */
  variants: EngineVariant[]
  /** 分歧处的截断原文，供清单里一眼定位 */
  context: string
  /** 是否命中唯一标识锚点（身份证号/账号）：命中即绑定到具体人/账户，优先看 */
  anchor_hit: boolean
  /** 两串相似度（0-1）；missing 类为 0。越低越可疑，清单里排前面 */
  similarity: number
  /**
   * 各引擎在这一页的块框，用于页面上的「双框对照」。
   *
   * 可选：旧任务 / 后端还没透出 bbox 时为空，那时分歧清单仍然可看，只是不画框。
   */
  blocks?: EngineBlockRect[]
}

/**
 * 某个引擎在某页认出的一个块（含坐标），用于「双框对照」。
 *
 * 坐标口径必须与 `PositionedBlock.rect` 完全一致（归一化 0-1、相对**页面图像**），
 * 否则两个框会画在不同的比例尺上，「两框重叠时都可见」就无从谈起。
 */
export interface EngineBlockRect {
  engine: EngineName
  page_no: number
  text: string
  /** 归一化 0-1 矩形；`approx` 为 true 时代表整页近似框而非精确位置 */
  rect: { x: number; y: number; w: number; h: number; approx?: boolean }
  /** 后端块类型（text/title/table/image…），只用于提示，不上色 */
  block_type: string
  /** 坐标不可信（整页近似框）：描边要更淡，不给假精度 */
  approx: boolean
}

/**
 * 定位框精度等级。
 *
 * 三档而不是单一的 `approx` 布尔：后端以前把「整页近似」与「半格误差」都写成
 * `approx: true`，前端只能画同一种虚线——律师无法区分「这个框根本不准」与
 * 「这个框八九不离十」。拆开后视觉分级：
 *
 * - `exact`：引擎真实返回的 bbox（MinerU/VL 原生）——实线，可信
 * - `cell` ：表格拆分的推算框（左右列对齐、纵向行高不均）——虚线 + ≈
 * - `page` ：整页近似（整张表没拆，坐标基本无意义）——更淡的虚线
 */
export type RectPrecision = 'exact' | 'cell' | 'page'

/** 从后端块里读精度；旧任务没有 `precision` 字段，退化成看 `approx`。 */
export function rectPrecisionOf(rect: { approx?: boolean; precision?: string } | null | undefined): RectPrecision {
  const raw = rect?.precision
  if (raw === 'exact' || raw === 'cell' || raw === 'page') return raw
  // 旧任务（后端还没透出 precision）：approx 的旧语义是「整页近似」
  return rect?.approx ? 'page' : 'exact'
}
