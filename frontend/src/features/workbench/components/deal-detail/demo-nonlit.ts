/**
 * 非诉线 · 演示数据（**仅用于录屏演示**，不参与真实业务）
 *
 * 与诉讼线（bank-litigation/components/demo-data.ts）同样的约定：
 *   1. 只出现在展示位置，不参与任何判断逻辑
 *   2. 全部脱敏：人名某某、机构某某公司、案号（20XX）…
 *   3. 数值口径真实：金额千分位、日期连续、页码区间合理
 *
 * 覆盖三个非诉场景：
 *   A. 专项服务（关厂清盘）—— 7 阶段 / 交付物 / 文件夹
 *   B. 跨境合同审查（泰国工厂租赁）—— 条款逐条审查 / 泰文法条核验
 *   C. 常年法律顾问 —— 服务事项流
 */

/* ═══════════════════════════════════════════════════════════
 * A. 专项服务：关厂清盘
 * ═══════════════════════════════════════════════════════════ */

/** 阶段交付物（挂在阶段下的小文件） */
export interface DemoDeliverable {
  name: string
  pages: number
  status: 'done' | 'drafting' | 'pending'
  updatedAt: string
  owner: string
}

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

/* ═══════════════════════════════════════════════════════════
 * C. 常年法律顾问：服务事项流
 * ═══════════════════════════════════════════════════════════ */

/** 一条服务事项 */
export interface DemoServiceItem {
  id: string
  date: string
  kind: '咨询' | '合同审查' | '出具意见' | '会议出席' | '培训'
  title: string
  /** 用时（小时） */
  hours: number
  status: 'done' | 'doing'
  /** 交付形式 */
  output: string
}

export const DEMO_SERVICE_ITEMS: DemoServiceItem[] = [
  { id: 's1', date: '2026-11-26', kind: '合同审查', title: '审阅《设备采购框架协议》并出具修改建议', hours: 2.5, status: 'done', output: '修订稿 + 审查意见 3 页' },
  { id: 's2', date: '2026-11-24', kind: '咨询', title: '解答劳动合同到期不续签的经济补偿口径', hours: 0.8, status: 'done', output: '口头答复 + 要点备忘' },
  { id: 's3', date: '2026-11-21', kind: '出具意见', title: '就厂房租赁合同提前解约出具法律意见书', hours: 4.0, status: 'done', output: '法律意见书 6 页' },
  { id: 's4', date: '2026-11-19', kind: '会议出席', title: '列席股东会，就增资扩股程序发表意见', hours: 3.0, status: 'done', output: '会议纪要签章版' },
  { id: 's5', date: '2026-11-15', kind: '合同审查', title: '审阅《员工保密与竞业限制协议》模板', hours: 1.5, status: 'done', output: '修订稿' },
  { id: 's6', date: '2026-11-12', kind: '培训', title: '为销售部门做「合同签署权限」专题培训', hours: 2.0, status: 'done', output: '课件 32 页 + 签到表' },
  { id: 's7', date: '2026-11-08', kind: '咨询', title: '答复应收账款诉讼时效中断的取证要点', hours: 1.2, status: 'done', output: '书面答复 2 页' },
  { id: 's8', date: '2026-11-03', kind: '出具意见', title: '就供应商违约索赔方案出具分析意见', hours: 3.5, status: 'done', output: '分析意见 8 页' },
]

/** 常法服务统计 */
export const DEMO_SERVICE_STATS = {
  contractDays: 365,
  usedDays: 96,
  remainDays: 269,
  totalHours: 18.5,
  monthlyQuota: 20,
  items: 8,
  byKind: [
    { kind: '合同审查', n: 2, hours: 4.0 },
    { kind: '咨询', n: 2, hours: 2.0 },
    { kind: '出具意见', n: 2, hours: 7.5 },
    { kind: '会议出席', n: 1, hours: 3.0 },
    { kind: '培训', n: 1, hours: 2.0 },
  ],
}

/* ═══════════════════════════════════════════════════════════
 * D. 跨境合同审查（泰国工厂租赁）· 双语文档视图的补充数据
 *
 * 与上面的 B 段共用 DEMO_TH_CONTRACT_REVISIONS（那 5 条修订是审查结论），
 * 这里补的是「支撑结论的材料」：合同正文双语对照、每条修订对应的一条外国法原文、
 * 审查会话进度、对方律师意见。
 *
 * 全部虚构：当事方用「某某公司 / 某某工业园」，条文英文按泰国《民商法典》
 * 通行英译的表述风格重写，条款号与 B 段的引用一致。
 * ═══════════════════════════════════════════════════════════ */

/** 合同正文里带修订的一段（en 为改后文，zh 为其对应译文） */
export interface DemoNl2ClauseSegment {
  text: string
  change?: 'mod' | 'add'
  rev?: string
}

/** 合同正文的一句（en 原文 + zh 译文），两栏按修订点切段以做红删绿增 */
export interface DemoNl2ClauseSentence {
  en: DemoNl2ClauseSegment[]
  zh: DemoNl2ClauseSegment[]
}

/** 合同正文的一条 ARTICLE（双语对照的最小对齐单位） */
export interface DemoNl2Clause {
  no: string
  titleEn: string
  titleZh: string
  sentences: DemoNl2ClauseSentence[]
  /** 挂在这一条上的修订 id；空数组 = 我方无异议 */
  revs: string[]
}

