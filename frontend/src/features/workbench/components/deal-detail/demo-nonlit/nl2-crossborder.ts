/**
 * 非诉线 · 演示数据 · B. 跨境合同审查（泰国工厂租赁）· 审查结论（**仅用于录屏演示**，不参与真实业务）
 *
 * 这里只有「结论」：5 条修订建议、法条核验的三道规则闸 + 一层判断、一次核验的流程日志。
 * 支撑结论的材料（合同正文双语对照 / 外国法原文摘录 / 会话进度 / 筛选口径 / 对方律师意见）
 * 在 `nl2-crossborder-doc.ts`，它通过 `DEMO_REVISION_BY_ID` 回查本文件的修订。
 *
 * 约定：只出现在展示位置、不参与判断逻辑；人名机构一律脱敏；条文条款号两段一致。
 */


/* ═══════════════════════════════════════════════════════════
 * B. 跨境合同审查（泰国工厂租赁）
 * ═══════════════════════════════════════════════════════════ */

/** 合同审查：一条修订建议 */
export interface DemoContractRevision {
  id: string
  severity: 'high' | 'mid' | 'low'
  title: string
  /** 原文（英文） */
  original: string
  /** 原文的对照译文（双语视图红删那一行的中文栏） */
  originalZh: string
  /** 建议改为 */
  suggested: string
  /** 法条依据 */
  citation: string
  /** 核验状态 */
  verified: boolean
  /** 甲/乙方立场 */
  stance: string
}

export const DEMO_TH_CONTRACT_REVISIONS: DemoContractRevision[] = [
  {
    id: 'r1',
    severity: 'high',
    title: '租金调增无上限',
    original: 'Annual rent increase shall be 100% of the Consumer Price Index of the prior calendar year.',
    originalZh: '原文本：年度租金按上一年度居民消费价格指数的 100% 调增。',
    suggested: 'Annual rent increase shall be capped at 5% of the prior year rent, and in no event exceed the increase of the Consumer Price Index.',
    citation: '泰国《民商法典》第 538 条',
    verified: true,
    stance: '我方为承租方，应限制单方调增',
  },
  {
    id: 'r2',
    severity: 'high',
    title: '押金无法退还',
    original: 'The deposit shall be forfeited upon lease expiry without deduction of any kind.',
    originalZh: '原文本：租期届满即没收保证金，不作任何扣除。',
    suggested: 'The deposit shall be refunded within 30 days after lease expiry, less any amount actually owed by Lessee.',
    citation: '泰国《民商法典》第 546 条',
    verified: true,
    stance: '期满没收条款可能被认定无效',
  },
  {
    id: 'r3',
    severity: 'mid',
    title: '提前解约无救济',
    original: "Lessee shall forfeit the entire deposit and pay liquidated damages equal to six (6) months' rent.",
    originalZh: '原文本：承租方提前解约即没收全部保证金，并支付六个月租金违约金。',
    suggested: "Lessee may terminate upon 60 days' notice, and shall pay liquidated damages equal to three (3) months' rent.",
    citation: '泰国《民商法典》第 549 条',
    verified: true,
    stance: '违约责任应与实际损失相当',
  },
  {
    id: 'r4',
    severity: 'low',
    title: '管辖法院约定不明',
    original: 'Any dispute shall be submitted to the competent court of Thailand for adjudication.',
    originalZh: '原文本：任何争议提交泰国主管法院裁决。',
    suggested: 'Any dispute shall be submitted to the exclusive jurisdiction of the Rayong Provincial Court.',
    citation: '泰国《民事诉讼法典》第 3 条',
    verified: true,
    stance: '约定「主管法院」过于笼统',
  },
  {
    id: 'r5',
    severity: 'mid',
    title: '语言版本以泰文为准',
    original: 'In case of any discrepancy, the Thai version shall prevail.',
    originalZh: '原文本：如有歧义，以泰文文本为准。',
    suggested: 'The Chinese version shall prevail as between the parties, provided the Thai version governs for registration purposes.',
    citation: '—',
    verified: false,
    stance: '我方为中方承租方，泰文优先不利',
  },
]

/** 法条核验：三道规则闸 */
export interface DemoLawGate {
  n: string
  name: string
  kind: 'rule' | 'model'
  result: 'pass' | 'fail' | 'skip'
  detail: string
  ms: number
}

export const DEMO_LAW_GATES: DemoLawGate[] = [
  { n: '01', name: '该法是否存在', kind: 'rule', result: 'pass', detail: 'BARLC 数据库命中《泰国民商法典》', ms: 820 },
  { n: '02', name: '是否有可读正文', kind: 'rule', result: 'pass', detail: '全文 1,752 条均已收录', ms: 1240 },
  { n: '03', name: '条款号是否在范围内', kind: 'rule', result: 'pass', detail: '第 538 / 546 / 549 条均在 1–1752 内', ms: 380 },
  { n: '04', name: '条文是否支持该主张', kind: 'model', result: 'pass', detail: '判断层：语义比对通过，置信度 0.94', ms: 2680 },
]

/** 一次核验的完整流程日志 */
export interface DemoVerifyLogRow {
  at: string
  text: string
  kind: 'info' | 'ok' | 'warn'
}

export const DEMO_VERIFY_LOG: DemoVerifyLogRow[] = [
  { at: '00:00.0', text: '解析合同引用：识别到 4 处外国法引用', kind: 'info' },
  { at: '00:00.8', text: '规则闸 01 · 检索《泰国民商法典》→ 命中', kind: 'ok' },
  { at: '00:02.0', text: '规则闸 02 · 拉取正文 1,752 条 → 完整', kind: 'ok' },
  { at: '00:03.3', text: '规则闸 03 · 第 538 条在范围内 → 通过', kind: 'ok' },
  { at: '00:03.6', text: '规则闸 03 · 第 546 条在范围内 → 通过', kind: 'ok' },
  { at: '00:04.0', text: '规则闸 03 · 第 549 条在范围内 → 通过', kind: 'ok' },
  { at: '00:05.1', text: '判断层 · 第 538 条语义比对 → 支持限制调增', kind: 'ok' },
  { at: '00:07.8', text: '判断层 · 第 546 条语义比对 → 支持押金返还', kind: 'ok' },
  { at: '00:10.5', text: '判断层 · 第 549 条语义比对 → 支持缩短违约期', kind: 'ok' },
  { at: '00:10.9', text: '第 5 处引用「泰文优先」无外国法依据，标记为需律师判断', kind: 'warn' },
]
