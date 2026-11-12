/**
 * 非诉线 · 演示数据 · A. 专项服务（关厂清盘）· 阶段与模板
 * （**仅用于录屏演示**，不参与真实业务）
 *
 * 这里是「计划」：7 个阶段（含 2 个子阶段）、阶段设计模板、从 0 起草的 AI 建议。
 * 同一批阶段的过程证据（变更记录 / 交付物版本 / 风险 / 客户确认 / 推进校验 / 甘特）
 * 在 `nl1-special-evidence.ts`；两份数据靠 `DEMO_NONLIT_PHASES[].id` 与
 * `.deliverables[].name` 对齐，改阶段或交付物名时两侧都要看。
 *
 * 约定：只出现在展示位置、不参与判断逻辑；人名机构一律脱敏；数值口径真实。
 */

import type { DemoDeliverable } from './types'


/** 一个阶段 */
export interface DemoPhase {
  id: string
  seq: string
  /** 阶段名 */
  name: string
  /** 计划起止 */
  planStart: string
  planEnd: string
  /** 实际状态 */
  status: 'done' | 'doing' | 'todo'
  /** 验收标准 */
  criterion: string
  deliverables: DemoDeliverable[]
}

export const DEMO_NONLIT_PHASES: DemoPhase[] = [
  {
    id: 'p1',
    seq: '1',
    name: '尽职调查',
    planStart: '2026-10-26',
    planEnd: '2026-11-08',
    status: 'done',
    criterion: '完成工商、税务、社保、债务四项底稿',
    deliverables: [
      { name: '工商登记与股权结构核实', pages: 12, status: 'done', updatedAt: '11-05 14:20', owner: '房某某' },
      { name: '职工名册与社保清缴明细', pages: 28, status: 'done', updatedAt: '11-07 09:40', owner: '黄某某' },
    ],
  },
  {
    id: 'p2',
    seq: '2',
    name: '方案设计',
    planStart: '2026-11-09',
    planEnd: '2026-11-20',
    status: 'done',
    criterion: '出具关厂方案并取得客户书面确认',
    deliverables: [
      { name: '关厂清盘总体方案 v2.0', pages: 18, status: 'done', updatedAt: '11-18 16:05', owner: '房某某' },
    ],
  },
  {
    id: 'p3',
    seq: '3',
    name: '文件起草',
    planStart: '2026-11-21',
    planEnd: '2027-01-15',
    status: 'doing',
    criterion: '职工安置、债权债务、注销三类文书定稿',
    deliverables: [
      { name: '职工安置方案与补偿测算表', pages: 34, status: 'drafting', updatedAt: '11-28 11:30', owner: '黄某某' },
    ],
  },
  {
    id: 'p3-1',
    seq: '3.1',
    name: '职工安置文书',
    planStart: '2026-11-21',
    planEnd: '2026-12-20',
    status: 'doing',
    criterion: '每位职工签署安置协议，无劳动争议',
    deliverables: [],
  },
  {
    id: 'p3-2',
    seq: '3.2',
    name: '债权债务与决议',
    planStart: '2026-11-25',
    planEnd: '2027-01-10',
    status: 'done',
    criterion: '债权人会议决议通过清偿方案',
    deliverables: [
      { name: '债权人会议决议（签字版）', pages: 6, status: 'done', updatedAt: '12-28 15:20', owner: '房某某' },
    ],
  },
  {
    id: 'p4',
    seq: '4',
    name: '登记与注销',
    planStart: '2027-01-16',
    planEnd: '2027-03-31',
    status: 'todo',
    criterion: '取得市监局注销登记通知书',
    deliverables: [],
  },
  {
    id: 'p5',
    seq: '5',
    name: '交割与移交',
    planStart: '2027-04-01',
    planEnd: '2027-04-30',
    status: 'todo',
    criterion: '完成资产交割与档案移交',
    deliverables: [],
  },
]

/** 阶段设计模板（点「设计阶段」时可选） */
export interface DemoPhaseTemplate {
  name: string
  phases: number
  desc: string
  used: number
}

export const DEMO_PHASE_TEMPLATES: DemoPhaseTemplate[] = [
  { name: '关厂清盘（标准）', phases: 7, desc: '尽调 → 方案 → 文书 → 注销 → 交割', used: 12 },
  { name: '股权收购', phases: 5, desc: '尽调 → 估值 → 谈判 → 签约 → 交割', used: 8 },
  { name: '合规体系搭建', phases: 4, desc: '体检 → 制度 → 培训 → 验收', used: 5 },
  { name: '知识产权布局', phases: 4, desc: '检索 → 布局 → 申请 → 维护', used: 3 },
]

/** 从 0 起草：AI 根据项目信息生成阶段划分 */
export interface DemoDraftSuggestion {
  name: string
  reason: string
}

export const DEMO_DRAFT_SUGGESTIONS: DemoDraftSuggestion[] = [
  { name: '补充「税务清算」阶段', reason: '关厂项目通常需单独走税务注销，建议插在登记与注销之前' },
  { name: '「职工安置」拆为两个子阶段', reason: '协商解除与经济补偿分属不同审批链，建议分开验收' },
  { name: '阶段 4 增加交付物「清税证明」', reason: '市监局注销前置材料，缺此项会被退回' },
]