export const DEMO_NL2_CONTRACT: DemoNl2Clause[] = [
  {
    no: '1',
    titleEn: 'PREMISES AND TERM',
    titleZh: '租赁标的与期限',
    revs: [],
    sentences: [
      {
        en: [{ text: 'Lessor hereby leases to Lessee the factory building with a gross floor area of 8,400 square metres located in the Rayong Industrial Estate, together with the land appurtenant thereto.' }],
        zh: [{ text: '出租方兹将位于罗勇工业园的厂房（建筑面积 8,400 平方米）及其附属土地出租给承租方使用。' }],
      },
      {
        en: [{ text: 'The term of this Lease shall be three (3) years commencing on 1 March 2027 and expiring on 28 February 2030, unless terminated earlier in accordance with ARTICLE 8.' }],
        zh: [{ text: '本合同租期为三年，自 2027 年 3 月 1 日起至 2030 年 2 月 28 日止，但依第 8 条提前终止的除外。' }],
      },
    ],
  },
  {
    no: '2',
    titleEn: 'RENT AND ESCALATION',
    titleZh: '租金及调增',
    revs: ['r1'],
    sentences: [
      {
        en: [{ text: 'The monthly rent is THB 1,260,000, payable in advance within five (5) banking days of each calendar month.' }],
        zh: [{ text: '月租金为 1,260,000 泰铢，应于每个自然月前五个银行工作日内预付。' }],
      },
      {
        en: [
          { text: 'Annual rent increase shall be ' },
          { text: 'capped at 5% of the prior year rent, and in no event exceed the increase of the Consumer Price Index', change: 'mod', rev: 'r1' },
          { text: ' of the prior calendar year.' },
        ],
        zh: [
          { text: '年度租金调增幅度' },
          { text: '以上一年度租金的 5% 为上限，且不得超过上一年度居民消费价格指数的涨幅', change: 'mod', rev: 'r1' },
          { text: '。' },
        ],
      },
    ],
  },
  {
    no: '3',
    titleEn: 'SECURITY DEPOSIT',
    titleZh: '履约保证金',
    revs: ['r2'],
    sentences: [
      {
        en: [{ text: 'Lessee shall pay a security deposit equal to three (3) months rent upon execution of this Lease.' }],
        zh: [{ text: '承租方应于本合同签署时支付相当于三个月租金的履约保证金。' }],
      },
      {
        en: [
          { text: 'The deposit shall be ' },
          { text: 'refunded within 30 days after lease expiry, less any amount actually owed by Lessee', change: 'mod', rev: 'r2' },
          { text: '.' },
        ],
        zh: [
          { text: '该保证金应' },
          { text: '于租期届满后 30 日内退还，但可扣除承租方实际欠付的款项', change: 'mod', rev: 'r2' },
          { text: '。' },
        ],
      },
    ],
  },
  {
    no: '4',
    titleEn: 'UTILITIES AND SERVICE CHARGES',
    titleZh: '公用事业费与服务费',
    revs: [],
    sentences: [
      {
        en: [{ text: 'Lessee shall bear all costs of electricity, water and telecommunication consumed at the premises, settled monthly against the meter readings.' }],
        zh: [{ text: '承租方应承担租赁物范围内发生的电费、水费及通讯费，按抄表数按月结算。' }],
      },
      {
        en: [{ text: 'The service charge of THB 18 per square metre per month covers common area maintenance and estate security.' }],
        zh: [{ text: '每月每平方米 18 泰铢的服务费涵盖公共区域维护与园区安保。' }],
      },
    ],
  },
  {
    no: '5',
    titleEn: 'USE AND COMPLIANCE',
    titleZh: '使用用途与合规',
    revs: [],
    sentences: [
      {
        en: [{ text: 'The premises shall be used solely for the manufacturing and warehousing of automotive parts, and Lessee shall obtain all factory licences required under Thai law.' }],
        zh: [{ text: '租赁物仅可用于汽车零部件的生产与仓储，承租方应按泰国法律取得全部工厂许可证。' }],
      },
      {
        en: [{ text: 'Lessee shall comply with the Factory Act B.E. 2535 and all applicable environmental regulations during the term.' }],
        zh: [{ text: '租期内，承租方应遵守《工厂法》（佛历 2535 年）及所有适用的环保法规。' }],
      },
    ],
  },
  {
    no: '6',
    titleEn: 'REPAIRS AND MAINTENANCE',
    titleZh: '维修与保养',
    revs: [],
    sentences: [
      {
        en: [{ text: 'Lessor shall keep the structure, roof and load-bearing walls in good repair throughout the term.' }],
        zh: [{ text: '租期内，出租方应保持主体结构、屋顶及承重墙处于良好状态。' }],
      },
      {
        en: [{ text: 'Lessee shall be responsible for day-to-day maintenance and for any damage caused by its employees or contractors.' }],
        zh: [{ text: '承租方负责日常保养，并对其员工或承包人造成的损坏负责。' }],
      },
    ],
  },
  {
    no: '7',
    titleEn: 'INSURANCE AND INDEMNITY',
    titleZh: '保险与赔偿',
    revs: [],
    sentences: [
      {
        en: [{ text: 'Lessor shall insure the premises against fire and allied perils and shall name Lessee as loss payee as its interest appears.' }],
        zh: [{ text: '出租方应为租赁物投保火灾及附加风险，并按承租方的利益将其列为赔付受益人。' }],
      },
      {
        en: [{ text: 'Each party shall indemnify the other against third-party claims arising from its own negligence.' }],
        zh: [{ text: '各方应就因其自身过失导致的第三方索赔向对方作出赔偿。' }],
      },
    ],
  },
  {
    no: '8',
    titleEn: 'EARLY TERMINATION',
    titleZh: '提前终止',
    revs: ['r3'],
    sentences: [
      {
        en: [{ text: 'Lessor may terminate this Lease upon Lessee committing a material breach which remains uncured thirty (30) days after written notice.' }],
        zh: [{ text: '承租方发生重大违约且在收到书面通知后三十日内未予纠正的，出租方可以终止本合同。' }],
      },
      {
        en: [
          { text: 'Lessee may ' },
          { text: "terminate upon 60 days' notice, and shall pay liquidated damages equal to three (3) months' rent", change: 'mod', rev: 'r3' },
          { text: '.' },
        ],
        zh: [
          { text: '承租方可' },
          { text: '提前 60 日通知终止，并支付相当于三个月租金的违约金', change: 'mod', rev: 'r3' },
          { text: '。' },
        ],
      },
    ],
  },
  {
    no: '9',
    titleEn: 'GOVERNING LAW AND DISPUTE RESOLUTION',
    titleZh: '适用法律与争议解决',
    revs: ['r4', 'r5'],
    sentences: [
      {
        en: [
          { text: 'Any dispute shall be submitted to the ' },
          { text: 'exclusive jurisdiction of the Rayong Provincial Court', change: 'mod', rev: 'r4' },
          { text: '.' },
        ],
        zh: [
          { text: '任何争议应提交' },
          { text: '罗勇府法院专属管辖', change: 'mod', rev: 'r4' },
          { text: '。' },
        ],
      },
      {
        en: [{ text: 'This Lease is governed by the laws of the Kingdom of Thailand.' }],
        zh: [{ text: '本合同适用泰王国法律。' }],
      },
      {
        en: [
          { text: 'This Lease is executed in Thai, English and Chinese. ' },
          { text: 'The Chinese version shall prevail as between the parties, provided the Thai version governs for registration purposes.', change: 'mod', rev: 'r5' },
        ],
        zh: [
          { text: '本合同以泰文、英文、中文三种文本签署。' },
          { text: '当事人之间以中文文本为准，但办理登记时以泰文文本为准。', change: 'mod', rev: 'r5' },
        ],
      },
    ],
  },
]

