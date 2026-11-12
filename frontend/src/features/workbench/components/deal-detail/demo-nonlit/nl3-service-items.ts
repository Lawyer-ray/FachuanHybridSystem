/**
 * 非诉线 · 演示数据 · C. 常年法律顾问 · 服务事项明细（NL3）
 * （**仅用于录屏演示**，不参与真实业务）
 *
 * 16 条服务事项，跨 3 个月，带耗时明细与交付物。`nl3-advisor.ts` 的 8 行表
 * 只够画一屏，回答不了「具体做了什么、时间花在哪」；这里是能展开的那一份。
 *
 * 口径：每条的 `effort[].hours` 之和 = 该条 `hours`；本月合计 18.5h 与
 * `nl3-advisor-stats.ts` 的月度工时对得上。全部虚构并脱敏。
 */

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
