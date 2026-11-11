import type { PackStatus } from './types'

/**
 * 预处理域导航模型。
 *
 * ═══ 为什么是「两级」而不是四个平级页签 ═══
 *
 * 旧模型把四个页签平铺：收件箱 · 待处理 · 已归案 · 不接归档。问题是它们混了
 * **两个正交的维度**：
 *
 *   · 收件箱      —— 回答「东西从哪来」（消息流入）
 *   · 后三个      —— 回答「材料包走到哪一步」（状态）
 *
 * 后果不只是概念不清，而是**同一份材料被数了两次**：收件箱的「全部」是
 * `listInbox({})`，包含 manual_upload / client_upload；而「待处理」拉的是
 * `source_type=manual_upload,client_upload`。同一份上传在两边各出现一次，
 * 两个角标的数字互相矛盾。
 *
 * 所以现在收敛成：一级 = 【收件箱 | 材料包】，材料包之下才按状态切分。
 * 这就是「流入 → 加工」两段，也是这条流水线真实的样子。
 *
 *   [收件箱] [材料包 ▾]
 *              ├ 待处理
 *              ├ 已归案
 *              └ 不接归档
 *
 * 收件箱只收**外来**来源，材料包不再出现在它的列表里（不再是它的一个来源档位），
 * 「材料包」这个来源档位随之取消——它已经升为一级导航。
 */

/** 一级导航：消息流入（收件箱） vs 材料加工（材料包） */
export type PrepSection = 'inbox' | 'pack'

/** 材料包三态（原本的 PackStatus 直接复用） */
export type PackStage = PackStatus

/**
 * 完整的「位置」= 一级区段 + （材料包区段内的）状态。
 *
 * 用联合类型而不是两个独立 state：URL 里只暴露一个 `?stage=`，避免
 * 「section=pack&stage=done」这种两个参数可能互相矛盾的表示。
 */
export type PrepStage = 'inbox' | PackStage

/** 一级导航项（材料包区段的标签会带上当前状态的词） */
export const PREP_SECTIONS: { key: PrepSection; label: string }[] = [
  { key: 'inbox', label: '收件箱' },
  { key: 'pack', label: '材料包' },
]

/** 材料包二级状态（顺序即漏斗顺序，不要按字母或加入时间排序） */
export const PACK_STAGES: { key: PackStage; label: string }[] = [
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已归案' },
  { key: 'filed', label: '不接归档' },
]

/** 判断当前是否处于材料包区段 */
export function isPackStage(stage: PrepStage): stage is PackStage {
  return stage !== 'inbox'
}

/** 阶段 → 所属一级区段 */
export function sectionOf(stage: PrepStage): PrepSection {
  return isPackStage(stage) ? 'pack' : 'inbox'
}

/** 材料包区段未指定状态时的默认落点：待处理是漏斗中段，最常看 */
export const DEFAULT_PACK_STAGE: PackStage = 'todo'

/**
 * 从 URL query 解析阶段。非法值一律落回收件箱——它是漏斗第一段，
 * 也是「我今天有没有新东西要处理」的默认问题。
 *
 * 兼容旧链接：`?stage=todo|done|filed` 仍然有效（它们本来就是材料包状态），
 * 所以历史书签、`materialPrep('todo')` 这类调用点不需要改。
 */
export function parseStage(raw: string | null): PrepStage {
  if (raw === 'todo' || raw === 'done' || raw === 'filed') return raw
  return 'inbox'
}

/**
 * 阶段 → URL 的 `?stage=` 值；收件箱是默认阶段，返回 null 表示不写参数
 * （保持 `/material-prep` 干净）。
 */
export function stageToQuery(stage: PrepStage): string | null {
  return stage === 'inbox' ? null : stage
}
