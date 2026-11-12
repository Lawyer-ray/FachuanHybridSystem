/**
 * 演示数据 · B2. OA 盖章
 *
 * 印章库 / 盖章历史 / 位置规则 / 失败原因 / 批量预设。
 * 真实功能上线时整个文件删除即可。
 */

export interface StampLogRow {
  fileName: string
  contract: string
  page: string
  ok: boolean
  at: string
}

export const DEMO_STAMP_LOG: StampLogRow[] = [
  { fileName: '民事起诉状（定稿）.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 3 页', ok: true, at: '11-03 09:40' },
  { fileName: '证据清单及明细.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 12 页', ok: true, at: '11-03 09:42' },
  { fileName: '授权委托书（扫描件）.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 1 页', ok: true, at: '11-03 09:44' },
  { fileName: '送达地址确认书.pdf', contract: '某某银行个贷不良批量诉讼', page: '骑缝', ok: false, at: '11-02 17:20' },
]

export interface OASealRow {
  name: string
  kind: '公章' | '合同章' | '财务章' | '法定代表人章'
  holder: string
  status: 'available' | 'in-use' | 'expired'
  usedThisMonth: number
  lastUsed: string
}

export const DEMO_OA_SEALS: OASealRow[] = [
  { name: '某某律所 公章', kind: '公章', holder: '行政部', status: 'available', usedThisMonth: 42, lastUsed: '11-03 09:44' },
  { name: '某某律所 合同专用章', kind: '合同章', holder: '行政部', status: 'available', usedThisMonth: 18, lastUsed: '11-02 16:20' },
  { name: '某某律所 财务专用章', kind: '财务章', holder: '财务部', status: 'in-use', usedThisMonth: 7, lastUsed: '11-03 10:15' },
  { name: '法定代表人 私章', kind: '法定代表人章', holder: '主任办', status: 'available', usedThisMonth: 31, lastUsed: '11-03 09:44' },
  { name: '某某律所 旧版公章', kind: '公章', holder: '行政部', status: 'expired', usedThisMonth: 0, lastUsed: '2025-12-31' },
]

export interface OASealRuleRow {
  docType: string
  seals: string
  position: string
  note: string
}

export const DEMO_OA_SEAL_RULES: OASealRuleRow[] = [
  { docType: '民事起诉状', seals: '公章 + 法定代表人章', position: '具状人处 + 骑缝', note: '骑缝章须覆盖全部附件页' },
  { docType: '证据清单及明细', seals: '公章', position: '清单末尾', note: '与证据材料一并骑缝' },
  { docType: '授权委托书', seals: '委托人签章 + 律所公章', position: '委托人签名处 + 落款', note: '缺委托人签章视为无效' },
  { docType: '送达地址确认书', seals: '公章', position: '确认人处', note: '须与立案信息一致' },
  { docType: '律师事务所函', seals: '公章', position: '落款处', note: '需注明承办律师与执业证号' },
  { docType: '办案小结', seals: '公章', position: '落款处', note: '归档前最后一环' },
]

export interface StampHistoryRow {
  fileName: string
  docType: string
  seals: string
  page: string
  ok: boolean
  reason: string
  at: string
  by: string
}

export const DEMO_STAMP_HISTORY: StampHistoryRow[] = [
  { fileName: '民事起诉状（定稿）.pdf', docType: '民事起诉状', seals: '公章+法代章', page: '第3页 + 骑缝', ok: true, reason: '', at: '11-03 09:44', by: '黄某某' },
  { fileName: '证据清单及明细.pdf', docType: '证据清单', seals: '公章', page: '第12页 + 骑缝', ok: true, reason: '', at: '11-03 09:42', by: '黄某某' },
  { fileName: '授权委托书（扫描件）.pdf', docType: '授权委托书', seals: '公章', page: '第1页', ok: true, reason: '', at: '11-03 09:40', by: '黄某某' },
  { fileName: '送达地址确认书.pdf', docType: '送达地址确认书', seals: '公章', page: '骑缝', ok: false, reason: '骑缝章位置与印章库不符', at: '11-02 17:20', by: '黄某某' },
  { fileName: '律师事务所函.pdf', docType: '律所函', seals: '公章', page: '落款处', ok: true, reason: '', at: '11-02 15:05', by: '房某某' },
  { fileName: '民事起诉状（初稿）.pdf', docType: '民事起诉状', seals: '公章', page: '第2页', ok: false, reason: '文件已被新版替代，拒绝盖章', at: '11-02 11:30', by: '房某某' },
  { fileName: '保全申请书.pdf', docType: '保全申请书', seals: '公章+法代章', page: '第1页 + 骑缝', ok: true, reason: '', at: '11-01 16:48', by: '黄某某' },
  { fileName: '证据目录.pdf', docType: '证据清单', seals: '公章', page: '末尾', ok: true, reason: '', at: '11-01 16:45', by: '黄某某' },
  { fileName: '执行申请书.pdf', docType: '执行申请书', seals: '公章', page: '落款处', ok: true, reason: '', at: '10-31 14:10', by: '房某某' },
  { fileName: '办案小结.docx', docType: '办案小结', seals: '公章', page: '落款处', ok: false, reason: '非 PDF 格式，需先转档', at: '10-31 10:02', by: '房某某' },
  { fileName: '退费账户确认书.pdf', docType: '退费确认书', seals: '公章', page: '确认人处', ok: true, reason: '', at: '10-30 17:22', by: '黄某某' },
  { fileName: '法定代表人身份证明.pdf', docType: '法代证明', seals: '公章', page: '落款处', ok: true, reason: '', at: '10-30 15:38', by: '黄某某' },
]

export interface StampFailureRow {
  cause: string
  stage: string
  last30: number
  autoRetry: boolean
  advice: string
}

export const DEMO_STAMP_FAILURES: StampFailureRow[] = [
  { cause: '骑缝章位置与印章库不符', stage: '盖章执行', last30: 3, autoRetry: false, advice: '检查文档页数与印章库登记的骑缝位置，必要时手工注入' },
  { cause: '文件已被新版替代', stage: '反查归属', last30: 5, autoRetry: false, advice: '确认取的是最新版文件，旧版禁止盖章' },
  { cause: '非 PDF 格式', stage: '格式校验', last30: 8, autoRetry: true, advice: '系统会自动转档为 PDF 后重试' },
  { cause: '印章使用权限不足', stage: '权限校验', last30: 2, autoRetry: false, advice: '由行政部授权对应印章，或改用其他可用章' },
  { cause: '文件不在绑定文件夹', stage: '反查归属', last30: 6, autoRetry: false, advice: '把文件放进已绑定的案件/合同文件夹后再试' },
]

export interface StampBatchRow {
  name: string
  docs: number
  pages: number
  seals: string
  note: string
}

export const DEMO_STAMP_BATCHES: StampBatchRow[] = [
  { name: '一审起诉全套', docs: 7, pages: 46, seals: '公章 + 法代章', note: '起诉状/证据清单/委托书/送达确认/退费账户/律所函/法代证明' },
  { name: '执行申请全套', docs: 5, pages: 28, seals: '公章', note: '执行申请书/限高申请/失信申请/账户确认/材料清单' },
  { name: '保全材料', docs: 3, pages: 15, seals: '公章 + 法代章', note: '保全申请书/担保函/财产线索' },
  { name: '归档补章', docs: 4, pages: 22, seals: '公章', note: '案卷封面/目录/办案小结/监督卡' },
]