/** 一条修订对应的外国法原文摘录（英文，20-40 词）+ 出处 */
export interface DemoNl2LawExcerpt {
  rev: string
  /** 法条名（中文） */
  law: string
  /** 条款号 */
  article: string
  /** 条文英文原文摘录（20-40 词） */
  textEn: string
  /** 数据库出处与收录状态 */
  source: string
  retrievedAt: string
  /** 判断层结论 */
  supports: string
  /** 判断层置信度 0-1 */
  confidence: number
}

export const DEMO_NL2_LAW_EXCERPTS: DemoNl2LawExcerpt[] = [
  {
    rev: 'r1',
    law: '泰国《民商法典》',
    article: '第 538 条',
    textEn:
      'If the rent is fixed by agreement for a definite period, the lessor may not increase it before the expiry of that period. Any stipulation to the contrary is voidable at the instance of the lessee.',
    source: 'BARLC · 泰国民商法典（英译）· 第 2 编 第 4 章 · 收录完整',
    retrievedAt: '核验 00:05.1',
    supports: '单方调增条款与 538 条的期间内不得调增相冲突，支持以 5% 封顶改写',
    confidence: 0.94,
  },
  {
    rev: 'r2',
    law: '泰国《民商法典》',
    article: '第 546 条',
    textEn:
      'On the termination of the hire property, if the lessee owes no rent or other obligations under the contract, the lessor shall return the security deposit to the lessee without delay.',
    source: 'BARLC · 泰国民商法典（英译）· 第 2 编 第 4 章 · 收录完整',
    retrievedAt: '核验 00:07.8',
    supports: '「期满没收且不作任何扣除」违反 546 条的返还义务，支持改为 30 日内退还',
    confidence: 0.96,
  },
  {
    rev: 'r3',
    law: '泰国《民商法典》',
    article: '第 549 条',
    textEn:
      'If the lessee fails to perform his obligations, the lessor may terminate the contract; this provision does not affect the right to claim damages for any actual loss sustained by the lessor.',
    source: 'BARLC · 泰国民商法典（英译）· 第 2 编 第 4 章 · 收录完整',
    retrievedAt: '核验 00:10.5',
    supports: '违约救济限于实际损失，六个月租金违约金显失相当，支持压缩为三个月',
    confidence: 0.89,
  },
  {
    rev: 'r4',
    law: '泰国《民事诉讼法典》',
    article: '第 3 条',
    textEn:
      'An action shall be brought in the court of the domicile of the defendant or of the place where the cause of action arose, unless the parties have agreed to confer jurisdiction on a specified court.',
    source: 'BARLC · 泰国民事诉讼法典（英译）· 第 1 章 · 收录完整',
    retrievedAt: '核验 00:11.2',
    supports: '当事人可约定特定法院，支持将「泰国主管法院」具体化为罗勇府法院',
    confidence: 0.91,
  },
]

/** 审查会话进度记录（合同 9 条逐条走） */
export interface DemoNl2ReviewProgress {
  total: number
  reviewed: number
  remain: number
  /** 已用时 */
  elapsed: string
  /** 预计剩余 */
  eta: string
  /** 最近落笔的条款 */
  lastClause: string
  /** 审查人 */
  reviewer: string
}

export const DEMO_NL2_REVIEW_PROGRESS: DemoNl2ReviewProgress = {
  total: 9,
  reviewed: 7,
  remain: 2,
  elapsed: '42 分钟',
  eta: '约 12 分钟',
  lastClause: 'ARTICLE 7 · 保险与赔偿',
  reviewer: '黄某某',
}

/** 审查维度筛选口径（顶部 tabs）。revIds 为空 = 全部 */
export interface DemoNl2Filter {
  id: string
  label: string
  revIds: string[]
}

export const DEMO_NL2_FILTERS: DemoNl2Filter[] = [
  { id: 'all', label: '全部', revIds: [] },
  { id: 'high', label: '高', revIds: ['r1', 'r2'] },
  { id: 'mid', label: '中', revIds: ['r3', 'r5'] },
  { id: 'low', label: '低', revIds: ['r4'] },
  { id: 'verified', label: '已挂法条', revIds: ['r1', 'r2', 'r3', 'r4'] },
  { id: 'manual', label: '需律师判断', revIds: ['r5'] },
]

/** 对方律师（出租方代理）的意见 */
export interface DemoNl2CounterOpinion {
  id: string
  rev: string
  author: string
  at: string
  opinion: string
  /** 对方立场：接受 / 还价 / 拒绝 */
  attitude: '接受' | '还价' | '拒绝'
}

export const DEMO_NL2_COUNTER_OPINIONS: DemoNl2CounterOpinion[] = [
  {
    id: 'o1',
    rev: 'r1',
    author: '出租方代理律师 · Somchai 律师（虚构）',
    at: '11-28 10:12',
    opinion: '5% 封顶可谈，但须同时约定：若 CPI 连续两年低于 2%，则按 2% 保底调增。',
    attitude: '还价',
  },
  {
    id: 'o2',
    rev: 'r2',
    author: '出租方代理律师 · Somchai 律师（虚构）',
    at: '11-28 10:20',
    opinion: '保证金返还期限由 30 日改为 45 日可接受，但保留「未结清水电费可先行抵扣」的权利。',
    attitude: '还价',
  },
  {
    id: 'o3',
    rev: 'r3',
    author: '出租方代理律师 · Somchai 律师（虚构）',
    at: '11-28 10:35',
    opinion: '违约金三个月租金低于我方坏账风险，最多退让至四个月，不接受 60 日通知期。',
    attitude: '拒绝',
  },
  {
    id: 'o4',
    rev: 'r4',
    author: '出租方代理律师 · Somchai 律师（虚构）',
    at: '11-28 10:41',
    opinion: '同意罗勇府法院专属管辖，但要求增加「争议标的超过 2 亿泰铢时提交中央知识产权与国际贸易法院」的例外。',
    attitude: '接受',
  },
]

/** 修订 id → 修订建议（双语视图按 id 回查被删原句，避免在两处重复维护文案） */
export const DEMO_REVISION_BY_ID: Record<string, DemoContractRevision> = Object.fromEntries(
  DEMO_TH_CONTRACT_REVISIONS.map((r) => [r.id, r]),
)

