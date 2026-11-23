import type { CloudBackend } from '../../api/pdf-split'
import {
  CLOUD_ENGINES,
  normalizeCloudSelection,
  toggleCloudEngine,
  type CloudEngine,
  type CloudSelection,
} from '../../types'

// 类型与两个纯函数都在域根 types.ts：store / reader-state 在根层，根层不能反向
// 指向本目录（E6）。这里 re-export 保持既有消费方（AutoSplitSettings / 单测）的
// import 路径不变。
export { CLOUD_ENGINES, normalizeCloudSelection, toggleCloudEngine }
export type { CloudEngine, CloudSelection }

/**
 * 自动分段「解析平台」的多选口径：勾哪些引擎就跑哪些，勾两个就交叉比对。
 *
 * ## 为什么是集合而不是单值
 *
 * 旧版是单选（auto / mineru / textin）：用户只能「锁一个」或者「让系统自己挑」，
 * 而「同时用两个引擎、把两边读得不一样的地方挑出来给我」这件事根本没有入口——
 * 它只能靠后端环境变量开关，等于把选择权交给了运维。现在改成勾选：
 * 一个都不勾 = 容灾（沿用原 auto 语义），勾一个 = 锁定，勾两个 = 交叉比对。
 *
 * ## 为什么不用 `auto` 这种选项值
 *
 * `auto` 是「没选」的**后果**而不是一个可选引擎。把它做成菜单项会和勾选状态
 * 互相打架（勾了 auto 又勾 mineru 该算什么？）。所以空集合就是 auto，
 * 菜单里用一句说明把这个后果讲清楚。
 */

/** 引擎码 → 菜单里的名字。与 `draft/engine.ts` 的 `engineLabel` 同义，只是那边喂给分歧清单 */
export function cloudEngineLabel(engine: CloudEngine): string {
  switch (engine) {
    case 'mineru':
      return 'MinerU'
    case 'paddleocr_vl':
      return 'PaddleOCR-VL'
    case 'textin':
      return 'Textin'
  }
}

/** 勾了两个及以上才比对：一个引擎自己跟自己没有「分歧」可言 */
export function crossChecks(selection: CloudSelection): boolean {
  return selection.length >= 2
}

/**
 * 一次自动分段的平台请求参数。
 *
 * - `cloudBackend`：**正主**（单值）。后端 `resolve_cloud_backends` 只认单值，
 *   把逗号串塞进去会被当成未知值静默降级成 auto，用户勾的锁定就白勾了。
 * - `dualEngines`：≥2 个引擎时才有，逗号分隔的**全部**所选引擎（含正主），
 *   作为独立表单字段 `dual_engines` 发出——后端据此另起一路比对，
 *   `cloud_backend` 的单值语义因此保持不变。
 */
export interface BackendRequest {
  /** 正主平台，直接作为 `cloud_backend` 发出。
   *
   * 类型故意**不含** `paddleocr_vl`：后端 `DocumentParseProvider.ProviderType` 只有
   * `mineru` / `textin`，把 `paddleocr_vl` 发进 `cloud_backend` 会被
   * `resolve_cloud_backends()` 当成未知值静默降级成 auto。让它参与比对的是
   * `dualEngines`，不是这里。 */
  cloudBackend: CloudBackend
  dualEngines: CloudEngine[] | null
}

/**
 * 选中集合 → 请求参数。
 *
 * 正主规则（按优先级）：MinerU → Textin → 列表第一个。理由：MinerU 是所有部署
 * 都配了的平台（`resolve_cloud_backends` 的 auto 首选就是它）；Textin 同样是可注册的
 * `DocumentParseProvider`。只有 PaddleOCR-VL 走的是独立 Paddle Key 路径，未必配得通，
 * 让它当正主会把「取字」这条主路径一起拖下水——所以只要选了任何一个可注册平台，
 * 就不让它当正主。正主只决定**谁产出正文**，不决定谁被比对（比对名单是全集）。
 */
// 类型用 `CloudBackend`（不含 'auto'）而不是 `CloudEngine`：这张表就是「哪些值
// 可以当 cloud_backend」，写成 CloudEngine 会允许 paddleocr_vl 混进来。
const PRIMARY_PREFERENCE: readonly Exclude<CloudBackend, 'auto'>[] = ['mineru', 'textin']

export function resolveBackendRequest(selection: CloudSelection): BackendRequest {
  // 先归一：勾选顺序不该影响发出的串（否则同样的两个引擎会发两种 dual_engines）
  const picked = normalizeCloudSelection(selection)
  if (picked.length === 0) return { cloudBackend: 'auto', dualEngines: null }

  // 只有可注册平台能当正主（`cloud_backend` 的后端枚举里只有 mineru/textin）。
  // `paddleocr_vl` 不在 `DocumentParseProvider.ProviderType` 里，把它发进
  // `cloud_backend` 会让后端 `resolve_cloud_backends()` 收到永远认不了的值。
  // 用户只勾了 paddleocr_vl（+ 可能的其它非注册引擎）时，正主只能退回 auto——
  // 那条路径会挑一个**已配置**的平台取字，而 paddleocr_vl 仍在 dual_engines 里参与比对。
  const preferred = PRIMARY_PREFERENCE.find((e) => picked.some((p) => p === e))
  return {
    cloudBackend: preferred ?? 'auto',
    dualEngines: crossChecks(picked) ? [...picked] : null,
  }
}

/** 序列化 `dual_engines` 表单值（逗号分隔）。只在 ≥2 个引擎时有值 */
export function serializeDualEngines(selection: CloudSelection): string | null {
  const req = resolveBackendRequest(selection)
  return req.dualEngines ? req.dualEngines.join(',') : null
}

/**
 * 设置菜单里的「当前选择」一句话，供主按钮悬浮说明与菜单底部提示共用。
 *
 * 双引擎时用「双引擎 · MinerU+VL」这种短名：悬浮说明是单行的，
 * 全名 `PaddleOCR-VL` 会把版面策略挤掉。
 *
 * 先用 `normalizeCloudSelection` 收窄：这个函数直接用在下一次 render 里，
 * 此时选择集可能还是旧会话的形状（`'auto'` / null），在这里统一守一道。
 * 三个以上引擎时不再说「双引擎」——那就是说错话了。
 */
export function cloudSelectionSummary(selection: CloudSelection): string {
  const picked = normalizeCloudSelection(selection)
  const [first] = picked
  if (first === undefined) return '自动容灾'
  if (!crossChecks(picked)) return `仅 ${cloudEngineLabel(first)}`
  const names = picked.map(cloudShortLabel).join('+')
  return picked.length === 2 ? `双引擎 · ${names}` : `${picked.length} 个引擎 · ${names}`
}

/** 页面框轴 / 标题里用的短名（`PaddleOCR-VL` → `VL`） */
export function cloudShortLabel(engine: CloudEngine): string {
  return engine === 'paddleocr_vl' ? 'VL' : cloudEngineLabel(engine)
}
