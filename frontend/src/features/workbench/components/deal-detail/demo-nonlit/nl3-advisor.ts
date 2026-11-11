/**
 * 非诉线 · 演示数据 · C. 常年法律顾问（**仅用于录屏演示**，不参与真实业务）
 *
 * 原名 `demo-nonlit.ts` 的 C 段与 E 段（NL3）合并到此：
 *   · C 段是 8 行服务事项表 + 常法统计（非诉页静态展示）
 *   · E 段是常法工作台的补充数据（16 条事项含耗时明细 / 12 个月工时 / 满意度回访 / 风险清单）
 * 两段都以「一个月 18.5h、配额 20h」为同一口径，拆开必然漂移，故同文件维护。
 *
 * 约定：只出现在展示位置、不参与判断逻辑；人名机构一律脱敏；工时明细之和 = 该条 hours。
 */

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
