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

/* ================= 程序线分叉与形态判定（多案件适配） =================
 *
 * 一条横向进度条能表达「一条程序线走到哪」（一审 → 二审 → 执行），表达不了
 * 「一个委托底下有几条互不相干的线」。261 号（两个被告各走一审+执行）与 14 个不同案由的系列案都属于后者：`×N` 把它们压成一个数字，读起来像
 * 「还差 N-1 个」。所以顶部先判形态，再决定画什么（方案见
 * docs/02-产品与方案/合同程序链多案件适配方案.md）：
 *   single → 不画（单案的阶段/状态/法院在案件卡上已经有了，画一遍是纯重复）
 *   chain  → ChainStepper，且砍掉永远空着的节点（trimPlan）
 *   multi  → CaseOverview 案件总览，一条程序线一条程序线地列
 */

/** 顶部该画什么：none=没案件；single=一个案件；chain=多案同一条线；multi=多条线 */
export type ChainShape = 'none' | 'single' | 'chain' | 'multi'

/**
 * 按 `prev`（后端 `Case.previous_case_id`）把案件分成若干条程序线。
 *
 * 取**无向连通分量**而不是沿 prev 走单链：`previous_case` 在库里大面积为空（261 的四个
 * 案件一个 prev 都没写），"链"只在真的手工串过时才存在。分量同时容得下两种现实——
 * 串过的按 `二审 → 执行` 归一组，没串过的各自成组（如实说「这几条的关系未知」，
 * 而不是替律师猜一条链）。prev 指向本委托以外或指向自己时按无线处理，案件不会被吞掉。
 */
export function caseBranches(cases: DealCase[]): DealCase[][] {
  const byId = new Map(cases.map((c) => [c.id, c]))
  const adj = new Map<number, number[]>()
  const link = (a: number, b: number) => adj.set(a, [...(adj.get(a) ?? []), b])
  for (const c of cases) {
    if (c.prev == null || c.prev === c.id || !byId.has(c.prev)) continue
    link(c.id, c.prev)
    link(c.prev, c.id)
  }
  const seen = new Set<number>()
  const out: DealCase[][] = []
  // 起点用收案日期序：不管接口返回顺序怎么变，线的先后都稳定
  for (const start of orderChain(cases)) {
    if (seen.has(start.id)) continue
    const group: DealCase[] = []
    seen.add(start.id)
    const stack = [start.id]
    while (stack.length > 0) {
      const c = byId.get(stack.pop() as number)
      if (!c) continue
      group.push(c)
      for (const nb of adj.get(c.id) ?? []) {
        if (seen.has(nb)) continue
        seen.add(nb)
        stack.push(nb)
      }
    }
    // 线内按程序序：小链点读起来必须是「一审 → 二审 → 执行」，同日再按 id
    out.push(group.sort((a, b) => stageRank(a.proc) - stageRank(b.proc) || a.id - b.id))
  }
  return out
}

export function chainShape(branches: DealCase[][]): ChainShape {
  const n = branches.reduce((sum, b) => sum + b.length, 0)
  if (n === 0) return 'none'
  if (n === 1) return 'single'
  return branches.length === 1 ? 'chain' : 'multi'
}

/**
 * 砍掉「永远空着」的节点。
 *
 * 合同勾选的阶段是**代理范围**，不等于**走得到的程序**：勾了一审/二审/执行，一审调解
 * 结案直接进执行，那个二审就该消失——它每开一次页面都提醒「还有一步没做」，而它永远
 * 不会发生。规则：最后一个已启动阶段**之前**的未启动阶段一律不画（已被跳过），之后只留
 * **紧邻的一个**（真正的下一步，与 NextStageRow 是同一个程序）。一个都还没启动时原样
 * 返回——此时空节点就是合同约定的代理范围，是有用信息，不是噪音。
 */
export function trimPlan(plan: StagePlan[]): StagePlan[] {
  let lastStarted = -1
  plan.forEach((p, i) => {
    if (p.state !== 'todo') lastStarted = i
  })
  if (lastStarted === -1) return plan
  const shown = plan.slice(0, lastStarted + 1).filter((p) => p.state !== 'todo')
  const nextTodo = plan.slice(lastStarted + 1).find((p) => p.state === 'todo')
  return nextTodo ? [...shown, nextTodo] : shown
}
