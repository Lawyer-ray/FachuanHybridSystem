/**
 * 常年顾问 · 工作台纯逻辑
 *
 * 常法页要回答三个数字问题：**服务期走了多少**、**每月忙不忙**、**配额还能撑多久**。
 * 这三件事的计算口径都放在这里，组件只负责画——口径可单测，录屏时数值也不会
 * 因为谁把百分比四舍五入写错而前后打架。
 *
 * 数据来自 `demo-nonlit.ts` 的 `DEMO_NL3_*`（演示数据，不进真实业务链路）。
 */

import {
  DEMO_NL3_QUOTA_POLICY,
  DEMO_NL3_RISKS,
  DEMO_NL3_SERVICE_STATS,
  type DemoNl3ServiceItem,
  type DemoNl3ServiceKind,
} from '../../demo-nonlit'

/** 配额的用法口径：本月工时 / 每月限额，按百分比取整 */
export function quotaUsage(usedHours: number, monthlyQuota: number): number {
  if (!(monthlyQuota > 0)) return 0
  return Math.round((usedHours / monthlyQuota) * 100)
}

/** 配额语气：≥ 超额线红、≥ 预警线黄、其余绿 */
export function quotaTone(usagePct: number): 'green' | 'yellow' | 'red' {
  if (usagePct >= DEMO_NL3_QUOTA_POLICY.exceedPct) return 'red'
  if (usagePct >= DEMO_NL3_QUOTA_POLICY.warnPct) return 'yellow'
  return 'green'
}

/** 服务期进度（已用天数 / 合同天数），0–1 */
export function serviceTermProgress(): number {
  const s = DEMO_NL3_SERVICE_STATS
  if (!(s.contractDays > 0)) return 0
  return Math.min(1, s.usedDays / s.contractDays)
}

/** 月度工时柱：高度取「本月 / 峰值」，配额线按同一比例画，超配额的月标黄 */
export interface MonthBar {
  month: string
  /** 显示用月份（「11月」） */
  label: string
  hours: number
  /** 柱高比例 0–1 */
  ratio: number
  /** 是否超过每月限额 */
  over: boolean
}

export function monthBars(hours: Array<{ month: string; hours: number }>, monthlyQuota: number): MonthBar[] {
  const peak = hours.reduce((m, x) => Math.max(m, x.hours), monthlyQuota)
  if (!(peak > 0)) return []
  return hours.map((x) => ({
    month: x.month,
    label: `${Number(x.month.slice(5))}月`,
    hours: x.hours,
    // 最矮也给 2%，否则「这个月没记工时」和「柱被裁掉」分不清
    ratio: Math.max(0.02, x.hours / peak),
    over: x.hours > monthlyQuota,
  }))
}

/** 配额线在同一坐标系里的高度（与 monthBars 的 peak 同源） */
export function quotaLineRatio(hours: Array<{ hours: number }>, monthlyQuota: number): number {
  const peak = hours.reduce((m, x) => Math.max(m, x.hours), monthlyQuota)
  return peak > 0 ? monthlyQuota / peak : 0
}

/** 一条事项展开后的耗时明细 */
export interface ItemEffortRow {
  label: string
  hours: number
}

/** 事项的耗时明细：明细之和应当等于事项工时，不等就按「其他」补齐差额 */
export function effortRows(item: DemoNl3ServiceItem): ItemEffortRow[] {
  const rows = item.effort.map((e) => ({ label: e.label, hours: e.hours }))
  const sum = rows.reduce((s, r) => s + r.hours, 0)
  const diff = Math.round((item.hours - sum) * 100) / 100
  if (diff > 0) rows.push({ label: '沟通与归档', hours: diff })
  return rows
}

/** 类型分组 tab：全部 + 每个类型（带条数与工时小计） */
export interface KindTab {
  key: 'all' | DemoNl3ServiceKind
  label: string
  count: number
  hours: number
}

