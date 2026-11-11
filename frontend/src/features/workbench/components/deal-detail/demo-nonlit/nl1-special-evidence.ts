/**
 * 非诉线 · 演示数据 · A. 专项服务（关厂清盘）· 过程证据
 * （**仅用于录屏演示**，不参与真实业务）
 *
 * `nl1-special.ts` 是「计划」，这里是**过程证据**：谁在什么时候动了哪个阶段、
 * 每份交付物改过几版、哪些风险还挂着、客户哪天点了头。律师点开任意一行
 * 都能看到依据，而不是一句「已完成」。
 *
 * 阶段名与 `DEMO_NONLIT_PHASES[].name` 对齐，交付物名与
 * `DEMO_NONLIT_PHASES[].deliverables[].name` 对齐，阶段 id 与 `.id` 对齐；
 * 改 A 段的阶段或交付物名时，这里要同步。
 *
 * 全部虚构并脱敏：经办人一律「黄某某 / 房某某」，客户与债权人用「某某公司」。
 */

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