/* ═══════════════════════════════════════════════════════════
 * E. 专项服务（关厂清盘）· 阶段抽屉 / 交付物 / 甘特 / 风险 / 客户确认
 *
 * 前四段是「结论」，这一段是**过程证据**：谁在什么时候动了哪个阶段、
 * 每份交付物改过几版、哪些风险还挂着、客户哪天点了头。律师点开任意一行
 * 都能看到依据，而不是一句「已完成」。
 *
 * 全部虚构并脱敏：经办人一律「黄某某 / 房某某」，客户与债权人用「某某公司」。
 * ═══════════════════════════════════════════════════════════ */

/** 阶段变更记录（谁 / 什么时候 / 把什么改成什么） */
export interface DemoNl1ChangeLog {
  id: string
  at: string
  who: string
  /** 变更类型：日期 / 状态 / 范围 / 交付物 / 验收标准 */
  kind: '日期' | '状态' | '范围' | '交付物' | '验收标准'
  /** 改的是哪个阶段（阶段名，与 DEMO_NONLIT_PHASES.name 对齐） */
  phase: string
  from: string
  to: string
  reason: string
}

export const DEMO_NL1_CHANGE_LOGS: DemoNl1ChangeLog[] = [
  {
    id: 'cl1',
    at: '2026-10-24 17:32',
    who: '黄某某',
    kind: '范围',
    phase: '尽职调查',
    from: '工商 + 税务两项底稿',
    to: '工商 + 税务 + 社保 + 债务四项底稿',
    reason: '关厂涉及职工安置，社保清缴情况是补偿测算的前提，补进尽调范围',
  },
  {
    id: 'cl2',
    at: '2026-11-08 09:12',
    who: '房某某',
    kind: '状态',
    phase: '尽职调查',
    from: '进行中',
    to: '已完成',
    reason: '四项底稿全部归档，客户在 11-07 邮件确认收悉',
  },
  {
    id: 'cl3',
    at: '2026-11-18 16:20',
    who: '房某某',
    kind: '日期',
    phase: '方案设计',
    from: '2026-11-09 至 2026-11-15',
    to: '2026-11-09 至 2026-11-20',
    reason: '客户内部需先开董事会，书面确认推迟 5 天，计划顺延',
  },
  {
    id: 'cl4',
    at: '2026-11-20 11:05',
    who: '黄某某',
    kind: '验收标准',
    phase: '方案设计',
    from: '出具关厂方案',
    to: '出具关厂方案并取得客户书面确认',
    reason: '口头同意不能作为阶段完成依据，验收标准补上「书面确认」',
  },
  {
    id: 'cl5',
    at: '2026-11-21 10:40',
    who: '房某某',
    kind: '范围',
    phase: '文件起草',
    from: '职工安置文书（单阶段）',
    to: '职工安置文书 + 债权债务与决议（两子阶段）',
    reason: '债权人会议与职工安置分属两条审批链，拆开验收避免互相拖累',
  },
  {
    id: 'cl6',
    at: '2026-11-27 15:18',
    who: '黄某某',
    kind: '交付物',
    phase: '文件起草',
    from: '职工安置方案（页码 21 页）',
    to: '职工安置方案与补偿测算表（34 页）',
    reason: '客户要求把经济补偿测算并入方案，单独拆表容易漏签',
  },
  {
    id: 'cl7',
    at: '2026-12-28 15:40',
    who: '房某某',
    kind: '状态',
    phase: '债权债务与决议',
    from: '进行中',
    to: '已完成',
    reason: '债权人会议决议签字版已回收（32 户债权人中 29 户签署，达到表决比例）',
  },
  {
    id: 'cl8',
    at: '2027-01-04 09:26',
    who: '黄某某',
    kind: '日期',
    phase: '登记与注销',
    from: '2027-01-16 至 2027-03-31',
    to: '2027-02-01 至 2027-04-15',
    reason: '税务清算需等 2026 年度汇算清缴完成，注销窗口整体后移半个月',
  },
  {
    id: 'cl9',
    at: '2027-01-06 14:02',
    who: '房某某',
    kind: '交付物',
    phase: '登记与注销',
    from: '（无交付物）',
    to: '清税证明 + 注销登记申请书 + 市监局受理回执',
    reason: '按 AI 建议补齐注销前置材料，缺「清税证明」会被市监局退回',
  },
  {
    id: 'cl10',
    at: '2027-01-08 10:15',
    who: '黄某某',
    kind: '验收标准',
    phase: '交割与移交',
    from: '完成资产交割',
    to: '完成资产交割与档案移交',
    reason: '关厂后会计档案需保存 10 年，档案移交单是律师免责的关键交付物',
  },
]

/** 交付物的一个版本（版本历史用） */
export interface DemoNl1DocVersion {
  version: string
  at: string
  who: string
  pages: number
  /** 这一版改了什么 */
  note: string
}

/** 交付物版本历史（按交付物名对齐 DEMO_NONLIT_PHASES[].deliverables[].name） */
export interface DemoNl1DocHistory {
  doc: string
  /** 当前版本（与阶段表里的页码一致） */
  current: number
  versions: DemoNl1DocVersion[]
}

