import type { PackStatus } from './types'

/**
 * 预处理域的一级「阶段」页签（唯一的流水线主干）。
 *
 * 为什么把收件箱和材料包放进同一套页签：它们是同一条单向漏斗的前后两段——
 * 消息流入 → 拆包 → 归案，而不是三个并列的平级入口。以前 navbar 上并排
 * 「收件箱 / 材料预处理」两个按钮，用户看不出先后关系，页面里还各有一套
 * 自己的筛选页签，两套页签并排时会互相竞争注意力。
 *
 * 现在层级是：一级页签 = 流水线阶段，二级筛选 = 当前阶段内的切分维度
 * （收件箱视图里的来源档位、材料包视图里的三态）。
 *
 * 页签顺序即漏斗顺序，不要按字母或按历史（加入时间）排序。
 */
export type PrepStage = 'inbox' | PackStatus

export const PREP_STAGES: { key: PrepStage; label: string }[] = [
  { key: 'inbox', label: '收件箱' },
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已归案' },
  { key: 'filed', label: '不接归档' },
]

/** 材料包三态（收件箱不是材料包状态，故用于 PackGrid / counts 的窄化） */
export const PACK_STAGES = PREP_STAGES.filter((s): s is { key: PackStatus; label: string } => s.key !== 'inbox')

/** 判断一个阶段是否属于材料包三态（决定主区域渲染网格还是收件箱列表） */
export function isPackStage(stage: PrepStage): stage is PackStatus {
  return stage !== 'inbox'
}

/**
 * 从 URL query 解析阶段。非法值一律落回收件箱——它是漏斗第一段，
 * 也是「我今天有没有新东西要处理」的默认问题。
 */
export function parseStage(raw: string | null): PrepStage {
  if (raw === 'todo' || raw === 'done' || raw === 'filed') return raw
  return 'inbox'
}
