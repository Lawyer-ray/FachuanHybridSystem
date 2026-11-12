/**
 * 演示数据 · F. 起诉条件（组件：components/ReadinessPanel.tsx）
 *
 * 演示态补充：槽位来源与更新时间 / 校验依据 / 历史校验 / 同类案件对比 /
 * 材料清单明细。真实判定仍以接口返回为准，这里只做画面填充。
 * 真实功能上线时整个文件删除即可。
 */

export interface ReadinessSlotMeta {
  fileCount: number
  lastAt: string
  /** 来源：整包分段 / OA 盖章 / 人工上传 / 要素式转换 */
  source: string
}

export const DEMO_READINESS_SLOT_META: Record<string, ReadinessSlotMeta> = {
  contract: { fileCount: 1, lastAt: '11-03 09:14', source: '整包分段 · 自动归案' },
  iou: { fileCount: 2, lastAt: '11-03 09:14', source: '整包分段 · 自动归案' },
  stmt: { fileCount: 3, lastAt: '11-03 09:15', source: '整包分段 · 自动归案' },
  coll: { fileCount: 4, lastAt: '11-01 16:41', source: '整包分段 · 自动归案' },
  id: { fileCount: 2, lastAt: '10-26 14:31', source: '人工上传' },
  guarantee: { fileCount: 0, lastAt: '—', source: '不适用' },
}

export const DEMO_READINESS_CHECK_BASIS: Record<string, { basis: string; source: string }> = {
  parties: { basis: '原告与被告均已登记，一方缺失即不通过', source: 'Case.parties[]' },
  jurisdiction: { basis: '必须登记至少一个主管机关（管辖法院）', source: 'Case.supervising_authorities[]' },
  limitation: { basis: '自收案日起推算，超过 3 年提示超期风险', source: 'Case.start_date' },
  materials: { basis: '按案由的关键材料槽位逐项比对，缺件即不通过', source: 'CaseMaterial' },
  amount: { basis: '标的额必须大于 0，否则无法计算受理费', source: 'Case.target_amount' },
}

export interface ReadinessHistoryRow {
  at: string
  result: 'pass' | 'fail'
  passed: number
  total: number
  missing: number
  by: string
  note: string
}

export const DEMO_READINESS_HISTORY: ReadinessHistoryRow[] = [
  { at: '11-03 10:06', result: 'pass', passed: 5, total: 5, missing: 0, by: '黄某某', note: '归案后自动复校' },
  { at: '11-03 09:16', result: 'fail', passed: 4, total: 5, missing: 1, by: '系统定时', note: '催收记录未归案' },
  { at: '11-02 17:52', result: 'fail', passed: 3, total: 5, missing: 2, by: '黄某某', note: '缺还款明细、催收记录' },
  { at: '11-01 16:44', result: 'fail', passed: 3, total: 5, missing: 2, by: '房某某', note: '补寄材料尚未复核' },
  { at: '10-31 15:10', result: 'fail', passed: 2, total: 5, missing: 3, by: '系统定时', note: '首次建档，材料为空' },
  { at: '10-29 11:30', result: 'fail', passed: 2, total: 5, missing: 3, by: '黄某某', note: '管辖法院未登记' },
  { at: '10-27 14:02', result: 'fail', passed: 1, total: 5, missing: 4, by: '系统定时', note: '仅登记当事人' },
]

export interface ReadinessPeerRow {
  caseName: string
  stage: string
  passed: number
  total: number
  missing: number
  latestAt: string
}

export const DEMO_READINESS_PEERS: ReadinessPeerRow[] = [
  { caseName: '某某银行广州分行诉谭某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-03 10:06' },
  { caseName: '某某银行广州分行诉吴某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-02 15:31' },
  { caseName: '某某银行广州分行诉李某某金融借款合同纠纷', stage: '一审', passed: 4, total: 5, missing: 1, latestAt: '11-02 11:20' },
  { caseName: '某某银行广州分行诉陈某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-01 09:48' },
  { caseName: '某某银行广州分行诉黄某某金融借款合同纠纷', stage: '一审', passed: 3, total: 5, missing: 2, latestAt: '10-30 16:12' },
  { caseName: '某某银行广州分行诉某某贸易公司金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '10-28 10:05' },
  { caseName: '某某银行广州分行诉刘某某金融借款合同纠纷', stage: '二审', passed: 3, total: 3, missing: 0, latestAt: '10-24 14:37' },
]

export interface ReadinessFileRow {
  name: string
  slot: string
  pages: number
  size: string
  at: string
  source: string
}

export const DEMO_READINESS_FILES: ReadinessFileRow[] = [
  { name: '借款合同.pdf', slot: '借款/主合同', pages: 7, size: '1.8 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '借款借据.pdf', slot: '借据或放款凭证', pages: 1, size: '0.3 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '放款凭证.pdf', slot: '借据或放款凭证', pages: 5, size: '1.1 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '还款明细.pdf', slot: '还款明细或对账单', pages: 6, size: '1.4 MB', at: '11-03 09:15', source: '整包分段' },
  { name: '对账单_2026Q3.pdf', slot: '还款明细或对账单', pages: 3, size: '0.7 MB', at: '11-03 09:15', source: '整包分段' },
  { name: '还款流水_全量.pdf', slot: '还款明细或对账单', pages: 12, size: '2.6 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '催收记录.pdf', slot: '催收记录', pages: 3, size: '0.9 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '催收函及签收单.pdf', slot: '催收记录', pages: 8, size: '2.1 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '当事人身份证明.pdf', slot: '当事人身份证明', pages: 1, size: '0.2 MB', at: '10-26 14:31', source: '人工上传' },
  { name: '被告身份信息核查.pdf', slot: '当事人身份证明', pages: 1, size: '0.2 MB', at: '10-26 14:31', source: '人工上传' },
]
