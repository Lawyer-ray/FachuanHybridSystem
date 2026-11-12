/**
 * 演示数据 · G. 单案诉讼线 · 六阶段
 *
 * 这条线讲的是「一个案子怎么从一叠扫描件走到法院立案」：
 *   ① 收案 → ② 读懂 → ③ 缺件 → ④ 文书 → ⑤ 回扫 → ⑥ 校验
 * 每个阶段的数据都围绕**同一个案件**（谭某某金融借款），不是统计报表。
 * 与 x1/x2/x3 三个下钻层模块共用同一批材料口径。
 * 真实功能上线时整个文件删除即可。
 */

export interface IntakeSegmentRow {
  seq: number
  fileName: string
  type: string
  pages: string
  confidence: number
  status: 'ok' | 'review' | 'unrecognized'
  note: string
}

export const DEMO_INTAKE_SEGMENTS: IntakeSegmentRow[] = [
  { seq: 1, fileName: '个人购房借款担保合同', type: '借款合同', pages: 'P1–14', confidence: 0.98, status: 'ok', note: '建行标准版，骑缝完整' },
  { seq: 2, fileName: '借款借据及放款凭证', type: '放款凭证', pages: 'P15–16', confidence: 0.97, status: 'ok', note: '金额 820,000.00 元' },
  { seq: 3, fileName: '还款明细表（2019-2026）', type: '还款明细', pages: 'P17–24', confidence: 0.95, status: 'ok', note: '共 84 期，逾期 12 期' },
  { seq: 4, fileName: '催收记录汇总', type: '催收记录', pages: 'P25–28', confidence: 0.93, status: 'ok', note: '电话 11 次 / 上门 3 次' },
  { seq: 5, fileName: '借款人身份证复印', type: '身份证明', pages: 'P29', confidence: 0.99, status: 'ok', note: '正反面同页' },
  { seq: 6, fileName: '差额补足承诺函', type: '担保文件', pages: 'P30–31', confidence: 0.61, status: 'review', note: '落款日期被印章遮盖，需人工核' },
  { seq: 7, fileName: '（未识别）手写便签', type: '未识别', pages: 'P32', confidence: 0.24, status: 'unrecognized', note: '疑似银行内部批注，非案件材料' },
  { seq: 8, fileName: '还款账户流水', type: '银行流水', pages: 'P33–38', confidence: 0.96, status: 'ok', note: '与明细表勾稽一致' },
]

export interface UnderstandDocRow {
  fileName: string
  type: string
  chars: number
  pages: number
  method: '原生PDF' | 'OCR' | '表格还原'
  quality: 'high' | 'medium'
  /** markdown 首段摘录 */
  excerpt: string
}

export const DEMO_UNDERSTAND_DOCS: UnderstandDocRow[] = [
  {
    fileName: '个人购房借款担保合同',
    type: '借款合同',
    chars: 12480,
    pages: 14,
    method: '原生PDF',
    quality: 'high',
    excerpt: '## 个人购房借款/担保合同\n\n**合同编号**：DEMO202100000001\n**借款人**：谭某某\n**贷款人**：某某银行某某支行\n\n### 第一条 贷款金额\n贷款金额为人民币 **820,000.00 元**（大写：捌拾贰万元整）。',
  },
  {
    fileName: '借款借据及放款凭证',
    type: '放款凭证',
    chars: 860,
    pages: 2,
    method: '原生PDF',
    quality: 'high',
    excerpt: '## 借款借据\n\n兹借到人民币 820,000.00 元，期限自 2019-03-18 至 2039-03-18。\n\n放款日期：2019-03-18　放款账号：6210 **** **** 3321',
  },
  {
    fileName: '还款明细表（2019-2026）',
    type: '还款明细',
    chars: 6420,
    pages: 8,
    method: '表格还原',
    quality: 'high',
    excerpt: '## 还款明细\n\n| 期次 | 应还日期 | 应还本息 | 实还 | 逾期天数 |\n|---|---|---|---|---|\n| 1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0 |\n| … | | | | |\n| 85 | 2026-04-18 | 5,432.11 | 0.00 | 198 |',
  },
  {
    fileName: '还款账户流水',
    type: '银行流水',
    chars: 9180,
    pages: 6,
    method: '表格还原',
    quality: 'medium',
    excerpt: '## 账户交易明细\n\n| 日期 | 摘要 | 金额 | 余额 |\n|---|---|---|---|\n| 2026-01-18 | 代扣 | 5,432.11 | 1,204.88 |\n| 2026-02-18 | 代扣失败 | 0.00 | 1,204.88 |',
  },
]

