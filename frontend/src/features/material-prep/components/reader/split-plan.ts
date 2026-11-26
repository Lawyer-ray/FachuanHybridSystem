import type { CloudSelection, SegmentStrategy } from '../../types'
import { dualEnginesOf } from './platform-selection'

/**
 * 自动分段的**成本档位**：给「简易」模式用的三档预设。
 *
 * ## 为什么是两笔账，不是一个"几倍"
 *
 * 自动分段的钱来自两个**互不相干**的地方：
 * 1. **取字**——把整包 PDF 送云端解析几遍。双引擎 = 每个引擎各解析一遍 = 2 次计费。
 * 2. **分段**——把逐页正文交给 LLM 切边界。`wholebook_cross` 要把整本和逐批各跑一遍 = 2 次调用。
 *
 * 合成一个"费用 ×3"的数字会误导：最贵那档其实是「取字 2 次 + 分段 2 次」，
 * 既不是 ×2 也不是 ×4。所以档位卡上分开写这两笔，用户才知道钱花在哪。
 *
 * ## 三档的措辞
 *
 * 「经济 / 标准 / 性能」沿用云主机那套直觉（低配 / 中配 / 高配）。要注意**性能档最慢**：
 * 它的"高配"体现在结果质量上（两种切法互相对照），不体现在速度上 —— 所以每档的
 * 说明必须把「买到什么 / 牺牲什么」写在同一行里，不能只留一个档名。
 *
 * ## 为什么档位只是预设，不是发给后端的枚举
 *
 * 后端只认具体参数（引擎 / 分段策略 / 判定开关）。档位是**前端帮用户填表**的快捷方式，
 * 一旦写进接口就会多出一份要维护的语义，且"自定义"这个状态无法表达。
 * 所以 `tierOf()` 反解：三项都对得上才算命中某档，否则就是「已自定义」。
 */

export type SplitTierId = 'cheap' | 'standard' | 'max'

export interface SplitTier {
  id: SplitTierId
  label: string
  /** 取字：整包云端解析几遍（双引擎 = 2） */
  parseRuns: 1 | 2
  /** 分段：分段 LLM 调用几遍（`wholebook_cross` = 2） */
  segmentRuns: 1 | 2
  /** 买到什么 / 牺牲什么 */
  hint: string
}

/** 档位顺序即成本从低到高——UI 直接按这个顺序渲染，不再单独排序。 */
export const SPLIT_TIERS: readonly SplitTier[] = [
  {
    id: 'cheap',
    label: '经济',
    parseRuns: 1,
    segmentRuns: 1,
    hint: '单引擎取字 · 分批分段。耗时最短、云端只解析一遍；没有交叉校验，读错不会被发现',
  },
  {
    id: 'standard',
    label: '标准',
    parseRuns: 2,
    segmentRuns: 1,
    hint: '双引擎取字 · 分批分段。两个引擎各读一遍，读得不一样的地方自动判，判不了才进人工',
  },
  {
    id: 'max',
    label: '性能',
    parseRuns: 2,
    segmentRuns: 2,
    hint: '双引擎取字 · 整本与分批同时分段。边界更准，两种切法不一致的段交人工；三档里最慢',
  },
]

/** 一档预设展开成的具体参数（与后端的字段同名同值，便于一眼核对）。 */
export interface SplitPlanPrefs {
  engines: CloudSelection
  segmentStrategy: SegmentStrategy
  judge: boolean
}

/** 档位 → 具体参数。`standard` / `max` 用双引擎，因为**判定只在双引擎分歧上才有事可做**。 */
export function applyTier(id: SplitTierId): SplitPlanPrefs {
  switch (id) {
    case 'cheap':
      return { engines: ['mineru'], segmentStrategy: 'batch', judge: false }
    case 'max':
      return { engines: ['mineru', 'paddleocr_vl'], segmentStrategy: 'wholebook_cross', judge: true }
    case 'standard':
      return { engines: ['mineru', 'paddleocr_vl'], segmentStrategy: 'batch', judge: true }
  }
}

/**
 * 当前参数命中了哪一档？没命中返回 `null`（=「已自定义」）。
 *
 * 判据只看**影响成本与结果**的三项；`layoutMode` 不参与——它是"电子页要不要上云"，
 * 与档位不是同一维度的取舍（同一个档位下两种版面策略都可能）。
 */
export function tierOf(prefs: SplitPlanPrefs): SplitTierId | null {
  const dual = dualEnginesOf(prefs.engines).length >= 2
  if (!dual && !prefs.judge && prefs.segmentStrategy === 'batch') return 'cheap'
  if (dual && prefs.judge && prefs.segmentStrategy === 'batch') return 'standard'
  if (dual && prefs.judge && prefs.segmentStrategy === 'wholebook_cross') return 'max'
  return null
}

/** 两个成本维度的简短文案，档位卡与高级区共用同一口径。 */
export function costBadges(tier: SplitTier): string {
  return `取字 ${tier.parseRuns} 遍 · 分段 ${tier.segmentRuns} 遍`
}
