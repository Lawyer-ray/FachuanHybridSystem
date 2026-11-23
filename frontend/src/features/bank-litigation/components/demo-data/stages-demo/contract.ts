/**
 * 演示数据 · G4. ④ 文书
 *
 * 委托材料生成、利益冲突核查、合同条款与模板。
 */

// ───────────────────────── ④ 文书 · 生成的委托材料与利冲核查 ─────────────────────────

export interface ContractGenRow {
  name: string
  source: string
  pages: number
  status: 'generated' | 'pending'
}

export const DEMO_CONTRACT_GEN: ContractGenRow[] = [
  { name: '民事委托代理合同', source: '合同模板 + 案件数据自动填充', pages: 6, status: 'generated' },
  { name: '授权委托书', source: '按当事人自动生成', pages: 1, status: 'generated' },
  { name: '风险告知书', source: '标准模板', pages: 2, status: 'generated' },
  { name: '收费协议', source: '按委托合同约定的费率生成', pages: 2, status: 'generated' },
  { name: '送达地址确认书', source: '按管辖法院模板生成', pages: 1, status: 'pending' },
]

export interface ConflictHitRow {
  subject: string
  role: string
  hit: boolean
  detail: string
  level: 'red' | 'yellow' | 'clear'
}

export const DEMO_CONFLICT_HITS: ConflictHitRow[] = [
  { subject: '某某银行某某支行', role: '委托人', hit: false, detail: '本所长期客户，无冲突', level: 'clear' },
  { subject: '谭某某', role: '被告', hit: false, detail: '当事人库无同名记录', level: 'clear' },
  { subject: '谭某某', role: '被告', hit: false, detail: '历史委托 0 条', level: 'clear' },
  { subject: '李某某', role: '共同借款人', hit: true, detail: '与本所在办「李某某离婚案」同名且证件号一致', level: 'red' },
  { subject: '某某置业公司', role: '抵押人', hit: false, detail: '关联企业 2 家，无在办案件', level: 'clear' },
  { subject: '某某置业公司', role: '抵押人', hit: false, detail: '历史委托已结案 3 年', level: 'yellow' },
]

// ───────────────────────── ④ 文书 · 委托合同条款 ─────────────────────────

export interface ContractTermRow {
  clause: string
  value: string
  source: string
  filled: boolean
}

export const DEMO_CONTRACT_TERMS: ContractTermRow[] = [
  { clause: '委托人', value: '某某银行某某支行', source: '案件当事人 · 原告', filled: true },
  { clause: '受托人', value: '某某律师事务所', source: '当前律所', filled: true },
  { clause: '案由', value: '金融借款合同纠纷', source: '案件数据', filled: true },
  { clause: '标的额', value: '¥998,670.21', source: '起诉状诉请合计', filled: true },
  { clause: '收费方式', value: '固定收费 ¥5,000 + 回款 12%', source: '合同模板默认值', filled: true },
  { clause: '代理阶段', value: '一审、二审、执行', source: '委托合同勾选', filled: true },
  { clause: '特别授权', value: '代为和解、代收法律文书', source: '需律师确认', filled: false },
  { clause: '承办律师', value: '黄某某（主办）', source: '案件指派', filled: true },
]

// ───────────────────────── ④ 文书 · 委托合同模板 ─────────────────────────

export interface ContractTemplateRow {
  name: string
  version: string
  fields: number
  cases: number
  updated: string
}

export const DEMO_CONTRACT_TEMPLATES: ContractTemplateRow[] = [
  { name: '民事委托代理合同（标准版）', version: 'v3.2', fields: 24, cases: 168, updated: '2026-09-12' },
  { name: '民事委托代理合同（风险代理）', version: 'v2.8', fields: 26, cases: 42, updated: '2026-08-30' },
  { name: '授权委托书（一审）', version: 'v1.6', fields: 8, cases: 210, updated: '2026-07-18' },
  { name: '风险告知书', version: 'v1.2', fields: 5, cases: 210, updated: '2026-06-05' },
  { name: '收费协议', version: 'v2.1', fields: 12, cases: 156, updated: '2026-09-01' },
]
