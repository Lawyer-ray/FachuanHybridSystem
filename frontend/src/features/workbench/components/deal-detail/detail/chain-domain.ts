import type { DealCase } from '../../../types'

/**
 * 程序阶段的程序顺序。后端 CaseStage 枚举的 choices 顺序（一审/二审/执行/劳动仲裁…）不是
 * 程序顺序，合同 representation_stages 也按 choices 序存（322 号存成「一审、二审、劳动仲裁」），
 * 所以排序只能靠这张表：前置程序 → 审判 → 再审/重审分支 → 申诉抗诉 → 执行。未知标签排最后。
 */
export const STAGE_ORDER: readonly string[] = [
  '侦查',
  '审查起诉',
  '劳动仲裁',
  '行政复议',
  '自诉',
  '一审',
  '二审',
  '重审一审',
  '重审二审',
  '申请再审',
  '再审一审',
  '再审二审',
  '提审',
  '死刑复核程序',
  '申诉',
  '申请抗诉',
  '申诉抗诉',
  '执行',
]

function stageRank(stage: string): number {
  const i = STAGE_ORDER.indexOf(stage)
  return i === -1 ? STAGE_ORDER.length : i
}

/** 同阶段内的案件顺序：收案日期升序、同日按 id */
export function orderChain(cases: DealCase[]): DealCase[] {
  return [...cases].sort((a, b) => (a.from || '').localeCompare(b.from || '') || a.id - b.id)
}

export type StepState = 'done' | 'cur' | 'todo'

/**
 * 一个程序阶段节点。cases 可为空（合同勾选了但还没立案 = 未启动）或多个
 * （两个一审分案、按被执行人分立的多个执行 = 分叉）。再往后要长出嵌套（保全挂在一审下、
 * 执行按被执行人再分）时在这里加 children，stepper / 主列都从这棵结构长出来。
 */
export interface StagePlan {
  stage: string
  state: StepState
  cases: DealCase[]
  /** 合同是否勾选了该阶段（未勾选但有案件 = 数据漂移，照样展示） */
  selected: boolean
}

/**
 * 程序计划 = 合同勾选的代理阶段 ∪ 案件实际所在阶段，按程序序排。
 * 合同一个阶段都没勾（库里 45 个争议合同如此）时退化为只看案件。
 */
export function buildStagePlan(selectedStages: string[], cases: DealCase[]): StagePlan[] {
  const byStage = new Map<string, DealCase[]>()
  for (const c of orderChain(cases)) {
    const list = byStage.get(c.proc)
    if (list) list.push(c)
    else byStage.set(c.proc, [c])
  }
  const stages = [...new Set([...selectedStages, ...byStage.keys()])].sort(
    (a, b) => stageRank(a) - stageRank(b) || a.localeCompare(b),
  )
  return stages.map((stage) => {
    const cs = byStage.get(stage) ?? []
    const state: StepState = cs.length === 0 ? 'todo' : cs.every((c) => c.done) ? 'done' : 'cur'
    return { stage, state, cases: cs, selected: selectedStages.includes(stage) }
  })
}

/** 主列案件顺序 = 计划顺序（stepper 就是目录），同阶段内按收案日期 */
export function planCases(plan: StagePlan[]): DealCase[] {
  return plan.flatMap((p) => p.cases)
}

export interface ChainStep {
  key: string
  /** 该阶段首个案件 id；null = 未启动（不可跳转） */
  caseId: number | null
  stage: string
  sub: string
  state: StepState
  /** 该阶段案件数（>1 即分叉，stepper 标 ×N） */
  n: number
}

export function chainSteps(plan: StagePlan[]): ChainStep[] {
  return plan.map((p) => {
    const first = p.cases[0]
    const label = p.state === 'todo' ? '未启动' : p.state === 'done' ? '已结' : '在办'
    return {
      key: p.stage,
      caseId: first?.id ?? null,
      stage: p.stage,
      sub: p.cases.length === 1 && first?.auth ? label + ' · ' + first.auth : label,
      state: p.state,
      n: p.cases.length,
    }
  })
}

/**
 * 「下一步」= 最后一个已启动阶段之后的第一个未启动阶段（全未启动则取第一个）。
 * 夹在中间的未启动阶段（如一审→执行、跳过了勾选的二审）不算下一步，只在 stepper 里如实留空心点。
 */
export function nextStage(plan: StagePlan[]): string | null {
  let lastStarted = -1
  plan.forEach((p, i) => {
    if (p.state !== 'todo') lastStarted = i
  })
  return plan.slice(lastStarted + 1).find((p) => p.state === 'todo')?.stage ?? null
}

/** stepper 右侧摘要：「2 个案件 · 劳动仲裁 → 一审」（只列已有案件的阶段） */
export function chainSummary(plan: StagePlan[]): string {
  const started = plan.filter((p) => p.cases.length > 0)
  if (started.length === 0) return ''
  const n = started.reduce((s, p) => s + p.cases.length, 0)
  return n + ' 个案件 · ' + started.map((p) => p.stage).join(' → ')
}

/** 同阶段多案（分叉）时节标题要带案名才分得清 */
export function ambiguousStages(plan: StagePlan[]): Set<string> {
  return new Set(plan.filter((p) => p.cases.length > 1).map((p) => p.stage))
}
