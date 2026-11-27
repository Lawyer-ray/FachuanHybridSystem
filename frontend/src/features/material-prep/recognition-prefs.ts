/**
 * 识别成本选择：勾哪些云端引擎、怎么分段、要不要自动裁定分歧。
 *
 * 从 `types.ts` 拆出：这一段是**运行期会变的选择**（律师按包挑引擎、挑分段策略），
 * 而 `types.ts` 剩下的是**描述一份材料的模型**。两者改动理由不同，混在一起会让
 * 那个文件每次都跟着涨。顺带把三个读脏值的收窄函数从「纯类型文件」里挪出来——
 * 纯类型文件里躺着可执行代码，是没人会去那里找逻辑的经典陷阱。
 *
 * 消费方仍从 `../types` 取（`types.ts` re-export 本文件），改为直接引本文件也合法。
 */

import type { EngineName } from './engine-types'

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
export type CloudEngine = EngineName | 'deepseek'

/** 勾选的引擎集合。**空数组 = 自动容灾**（不勾任何引擎时的默认行为） */
export type CloudSelection = CloudEngine[]

/** 菜单里的固定顺序：MinerU 在最前，因为它也是双引擎的正主（见 `resolveBackendRequest`）。
 *
 *  `deepseek` 排最后且**不参与交叉比对**（后端 `DUAL_ENGINE_CHOICES` 里没有它）：
 *  它只能当 `cloud_backend` 用，所以勾了它之后要么是正主、要么是 auto 链上的兜底。
 *  它的真实价值是「MinerU/Textin 整批失败时把结果捞回来」，不是第二意见。 */
export const CLOUD_ENGINES: readonly CloudEngine[] = ['mineru', 'paddleocr_vl', 'textin', 'deepseek']

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

/**
 * 分段策略：粒度 / 成本 / 稳定性三者的取舍。取值与后端 `PdfSplitSegmentStrategy` 逐字一致。
 *
 * · batch —— 逐批摘要再合并切边界。稳、大卷宗不会撞 LLM 超时；看得不全，可能把两份并成一份
 * · wholebook —— 整本一次看完再切。边界更准；大卷宗可能超时（后端会自动退回 batch）
 * · wholebook_cross —— 两种都跑，边界不一致的段标「两种切法不一致」交人工。**分段 LLM 调用翻倍**
 */
export type SegmentStrategy = 'batch' | 'wholebook' | 'wholebook_cross'

export const SEGMENT_STRATEGIES: readonly SegmentStrategy[] = ['batch', 'wholebook', 'wholebook_cross']

/** 脏值一律回落 `batch`：它是唯一不会放大成本的取值，也是后端默认。 */
export function normalizeSegmentStrategy(raw: unknown): SegmentStrategy {
  return SEGMENT_STRATEGIES.includes(raw as SegmentStrategy) ? (raw as SegmentStrategy) : 'batch'
}

/** 材料包级的识别成本选择（`DraftState.recognition`） */
export interface RecognitionPrefs {
  /** fast_text = 电子页只抽文本层（不计费、无坐标）；layout = 电子页也上云（更准、更慢、按页计费） */
  layoutMode?: 'fast_text' | 'layout'
  /** 勾选的云端引擎：空 = 自动容灾；1 个 = 锁定；≥2 个**可比对的** = 交叉比对
   *  （多付一次云端费用）。`deepseek` 不参与比对，见 `DUAL_CAPABLE`。 */
  engines?: CloudSelection
  /** 分段策略（见 `SegmentStrategy`）。缺省 = batch */
  segmentStrategy?: SegmentStrategy
  /** 分歧自动裁定：两个引擎读得不一样时，用打分器判「哪一侧与图上的字相符」。
   *  默认 **true**；但**只在 ≥2 个可比对引擎时才有分歧可判**，单引擎下开着也是空转。 */
  judge?: boolean
}