export interface GapNoticeRow {
  item: string
  reason: string
  severity: 'blocker' | 'normal'
  channel: string
  sentAt: string
  status: 'waiting' | 'received' | 'pending'
  reply: string
}

export const DEMO_GAP_NOTICES: GapNoticeRow[] = [
  { item: '催收记录（2025 年后）', reason: '现有催收记录止于 2025-06，缺最近 12 个月，影响诉讼时效举证', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'received', reply: '客户已于 10-30 补传 2 份' },
  { item: '借款人最新联系方式', reason: '合同留存电话已停用，送达地址需更新', severity: 'normal', channel: '微信', sentAt: '10-28 14:02', status: 'received', reply: '客户提供新手机号与现住址' },
  { item: '抵押物权属证明', reason: '合同约定抵押，但未见不动产权证复印件', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'waiting', reply: '—' },
  { item: '共同借款人身份证明', reason: '合同列明两位借款人，仅见一人身份证', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'waiting', reply: '—' },
  { item: '还款账户近半年流水', reason: '已有流水止于 2026-04，建议补至起诉前一月', severity: 'normal', channel: '邮件', sentAt: '10-30 09:15', status: 'pending', reply: '—' },
]

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

export interface ReturnedMailRow {
  subject: string
  from: string
  attachments: number
  matchedCase: string
  matchedBy: string
  action: string
  at: string
}

export const DEMO_RETURNED_MAILS: ReturnedMailRow[] = [
  { subject: 'Re: 谭某某案 补充材料', from: '客户经理 王某某', attachments: 2, matchedCase: '谭某某金融借款', matchedBy: '案号 + 当事人名', action: '已自动下载并归案', at: '11-01 09:12' },
  { subject: '扫描件-不动产权证', from: '行政 陈某某', attachments: 1, matchedCase: '谭某某金融借款', matchedBy: '文件名关键词', action: '已自动归案', at: '11-01 10:05' },
  { subject: '（20XX）粤0106民初XXXX号 受理通知书', from: '法院短信转发', attachments: 1, matchedCase: '谭某某金融借款', matchedBy: '案号精确匹配', action: '已归案并回填案号', at: '11-01 11:30' },
  { subject: 'FW: 律师函签收回执', from: '客户 李某某', attachments: 1, matchedCase: '待人工确认', matchedBy: '匹配度 62%，低于阈值', action: '已放入待处理', at: '11-01 13:48' },
]

export interface SignCheckRow {
  docName: string
  needSeal: string
  needSign: string
  sealOk: boolean
  signOk: boolean
  note: string
}

export const DEMO_SIGN_CHECKS: SignCheckRow[] = [
  { docName: '民事起诉状', needSeal: '公章 + 法定代表人章', needSign: '具状人签名', sealOk: true, signOk: true, note: '骑缝章覆盖全部 4 页' },
  { docName: '证据清单', needSeal: '公章', needSign: '—', sealOk: true, signOk: true, note: '与证据材料一并骑缝' },
  { docName: '授权委托书', needSeal: '公章', needSign: '委托人签名 + 指印', sealOk: true, signOk: false, note: '委托人签名处空白，需重新签署' },
  { docName: '送达地址确认书', needSeal: '公章', needSign: '确认人签名', sealOk: true, signOk: true, note: '地址与立案信息一致' },
  { docName: '退费账户确认书', needSeal: '公章', needSign: '—', sealOk: false, signOk: true, note: '未盖章，需补盖财务章' },
  { docName: '授权委托证明材料', needSeal: '公章', needSign: '—', sealOk: true, signOk: true, note: '律所函 + 执业证复印件齐全' },
]

export interface IntakeEventRow {
  at: string
  event: string
  detail: string
  ms: number
}