export function kindTabs(items: DemoNl3ServiceItem[]): KindTab[] {
  const order: DemoNl3ServiceKind[] = ['合同审查', '咨询', '出具意见', '会议出席', '培训']
  const all: KindTab = {
    key: 'all',
    label: '全部',
    count: items.length,
    hours: round1(items.reduce((s, i) => s + i.hours, 0)),
  }
  const rest = order
    .map((kind) => {
      const hit = items.filter((i) => i.kind === kind)
      return { key: kind, label: kind, count: hit.length, hours: round1(hit.reduce((s, i) => s + i.hours, 0)) }
    })
    .filter((t) => t.count > 0)
  return [all, ...rest]
}

/** 按 tab 过滤事项（'all' 不过滤） */
export function filterItems(items: DemoNl3ServiceItem[], key: KindTab['key']): DemoNl3ServiceItem[] {
  return key === 'all' ? items : items.filter((i) => i.kind === key)
}

/** 按月份分组（前端展示用，键为 yyyy-mm，组内保持原顺序） */
export function groupByMonth(items: DemoNl3ServiceItem[]): Array<{ month: string; items: DemoNl3ServiceItem[] }> {
  const out: Array<{ month: string; items: DemoNl3ServiceItem[] }> = []
  for (const it of items) {
    const month = it.date.slice(0, 7)
    const last = out.at(-1)
    if (last && last.month === month) last.items.push(it)
    else out.push({ month, items: [it] })
  }
  return out
}

/* ═══════════════════════════════════════════════════════════
 * 续签提醒：合同剩余天数 → 工时使用率 → 续签建议
 * ═══════════════════════════════════════════════════════════ */

export type RenewVerdict = 'renew' | 'renegotiate' | 'hold'

export interface RenewSignal {
  key: string
  label: string
  /** 读数（「140 天」「92%」） */
  value: string
  tone: 'green' | 'yellow' | 'red' | 'neutral'
  /** 判断依据 */
  reason: string
}

export interface RenewSuggestion {
  verdict: RenewVerdict
  title: string
  /** 一句话结论 */
  headline: string
  signals: RenewSignal[]
  /** 建议的动作 */
  actions: string[]
  /** 建议报价（原额 × 系数，取整到百元） */
  suggestedFee: number
}

/** 风险清单里未闭环的高等级条数（续签建议的输入之一） */
export function openHighRiskCount(): number {
  return DEMO_NL3_RISKS.filter((r) => r.level === '高' && !r.closed).length
}

/**
 * 续签建议的生成规则（演示口径，但规则本身是真的）：
 *
 * 1. 剩余天数 ≤ 90 天 → 进入续签窗口；≤ 30 天 → 紧急
 * 2. 工时使用率 ≥ 90% → 说明月配额偏紧，新合同应上调配额或改按小时计费
 * 3. 工时使用率 < 60% 且尚未进入续签窗口 → 用量不足，续签时不宜涨价
 * 4. 风险提示里有「高」级未闭环 → 续签前先补合规整改条款
 */
