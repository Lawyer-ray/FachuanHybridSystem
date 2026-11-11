/**
 * 非诉线 · 演示数据 · B. 跨境合同审查（泰国工厂租赁）· 双语文档视图的补充数据
 * （**仅用于录屏演示**，不参与真实业务）
 *
 * 与 `nl2-crossborder.ts` 共用 DEMO_TH_CONTRACT_REVISIONS（那 5 条修订是审查结论），
 * 这里补的是「支撑结论的材料」：合同正文双语对照、每条修订对应的一条外国法原文、
 * 审查会话进度、对方律师意见。
 *
 * 全部虚构：当事方用「某某公司 / 某某工业园」，条文英文按泰国《民商法典》
 * 通行英译的表述风格重写，条款号与审查结论段的引用一致。
 */

import { DEMO_TH_CONTRACT_REVISIONS, type DemoContractRevision } from './nl2-crossborder'

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
