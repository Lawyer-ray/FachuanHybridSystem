/**
 * 非诉线 · 演示数据 · C. 常年法律顾问 · 工时 / 满意度 / 风险（NL3）
 * （**仅用于录屏演示**，不参与真实业务）
 *
 * 服务期用量口径（12 个月工时 + 服务期与配额 + 配额预警阈值）、
 * 月度满意度回访、常法风险提示清单（合同到期 / 用工 / 合规缺口）。
 *
 * 口径：本月 18.5h / 配额 20h，与 `nl3-service-items.ts` 的 16 条事项合计一致。
 * 全部虚构并脱敏（人名某某、公司某某公司）。
 */

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
