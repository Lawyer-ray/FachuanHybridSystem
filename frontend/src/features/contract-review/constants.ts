/**
 * 合同审查域的本域常量。
 *
 * `STEPS` 与 `DEMAND_CHIPS` 原来长在 ReviewLaunchDrawer.tsx 里，抽屉拆成
 * hooks + 子组件后有三个文件要读它们（步骤开关状态、②审查内容、③特别交代），
 * 留在组件文件里会形成「子组件反过来从父组件文件拿常量」的怪依赖。
 */

/**
 * 审查步骤（对应后端 selected_steps）。
 *
 * `defaultOn` 是**初次打开时的默认勾选**，不是"当前开关状态"——当前状态在
 * use-launch-submit 的 steps state 里。早先这个字段叫 `on`，读代码的人会以为
 * 它跟着 UI 变，实际首次 useState 之后模块常量再没被读过，同名双语义。
 */
export const STEPS: ReadonlyArray<{ key: string; label: string; desc: string; defaultOn: boolean }> = [
  { key: 'contract_review', label: '条款审查', desc: '付款 · 验收 · 违约 · 终止 · 争议解决', defaultOn: true },
  { key: 'typo_check', label: '错别字检测', desc: '逐段比对，产出以修订落盘', defaultOn: true },
  { key: 'review_report', label: '评估报告', desc: '整体风险摘要，供回给客户', defaultOn: true },
  { key: 'format_document', label: '格式规范化', desc: '字体 · 行距 · 缩进 · 页码 · 标题编号', defaultOn: false },
]

/** 步骤 key → 默认开关（useState 初始化用；测试断言"默认勾选三项"也取这里） */
export function defaultStepToggles(): Record<string, boolean> {
  const init: Record<string, boolean> = {}
  for (const s of STEPS) init[s.key] = s.defaultOn
  return init
}

/** 常用交代 chips（写进 textarea，律师可继续编辑） */
export const DEMAND_CHIPS = [
  { key: '压工期', text: '这单一定要压工期' },
  { key: '控预算', text: '预算不能再加' },
  { key: '别太硬', text: '别把话说太死' },
]
