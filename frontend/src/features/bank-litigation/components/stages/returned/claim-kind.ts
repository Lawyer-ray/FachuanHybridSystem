/**
 * 归案日志的筛选口径 —— 把邮件行上的「处理结果」文案翻成三分法。
 *
 * 为什么不用后端字段：这一屏的邮件行是演示数据，动作文案本身就是结果；
 * 筛选条（全部 / 自动归案 / 待人工 / 已标记无关）只认这三种口径，
 * 所以收敛成一个纯函数，面板与抽屉共用以保证两边判定一致。
 */

/** 归案日志里一封邮件的筛选口径 */
export type ClaimKind = 'auto' | 'manual' | 'ignored'

export function claimKindOf(action: string): ClaimKind {
  if (action.startsWith('已标记无关')) return 'ignored'
  if (action.startsWith('已自动') || action.startsWith('已归案')) return 'auto'
  return 'manual'
}