export const DEMO_INTAKE_EVENTS: IntakeEventRow[] = [
  { at: '10-28 09:41', event: '客户上传', detail: '王某某 通过客户链接上传 银行个贷不良_首批材料.zip', ms: 0 },
  { at: '10-28 09:41', event: '自动下载', detail: '12.4 MB · 6 个源文件', ms: 1240 },
  { at: '10-28 09:42', event: '合并整包', detail: '6 个源文件 → 38 页单一 PDF', ms: 860 },
  { at: '10-28 09:42', event: '页面识别', detail: '逐页文本提取 + 版式判断', ms: 4200 },
  { at: '10-28 09:43', event: '分段完成', detail: '识别出 8 份材料，其中 2 份需人工确认', ms: 2100 },
  { at: '10-28 09:43', event: '自动归案', detail: '6 份高置信度材料已挂到本案', ms: 680 },
  { at: '10-28 09:44', event: '通知律师', detail: '待核对 2 份，已在待办里提醒', ms: 120 },
]

export interface UnderstandFieldRow {
  doc: string
  field: string
  value: string
  confidence: number
  source: string
}

export const DEMO_UNDERSTAND_FIELDS: UnderstandFieldRow[] = [
  { doc: '借款合同', field: '合同编号', value: 'DEMO202100000001', confidence: 0.99, source: '第 1 页首行' },
  { doc: '借款合同', field: '借款人', value: '谭某某', confidence: 0.98, source: '第 1 页当事人栏' },
  { doc: '借款合同', field: '贷款金额', value: '¥820,000.00', confidence: 0.99, source: '第一条 贷款金额' },
  { doc: '借款合同', field: '借款期限', value: '2019-03-18 至 2039-03-18', confidence: 0.97, source: '第二条 借款期限' },
  { doc: '借款合同', field: '年利率', value: '4.90%', confidence: 0.96, source: '第四条 利率' },
  { doc: '借款合同', field: '逾期罚息', value: '约定利率上浮 50%', confidence: 0.95, source: '第九条 违约责任' },
  { doc: '借款合同', field: '管辖法院', value: '合同签订地人民法院', confidence: 0.88, source: '第十七条 争议解决' },
  { doc: '还款明细', field: '已还期数', value: '84 期', confidence: 0.99, source: '表格行数统计' },
  { doc: '还款明细', field: '逾期期数', value: '12 期', confidence: 0.98, source: '逾期天数列' },
  { doc: '还款明细', field: '最后还款日', value: '2026-04-18', confidence: 0.97, source: '表格末行' },
  { doc: '催收记录', field: '催收次数', value: '电话 11 次 / 上门 3 次', confidence: 0.94, source: '记录汇总页' },
  { doc: '催收记录', field: '最后催收日', value: '2025-06-12', confidence: 0.93, source: '记录末条' },
]

export interface GapReceivedRow {
  item: string
  fileName: string
  pages: number
  receivedAt: string
  recognized: boolean
  note: string
}

export const DEMO_GAP_RECEIVED: GapReceivedRow[] = [
  { item: '催收记录（2025 年后）', fileName: '催收记录_补充_2025Q3-Q4.pdf', pages: 6, receivedAt: '10-30 09:20', recognized: true, note: '识别到电话催收 7 次、上门 2 次' },
  { item: '借款人最新联系方式', fileName: '客户补充信息.txt', pages: 1, receivedAt: '10-30 09:22', recognized: true, note: '手机号 138****XXXX，现住址已更新' },
]

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

export interface ScanBatchRow {
  batch: string
  scannedAt: string
  pages: number
  matched: string
  confidence: number
  status: 'auto' | 'manual'
}

export const DEMO_SCAN_BATCHES: ScanBatchRow[] = [
  { batch: '行政扫描_11-01_0920', scannedAt: '11-01 09:20', pages: 12, matched: '谭某某金融借款', confidence: 0.96, status: 'auto' },
  { batch: '行政扫描_11-01_1005', scannedAt: '11-01 10:05', pages: 4, matched: '谭某某金融借款', confidence: 0.94, status: 'auto' },
  { batch: '行政扫描_11-01_1430', scannedAt: '11-01 14:30', pages: 8, matched: '其他案件（2 件候选）', confidence: 0.71, status: 'manual' },
]

export interface FilingCheckRow {
  check: string
  result: 'pass' | 'warn' | 'fail'
  value: string
  detail: string
}