export const DEMO_NL1_DOC_HISTORY: DemoNl1DocHistory[] = [
  {
    doc: '工商登记与股权结构核实',
    current: 12,
    versions: [
      { version: 'v1', at: '2026-10-28 15:10', who: '房某某', pages: 9, note: '初稿：工商内档导出 + 股权穿透至自然人' },
      { version: 'v2', at: '2026-11-01 11:35', who: '房某某', pages: 11, note: '补 2019 年一次未备案的股权转让（对赌回购触发）' },
      { version: 'v3', at: '2026-11-05 14:20', who: '黄某某', pages: 12, note: '按客户补充材料修订实缴出资时间，定稿归档' },
    ],
  },
  {
    doc: '职工名册与社保清缴明细',
    current: 28,
    versions: [
      { version: 'v1', at: '2026-11-02 09:50', who: '黄某某', pages: 24, note: '初稿：社保系统导出 187 人，含 12 人断缴' },
      { version: 'v2', at: '2026-11-07 09:40', who: '黄某某', pages: 28, note: '补断缴人员的补缴方案与滞纳金测算，客户签收' },
    ],
  },
  {
    doc: '关厂清盘总体方案 v2.0',
    current: 18,
    versions: [
      { version: 'v1.0', at: '2026-11-12 17:45', who: '房某某', pages: 14, note: '初稿：三条清盘路径对比（注销 / 破产 / 转让）' },
      { version: 'v1.5', at: '2026-11-15 10:20', who: '黄某某', pages: 16, note: '按客户意见删去破产路径，加职工安置时间表' },
      { version: 'v2.0', at: '2026-11-18 16:05', who: '房某某', pages: 18, note: '补税务清算节点与预算表，客户董事会书面确认' },
    ],
  },
  {
    doc: '职工安置方案与补偿测算表',
    current: 34,
    versions: [
      { version: 'v0.9', at: '2026-11-24 16:30', who: '黄某某', pages: 21, note: '草案：N+1 补偿口径，未含特殊工种提前退休情形' },
      { version: 'v1.2', at: '2026-11-28 11:30', who: '黄某某', pages: 34, note: '并入经济补偿测算表，补 14 名特殊工种的年限折算' },
      { version: 'v1.3', at: '2027-01-05 14:15', who: '房某某', pages: 34, note: '待客户签字确认（签字页缺失，标记为待补签）' },
    ],
  },
  {
    doc: '债权人会议决议（签字版）',
    current: 6,
    versions: [
      { version: 'v1', at: '2026-12-20 17:05', who: '房某某', pages: 5, note: '会议记录整理稿，未附签字页' },
      { version: 'v2', at: '2026-12-28 15:20', who: '房某某', pages: 6, note: '附 29 户债权人签字页，达表决比例，定稿' },
    ],
  },
]

/** 风险登记表（风险 / 影响 / 应对 / 责任人 / 状态） */
export interface DemoNl1Risk {
  id: string
  risk: string
  /** 高 / 中 / 低 */
  level: '高' | '中' | '低'
  impact: string
  response: string
  owner: string
  due: string
  status: '监控中' | '已闭环' | '待决断'
}

export const DEMO_NL1_RISKS: DemoNl1Risk[] = [
  {
    id: 'rk1',
    risk: '职工安置方案未签，集体停工风险',
    level: '高',
    impact: '187 名职工中尚有 41 人未签安置协议，存在停工与仲裁连锁风险',
    response: '分批座谈 + 一对一测算说明；同步准备劳动仲裁应诉材料',
    owner: '黄某某',
    due: '2027-01-20',
    status: '待决断',
  },
  {
    id: 'rk2',
    risk: '税务清算滞纳金超预算',
    level: '高',
    impact: '12 人社保断缴产生滞纳金约 18 万元，超出方案预算 6 万元',
    response: '申请分期缴纳并主张非主观故意减免；调整方案预算表',
    owner: '房某某',
    due: '2027-02-10',
    status: '监控中',
  },
  {
    id: 'rk3',
    risk: '债权人会议决议被异议',
    level: '中',
    impact: '3 户债权人对清偿顺序有异议，可能申请撤销决议',
    response: '补充担保物权属证明；预留 30 日异议沟通期',
    owner: '房某某',
    due: '2027-02-28',
    status: '监控中',
  },
  {
    id: 'rk4',
    risk: '注销材料被市监局退回',
    level: '中',
    impact: '缺「清税证明」将直接退回，注销周期至少延长 1 个月',
    response: '已在阶段 4 增加清税证明交付物，税务清算完成后立即申领',
    owner: '黄某某',
    due: '2027-03-15',
    status: '监控中',
  },
  {
    id: 'rk5',
    risk: '厂房租赁违约金争议',
    level: '中',
    impact: '提前退租需支付 3 个月租金违约金，出租方主张另有装修损失',
    response: '核对租赁合同装修补偿条款；以评估报告压减装修损失主张',
    owner: '房某某',
    due: '2027-04-30',
    status: '监控中',
  },
  {
    id: 'rk6',
    risk: '设备处置价款低于评估',
    level: '低',
    impact: '二手设备市场下行，处置价可能低于评估值约 8%',
    response: '延长挂牌期 + 引入两家回收商竞价',
    owner: '黄某某',
    due: '2027-05-31',
    status: '已闭环',
  },
  {
    id: 'rk7',
    risk: '会计档案移交缺失',
    level: '低',
    impact: '关厂后会计凭证需保存 10 年，移交缺失可能致律师事后被追责',
    response: '阶段 5 增加档案移交单交付物，逐箱编号签收',
    owner: '黄某某',
    due: '2027-04-30',
    status: '监控中',
  },
]

/** 客户确认记录（哪天确认了什么） */
export interface DemoNl1ClientConfirm {
  id: string
  at: string
  by: string
  /** 确认形式：邮件 / 会议纪要 / 签字页 / 微信 */
  channel: '邮件' | '会议纪要' | '签字页' | '微信'
  what: string
  /** 关联阶段 */
  phase: string
  /** 结论：确认 / 附条件确认 / 不确认 */
  verdict: '确认' | '附条件确认' | '不确认'
}

export const DEMO_NL1_CLIENT_CONFIRMS: DemoNl1ClientConfirm[] = [
  {
    id: 'cc1',
    at: '2026-11-07 18:20',
    by: '某某公司 · 法定代表人 张某某',
    channel: '邮件',
    what: '确认收悉尽职调查四项底稿，同意进入方案设计阶段',
    phase: '尽职调查',
    verdict: '确认',
  },
  {
    id: 'cc2',
    at: '2026-11-18 16:05',
    by: '某某公司 · 董事会决议',
    channel: '签字页',
    what: '董事会决议通过关厂清盘总体方案 v2.0，授权法定代表人签署后续文书',
    phase: '方案设计',
    verdict: '确认',
  },
  {
    id: 'cc3',
    at: '2026-11-25 10:40',
    by: '某某公司 · 人力资源总监 李某某',
    channel: '会议纪要',
    what: '同意职工安置按 N+1 口径执行，但要求对特殊工种给予年限折算',
    phase: '职工安置文书',
    verdict: '附条件确认',
  },
  {
    id: 'cc4',
    at: '2026-12-28 15:20',
    by: '某某公司 · 债权人会议',
    channel: '签字页',
    what: '债权人会议通过清偿方案（29/32 户签署），同意按比例清偿',
    phase: '债权债务与决议',
    verdict: '确认',
  },
  {
    id: 'cc5',
    at: '2027-01-05 14:15',
    by: '某某公司 · 财务负责人 王某某',
    channel: '邮件',
    what: '对职工安置方案 v1.3 提出两处数字疑问（补偿基数是否含年终奖），暂不签',
    phase: '职工安置文书',
    verdict: '不确认',
  },
  {
    id: 'cc6',
    at: '2027-01-08 11:30',
    by: '某某公司 · 法定代表人 张某某',
    channel: '微信',
    what: '同意注销阶段后移半个月，配合 2026 年度汇算清缴完成后再申报',
    phase: '登记与注销',
    verdict: '附条件确认',
  },
]