export function buildRenewSuggestion(input?: {
  remainDays?: number
  usedHours?: number
  monthlyQuota?: number
  baseFee?: number
  highRiskOpen?: number
}): RenewSuggestion {
  const s = DEMO_NL3_SERVICE_STATS
  const remainDays = input?.remainDays ?? s.remainDays
  const usedHours = input?.usedHours ?? s.totalHours
  const monthlyQuota = input?.monthlyQuota ?? s.monthlyQuota
  const baseFee = input?.baseFee ?? s.baseFee
  const highRiskOpen = input?.highRiskOpen ?? openHighRiskCount()
  const usage = quotaUsage(usedHours, monthlyQuota)

  const inWindow = remainDays <= 90
  const urgent = remainDays <= 30
  const tight = usage >= DEMO_NL3_QUOTA_POLICY.warnPct
  // 「用量不足」只在**还没进续签窗口**时才成为暂缓的理由：一旦到期在即，
  // 用量低只是谈配额的筹码，不能拿来当「不续签」的结论
  const idle = usage < 60 && !inWindow

  const verdict: RenewVerdict = idle ? 'hold' : tight || highRiskOpen > 0 ? 'renegotiate' : 'renew'

  const signals: RenewSignal[] = [
    {
      key: 'term',
      label: '合同剩余天数',
      value: `${remainDays} 天`,
      tone: urgent ? 'red' : inWindow ? 'yellow' : 'green',
      reason: urgent ? '已进入到期前 30 天，须本周发起续签' : inWindow ? '已进入到期前 90 天续签窗口' : '尚未进入续签窗口，可继续观察',
    },
    {
      key: 'quota',
      label: '工时使用率',
      value: `${usage}%`,
      tone: quotaTone(usage),
      reason: tight
        ? `本月 ${usedHours}h 已达配额 ${monthlyQuota}h 的 ${usage}%（预警线 ${DEMO_NL3_QUOTA_POLICY.warnPct}%）`
        : `本月 ${usedHours}h，配额 ${monthlyQuota}h 尚有余量`,
    },
    {
      key: 'risk',
      label: '未闭环风险',
      value: `${highRiskOpen} 项`,
      tone: highRiskOpen > 0 ? 'yellow' : 'green',
      reason: highRiskOpen > 0 ? '存在高等级合规缺口，续签前应写入整改承诺' : '风险清单已全部闭环',
    },
    {
      key: 'demand',
      label: '用量趋势',
      value: idle ? '偏低' : tight ? '偏高' : '平稳',
      tone: idle ? 'neutral' : tight ? 'yellow' : 'green',
      reason: idle
        ? '用量不足六成，客户可能压价'
        : tight
          ? '工时接近每月上限，说明需求量在涨'
          : '工时使用率处在正常区间',
    },
  ]

  const factor = verdict === 'hold' ? 1 : tight ? 1.2 : 1.1
  const suggestedFee = Math.round((baseFee * factor) / 100) * 100

  const actions: string[] =
    verdict === 'hold'
      ? ['先与客户复盘用量，把「为什么没用满」说清楚', '提议降配到 15h/月或改为按小时计费', '续签窗口打开后再发续签函']
      : verdict === 'renegotiate'
        ? [
            `按 ${factor.toFixed(1)} 系数起草续签报价（配额上调到 ${Math.round(monthlyQuota * 1.5)}h/月）`,
            '把未闭环的合规整改写成续签前的承诺事项',
            '提前 60 天发出续签函，留出谈价时间',
          ]
        : ['按原价起草续签函，配额维持 20h/月', '附本年度服务报告作为续签依据', '到期前 45 天发出续签函']

  const headline =
    verdict === 'hold'
      ? `用量不足六成，建议先复盘再谈续签（报价不变 ${baseFee.toLocaleString('zh-CN')} 元）`
      : verdict === 'renegotiate'
        ? `配额吃紧（${usage}%）+ ${highRiskOpen} 项高风险未闭环，建议上调配额后按 ${suggestedFee.toLocaleString('zh-CN')} 元续签`
        : `用量与剩余天数都正常，按原价 ${baseFee.toLocaleString('zh-CN')} 元续签即可`

  return {
    verdict,
    title: verdict === 'hold' ? '建议暂缓续签' : verdict === 'renegotiate' ? '建议调价续签' : '建议原价续签',
    headline,
    signals,
    actions,
    suggestedFee,
  }
}

/** 续签动作的流水（交给 useNonLitAction 播：进度条 + 日志 + 重试 + 中途确认） */
export function renewSteps() {
  const s = DEMO_NL3_SERVICE_STATS
  return [
    {
      text: `读取合同期限：${s.from} → ${s.to}`,
      ms: 500,
      parallel: ['合同要素', '服务范围', '收费条款'],
    },
    { text: `剩余天数检测：${s.remainDays} 天，进入续签窗口`, ms: 700 },
    {
      text: '工时使用率检测',
      ms: 800,
      retry: { times: 1, delay: 800, reason: '工时台账接口超时，重试中' },
    },
    { text: `汇总风险清单：未闭环高等级 ${openHighRiskCount()} 项`, ms: 600 },
    {
      text: '生成续签建议',
      ms: 700,
      confirm: `检测到本月工时已达配额的 ${quotaUsage(s.totalHours, s.monthlyQuota)}%，且 ${openHighRiskCount()} 项高等级合规缺口未闭环。建议调价续签，是否采用该方案？`,
    },
    { text: '续签函草稿已写入合同文件夹', ms: 500 },
  ]
}

const round1 = (n: number) => Math.round(n * 10) / 10