export const DEMO_FILING_CHECKS: FilingCheckRow[] = [
  { check: '当事人主体适格', result: 'pass', value: '原告 1 · 被告 2', detail: '借贷双方均具备诉讼主体资格' },
  { check: '管辖', result: 'pass', value: '广州市天河区人民法院', detail: '合同约定签订地法院，与立案法院一致' },
  { check: '诉讼时效', result: 'pass', value: '未届满', detail: '最后还款日 2026-04-18，起算未满三年' },
  { check: '金额三处一致', result: 'fail', value: '差 31.85 元', detail: '起诉状 998,670.21 / 立案表单 998,702.06' },
  { check: '签字盖章', result: 'fail', value: '2 份未通过', detail: '授权委托书缺签名、退费确认书缺盖章' },
  { check: '要素式起诉状', result: 'warn', value: '待转换', detail: '法院要求要素式，当前为传统格式' },
]

export interface SourceFileRow {
  name: string
  size: string
  pages: number
  kind: string
}

export const DEMO_INTAKE_SOURCES: SourceFileRow[] = [
  { name: '借款合同.pdf', size: '3.2 MB', pages: 14, kind: 'PDF 原生' },
  { name: '借据.pdf', size: '0.4 MB', pages: 2, kind: 'PDF 扫描' },
  { name: '还款明细.xlsx', size: '0.2 MB', pages: 8, kind: '表格' },
  { name: '催收记录.pdf', size: '1.8 MB', pages: 4, kind: 'PDF 扫描' },
  { name: '身份证.jpg', size: '1.1 MB', pages: 1, kind: '图片' },
  { name: '流水.pdf', size: '5.7 MB', pages: 9, kind: 'PDF 扫描' },
]

export interface UnderstandIssueRow {
  doc: string
  issue: string
  impact: string
  action: string
}

export const DEMO_UNDERSTAND_ISSUES: UnderstandIssueRow[] = [
  { doc: '差额补足承诺函', issue: '落款日期被红色印章覆盖', impact: '抽不到签署日期，影响生效时间判断', action: '已标记待人工核对' },
  { doc: '催收记录', issue: '手写批注部分 OCR 置信度 0.58', impact: '催收次数可能少算', action: '已保留原图，律师可对照' },
  { doc: '还款账户流水', issue: '表格跨页断行，第 4-5 页表头重复', impact: '需按表头重新拼表', action: '已自动拼表，标记需复核' },
]

export interface GapTemplateRow {
  severity: string
  title: string
  body: string
  channel: string
}

export const DEMO_GAP_TEMPLATES: GapTemplateRow[] = [
  { severity: '硬阻塞', title: '影响立案的缺件', body: '以下材料缺失将无法立案，请尽快补充：{list}', channel: '短信 + 邮件 + 微信' },
  { severity: '一般', title: '建议补充的材料', body: '以下材料建议补充，不影响先立案：{list}', channel: '邮件' },
  { severity: '催办', title: '补件催办提醒', body: '您还有 {n} 项材料未补齐，已超 {days} 天，请尽快处理', channel: '短信' },
  { severity: '回执', title: '已收妥确认', body: '您补交的 {n} 份材料已收到并归档，无需再重复提交', channel: '短信' },
]

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

export interface ReturnedDiffRow {
  stage: string
  before: string
  after: string
  delta: string
}

export const DEMO_RETURNED_DIFF: ReturnedDiffRow[] = [
  { stage: '材料份数', before: '8 份', after: '12 份', delta: '+4' },
  { stage: '总页数', before: '38 页', after: '62 页', delta: '+24' },
  { stage: '缺件项', before: '5 项', after: '3 项', delta: '-2' },
  { stage: '硬阻塞', before: '3 项', after: '1 项', delta: '-2' },
  { stage: '起诉条件', before: '4/6 通过', after: '5/6 通过', delta: '+1' },
]

export interface FilingFixRow {
  item: string
  fix: string
  owner: string
  eta: string
  auto: boolean
}

export const DEMO_FILING_FIXES: FilingFixRow[] = [
  { item: '金额三处不一致', fix: '按起诉状定稿基准重写立案表单标的额（差 31.85 元）', owner: '系统自动', eta: '即时', auto: true },
  { item: '授权委托书缺签名', fix: '通知当事人补签，签署后重新扫描上传', owner: '经办律师', eta: '1 个工作日', auto: false },
  { item: '退费确认书缺盖章', fix: '推送 OA 盖章流程，盖财务章后回传', owner: '行政', eta: '当日', auto: false },
  { item: '要素式起诉状待转换', fix: '用「要素式转换」把传统起诉状转成法院要素式', owner: '系统自动', eta: '1 分钟', auto: true },
]