/** 推进到下一阶段：前置校验项（3 项，其中 1 项未签署） */
export interface DemoNl1GateRule {
  id: string
  /** 校验名 */
  label: string
  /** 校验细节 */
  detail: string
  ok: boolean
  /** 不通过时给的处置建议 */
  fix?: string
}

export const DEMO_NL1_GATE_RULES: DemoNl1GateRule[] = [
  {
    id: 'g1',
    label: '交付物齐全',
    detail: '职工安置文书 2 份、债权债务与决议 1 份，均在合同文件夹内',
    ok: true,
  },
  {
    id: 'g2',
    label: '验收标准满足',
    detail: '「每位职工签署安置协议」未达成：187 人中已签 146 人（78%）',
    ok: false,
    fix: '把未签的 41 人拆成独立跟进清单，先分流集体停工风险再推进',
  },
  {
    id: 'g3',
    label: '客户书面确认',
    detail: '职工安置方案 v1.3 签字页缺失，客户 01-05 邮件明确「暂不签」',
    ok: false,
    fix: '先答复客户的两处数字疑问（补偿基数是否含年终奖），再约签',
  },
]

/* 甘特图的 7 条阶段（与 DEMO_NONLIT_PHASES 同一批阶段，按主线摊到日历上） */
export interface DemoNl1GanttRow {
  /** 对应 DEMO_NONLIT_PHASES.id */
  phaseId: string
  /** 计划工期（天） */
  planDays: number
  /** 实际进度 0-100 */
  progress: number
  /** 实际用掉的天数（延期判断用；未开始为 0） */
  actualDays: number
  /** 谁负责 */
  owner: string
}

export const DEMO_NL1_GANTT: DemoNl1GanttRow[] = [
  { phaseId: 'p1', planDays: 14, progress: 100, actualDays: 13, owner: '房某某' },
  { phaseId: 'p2', planDays: 12, progress: 100, actualDays: 9, owner: '房某某' },
  { phaseId: 'p3', planDays: 56, progress: 62, actualDays: 41, owner: '黄某某' },
  { phaseId: 'p3-1', planDays: 30, progress: 48, actualDays: 41, owner: '黄某某' },
  { phaseId: 'p3-2', planDays: 47, progress: 100, actualDays: 33, owner: '房某某' },
  { phaseId: 'p4', planDays: 74, progress: 0, actualDays: 0, owner: '黄某某' },
  { phaseId: 'p5', planDays: 30, progress: 0, actualDays: 0, owner: '房某某' },
]

/* ═══════════════════════════════════════════════════════════
 * E. 常年法律顾问 · 日常工作台补充数据（NL3）
 *
 * 上面的 C 段只够画一张 8 行的服务事项表，回答不了常法页最该回答的三个问题：
 * 服务期走了多少、每月忙不忙、配额还能撑多久。这里补齐：
 *   · 16 条服务事项（跨 3 个月，带耗时明细与交付物）
 *   · 12 个月的月度工时
 *   · 客户满意度回访记录
 *   · 常法风险提示清单（合同到期 / 用工 / 合规缺口）
 *
 * 金额与工时口径自洽：本月 18.5h / 配额 20h；每条的明细之和 = 该条工时。
 * 全部虚构并脱敏（人名某某、公司某某公司）。
 * ═══════════════════════════════════════════════════════════ */

/** 服务事项类型（tabs 与类型小计都按这个顺序） */
export type DemoNl3ServiceKind = '合同审查' | '咨询' | '出具意见' | '会议出席' | '培训'

/** 一条服务事项的耗时明细 */
export interface DemoNl3Effort {
  label: string
  hours: number
}

/** 一条服务事项（常法工作台用；明细之和等于 hours） */
export interface DemoNl3ServiceItem {
  id: string
  /** yyyy-mm-dd */
  date: string
  kind: DemoNl3ServiceKind
  title: string
  /** 具体做了什么 */
  detail: string
  /** 交付物（文件名，点「补传」时同名上传） */
  deliverable: string
  /** 已交付 / 待补 */
  delivered: boolean
  hours: number
  effort: DemoNl3Effort[]
  status: 'done' | 'doing'
  /** 是否已转成正式意见书 */
  opinionIssued: boolean
}

export const DEMO_NL3_SERVICE_ITEMS: DemoNl3ServiceItem[] = [
  {
    id: 'n3-01',
    date: '2026-11-26',
    kind: '合同审查',
    title: '审阅《设备采购框架协议》并出具修改建议',
    detail: '逐条审阅 42 条，改 11 条：付款节点改为验收后 30 日、质保金从 10% 降到 5%、增加逾期交货违约金封顶',
    deliverable: '设备采购框架协议（修订稿）+ 审查意见 3 页',
    delivered: true,
    hours: 2.5,
    effort: [
      { label: '通读与标记风险条款', hours: 1.0 },
      { label: '出具修改条文', hours: 1.0 },
      { label: '与采购部电话确认商务口径', hours: 0.5 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-02',
    date: '2026-11-24',
    kind: '咨询',
    title: '解答劳动合同到期不续签的经济补偿口径',
    detail: '区分「单位不续签」「员工不续签」「以低于原条件续签」三种情形，给出 N / 无补偿的不同结论',
    deliverable: '口头答复 + 要点备忘 1 页',
    delivered: true,
    hours: 0.8,
    effort: [
      { label: '电话沟通事实', hours: 0.3 },
      { label: '检索本地口径与近期案例', hours: 0.3 },
      { label: '整理要点备忘', hours: 0.2 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-03',
    date: '2026-11-21',
    kind: '出具意见',
    title: '就厂房租赁合同提前解约出具法律意见书',
    detail: '结论：出租方无权单方解约，但未履行 60 日书面通知义务时我方需承担 3 个月租金违约金',
    deliverable: '法律意见书 6 页',
    delivered: true,
    hours: 4.0,
    effort: [
      { label: '查阅合同与往来函件', hours: 1.2 },
      { label: '检索同类裁判观点', hours: 1.3 },
      { label: '撰写并复核意见书', hours: 1.5 },
    ],
    status: 'done',
    opinionIssued: true,
  },
  {
    id: 'n3-04',
    date: '2026-11-19',
    kind: '会议出席',
    title: '列席股东会，就增资扩股程序发表意见',
    detail: '就表决权回避、增资价格公允性与出资期限三项发表意见，会议全程 2 小时 20 分',
    deliverable: '会议纪要签章版',
    delivered: true,
    hours: 3.0,
    effort: [
      { label: '会前材料审阅', hours: 1.0 },
      { label: '现场参会与发表意见', hours: 1.5 },
      { label: '纪要复核', hours: 0.5 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-05',
    date: '2026-11-15',
    kind: '合同审查',
    title: '审阅《员工保密与竞业限制协议》模板',
    detail: '竞业限制补偿标准低于最低工资，改为按月发放月均工资的 30%；限制期限从 3 年压到 2 年',
    deliverable: '协议模板（修订稿）',
    delivered: true,
    hours: 1.5,
    effort: [
      { label: '对照劳动法审查补偿条款', hours: 0.8 },
      { label: '改写模板并批注', hours: 0.7 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-06',
    date: '2026-11-12',
    kind: '培训',
    title: '为销售部门做「合同签署权限」专题培训',
    detail: '讲清谁有权签、盖章与签字的效力、越权签署的追认与免责，现场答疑 7 个问题',
    deliverable: '课件 32 页 + 签到表',
    delivered: true,
    hours: 2.0,
    effort: [
      { label: '编写课件', hours: 1.2 },
      { label: '现场授课与答疑', hours: 0.8 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-07',
    date: '2026-11-08',
    kind: '咨询',
    title: '答复应收账款诉讼时效中断的取证要点',
    detail: '列了对账单签收、催款函 EMS 回执、微信催收记录三类证据的固定方式与效力强弱',
    deliverable: '书面答复 2 页',
    delivered: true,
    hours: 1.2,
    effort: [
      { label: '梳理证据清单', hours: 0.6 },
      { label: '撰写书面答复', hours: 0.6 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-08',
    date: '2026-11-03',
    kind: '出具意见',
    title: '就供应商违约索赔方案出具分析意见',
    detail: '测算可得利益损失区间，建议先发解除通知再主张违约金，避免「解除与违约金并行」被驳',
    deliverable: '分析意见 8 页',
    delivered: true,
    hours: 3.5,
    effort: [
      { label: '核算损失金额', hours: 1.0 },
      { label: '检索违约金与解除并行判例', hours: 1.3 },
      { label: '撰写分析意见', hours: 1.2 },
    ],
    status: 'done',
    opinionIssued: true,
  },
  {
    id: 'n3-09',
    date: '2026-10-28',
    kind: '合同审查',
    title: '审阅《厂房租赁补充协议》第三稿',
    detail: '把「租金随 CPI 无上限调增」改为年度涨幅不超过 5%，并补入押金 30 日返还条款',
    deliverable: '补充协议（终稿）',
    delivered: true,
    hours: 1.8,
    effort: [
      { label: '逐条比对前两稿', hours: 0.8 },
      { label: '出具终稿批注', hours: 1.0 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-10',
    date: '2026-10-24',
    kind: '咨询',
    title: '答复员工工伤停工留薪期工资标准',
    detail: '明确停工留薪期内原工资福利不变，绩效部分按近 12 个月平均计算，不得按最低工资发放',
    deliverable: '口头答复',
    delivered: true,
    hours: 0.6,
    effort: [
      { label: '核对本地工伤规定', hours: 0.3 },
      { label: '答复人事部', hours: 0.3 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-11',
    date: '2026-10-20',
    kind: '出具意见',
    title: '就环保行政处罚陈述申辩出具意见',
    detail: '指出处罚决定未履行听证告知程序，建议在 3 日内提交陈述申辩并申请听证',
    deliverable: '陈述申辩意见书 4 页',
    delivered: true,
    hours: 2.6,
    effort: [
      { label: '查阅处罚决定书与现场笔录', hours: 1.0 },
      { label: '撰写申辩意见', hours: 1.6 },
    ],
    status: 'done',
    opinionIssued: true,
  },
  {
    id: 'n3-12',
    date: '2026-10-16',
    kind: '会议出席',
    title: '参加劳动争议调解会，协助达成和解',
    detail: '当场促成 2 名离职员工签署和解协议，金额从 18 万谈至 11.5 万，一次性了结',
    deliverable: '和解协议 2 份（签字版）',
    delivered: true,
    hours: 2.2,
    effort: [
      { label: '会前方案准备', hours: 0.7 },
      { label: '现场调解', hours: 1.5 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-13',
    date: '2026-10-12',
    kind: '培训',
    title: '新员工合规入职培训（劳动纪律篇）',
    detail: '讲清考勤、保密、礼品与利益冲突四条红线，共 46 人参加',
    deliverable: '课件 18 页',
    delivered: true,
    hours: 1.5,
    effort: [
      { label: '编写课件', hours: 1.0 },
      { label: '现场授课', hours: 0.5 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-14',
    date: '2026-09-28',
    kind: '合同审查',
    title: '审阅《委托加工合同》并出具风险提示',
    detail: '模具归属条款约定不明，改为「委托方出资的模具所有权归委托方」，并加保密与竞业条款',
    deliverable: '风险提示函 2 页',
    delivered: false,
    hours: 2.0,
    effort: [
      { label: '审阅合同全文', hours: 1.1 },
      { label: '撰写风险提示函', hours: 0.9 },
    ],
    status: 'doing',
    opinionIssued: false,
  },
  {
    id: 'n3-15',
    date: '2026-09-22',
    kind: '咨询',
    title: '答复分公司负责人越权担保的效力问题',
    detail: '分公司对外担保需总公司书面授权，善意相对人可主张有效，但已留存授权缺失证据',
    deliverable: '书面答复 1 页',
    delivered: true,
    hours: 1.0,
    effort: [
      { label: '核对担保链条文件', hours: 0.5 },
      { label: '撰写答复', hours: 0.5 },
    ],
    status: 'done',
    opinionIssued: false,
  },
  {
    id: 'n3-16',
    date: '2026-09-15',
    kind: '出具意见',
    title: '就股权代持还原方案出具法律意见',
    detail: '建议以股权转让方式还原，同步处理个税申报与工商变更，避免被认定为抽逃出资',
    deliverable: '法律意见书 5 页',
    delivered: false,
    hours: 3.2,
    effort: [
      { label: '梳理代持协议与出资凭证', hours: 1.2 },
      { label: '设计还原路径', hours: 1.0 },
      { label: '撰写意见书', hours: 1.0 },
    ],
    status: 'doing',
    opinionIssued: false,
  },
]

/** 月度工时（12 个月，服务期内逐月累计；11 月 18.5h / 10 月 19.2h 与事项明细对得上） */
export interface DemoNl3MonthHours {
  /** yyyy-mm */
  month: string
  hours: number
}

export const DEMO_NL3_MONTHLY_HOURS: DemoNl3MonthHours[] = [
  { month: '2026-03', hours: 9.5 },
  { month: '2026-04', hours: 14.0 },
  { month: '2026-05', hours: 11.2 },
  { month: '2026-06', hours: 16.5 },
  { month: '2026-07', hours: 12.8 },
  { month: '2026-08', hours: 10.0 },
  { month: '2026-09', hours: 6.2 },
  { month: '2026-10', hours: 8.7 },
  { month: '2026-11', hours: 18.5 },
  { month: '2026-12', hours: 8.0 },
  { month: '2027-01', hours: 6.5 },
  { month: '2027-02', hours: 4.0 },
]

/** 服务期与配额口径（比 C 段的 DEMO_SERVICE_STATS 更完整：加上起止日期与报价） */
export const DEMO_NL3_SERVICE_STATS = {
  from: '2026-03-22',
  to: '2027-03-21',
  contractDays: 365,
  usedDays: 96,
  remainDays: 269,
  totalHours: 18.5,
  monthlyQuota: 20,
  items: 8,
  /** 年度合同金额（元）—— 续签建议的报价基数 */
  baseFee: 96000,
}

/** 配额预警阈值（%）：达到 warn 标黄，达到 exceed 标红 */
export const DEMO_NL3_QUOTA_POLICY = {
  warnPct: 90,
  exceedPct: 100,
}

/** 客户满意度回访记录（每月一次电话回访） */
export interface DemoNl3Satisfaction {
  id: string
  date: string
  /** 满意度分（5 分制） */
  score: number
  /** 回访对象（脱敏） */
  interviewer: string
  channel: '电话' | '微信' | '现场'
  feedback: string
}

export const DEMO_NL3_SATISFACTION: DemoNl3Satisfaction[] = [
  {
    id: 'sat-1',
    date: '2026-11-27',
    score: 5,
    interviewer: '分管副总 陈某某',
    channel: '电话',
    feedback: '设备采购协议的修改建议很具体，采购部直接拿去用了；希望以后合同都能当天回',
  },
  {
    id: 'sat-2',
    date: '2026-10-30',
    score: 4,
    interviewer: '人事总监 李某某',
    channel: '微信',
    feedback: '工伤与补偿口径答复清楚，但希望多给两页纸面材料，方便给车间主管看',
  },
  {
    id: 'sat-3',
    date: '2026-09-29',
    score: 4,
    interviewer: '财务经理 周某某',
    channel: '现场',
    feedback: '环保处罚申辩帮了大忙，罚款减半；建议提前把类似风险列个清单给我们自查',
  },
  {
    id: 'sat-4',
    date: '2026-08-28',
    score: 5,
    interviewer: '分管副总 陈某某',
    channel: '电话',
    feedback: '调解会当场谈下来，省了六万多；希望明年把培训增加到每季度一次',
  },
  {
    id: 'sat-5',
    date: '2026-07-30',
    score: 3,
    interviewer: '人事总监 李某某',
    channel: '电话',
    feedback: '问的问题回得有点慢，当天没等到回复；其他都满意',
  },
]

/** 常法风险提示清单（合同到期 / 用工风险 / 合规缺口三类） */
export interface DemoNl3Risk {
  id: string
  category: '合同到期' | '用工风险' | '合规缺口'
  title: string
  level: '高' | '中' | '低'
  /** 到期日 / 触发日（yyyy-mm-dd；合规缺口用「下次检查日」） */
  due: string
  impact: string
  /** 建议动作 */
  action: string
  closed: boolean
}

export const DEMO_NL3_RISKS: DemoNl3Risk[] = [
  {
    id: 'n3rk-1',
    category: '合同到期',
    title: '安全生产责任险保单 12 月 31 日到期',
    level: '高',
    due: '2026-12-31',
    impact: '保单断保期间发生事故，全部赔偿由公司自行承担，且影响投标资格',
    action: '本周内比价续保，续保后把保单号回填台账',
    closed: false,
  },
  {
    id: 'n3rk-2',
    category: '合规缺口',
    title: '危废转移台账缺 8 月两笔联单',
    level: '高',
    due: '2026-12-10',
    impact: '环保部门现场检查时可认定为台账不全，处以罚款并责令整改',
    action: '联系处置单位补开联单，补齐扫描件归档',
    closed: false,
  },
  {
    id: 'n3rk-3',
    category: '用工风险',
    title: '12 名员工劳动合同将于 2027-01 到期',
    level: '中',
    due: '2027-01-15',
    impact: '到期不续签需支付经济补偿；连续两次固定期限后再签必须签无固定期限',
    action: '12 月初启动续签意愿摸底，区分核心岗位与临时岗位',
    closed: false,
  },
  {
    id: 'n3rk-4',
    category: '合同到期',
    title: '厂房租赁合同 2027-03-31 到期（与常法服务期同步）',
    level: '中',
    due: '2027-03-31',
    impact: '出租方可能上调租金；提前解约条款对我方不利',
    action: '续签常法合同时一并启动租赁续约谈判',
    closed: false,
  },
  {
    id: 'n3rk-5',
    category: '合规缺口',
    title: '公司章程仍是 2019 年版本，未反映两次增资',
    level: '低',
    due: '2027-02-28',
    impact: '工商登记的股东出资与章程不一致，影响后续股权变更与融资尽调',
    action: '按最新增资结果修订章程并办理备案',
    closed: false,
  },
  {
    id: 'n3rk-6',
    category: '用工风险',
    title: '竞业限制补偿标准低于法定下限',
    level: '中',
    due: '2026-11-15',
    impact: '补偿过低可能导致竞业限制条款不被支持，核心岗位人员离职后难以限制',
    action: '按新模板重签 6 名核心岗位的竞业协议',
    closed: false,
  },
]
