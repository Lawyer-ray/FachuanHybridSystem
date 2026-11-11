/**
 * 非诉线 C · 常年顾问工作台：服务配额 + 事项流 + 回访 + 风险 + 续签。
 *
 * 常法合同卖的是「一年 20 小时/月」，所以这一屏要回答的是「服务期走了多少、
 * 每月忙不忙、配额还能撑多久、要不要续签」。卡片全部落在 nonlit/advisor/ 下，
 * 这里只做汇总条与编排（单卡实现见各文件头注释）。
 *
 * 从 `nonlit-workbench.tsx` 按「一屏一个工作台」拆出，只搬移不改行为。
 */

import { toast } from 'sonner'

import {
  DEMO_NL3_RISKS,
  DEMO_NL3_SATISFACTION,
  DEMO_NL3_SERVICE_ITEMS,
  DEMO_NL3_SERVICE_STATS,
} from './demo-nonlit'
import { NonLitActionCard } from './nonlit-action-card'
import { SectionHead, StatCell, StatStrip } from './nonlit/special/special-stat'
import { AdvisorFeedbackCard } from './nonlit/advisor/advisor-feedback-card'
import { AdvisorQuotaCard } from './nonlit/advisor/advisor-quota-card'
import { AdvisorRenewCard } from './nonlit/advisor/advisor-renew-card'
import { AdvisorRiskCard } from './nonlit/advisor/advisor-risk-card'
import { AdvisorServiceList } from './nonlit/advisor/advisor-service-list'
import { quotaTone, quotaUsage } from './nonlit/advisor/advisor-domain'
import { useNonLitAction } from './use-nonlit-action'
import { Card } from './ui'

export function AdvisorWorkbench() {
  /** 生成月度服务报告 */
  const report = useNonLitAction(
    [
      { text: '读取本月服务事项（8 条）', ms: 600 },
      { text: '按类型汇总：合同审查 2 / 咨询 2 / 出具意见 2 / 会议 2 / 培训 2', ms: 900 },
      {
        text: '统计服务工时',
        ms: 700,
        retry: { times: 1, delay: 800, reason: '一条事项缺失开始时间，按结束时间倒推' },
      },
      { text: '生成服务报告正文', ms: 1000 },
      { text: '附上事项明细表与客户回访记录', ms: 600 },
    ],
    '月度服务报告已生成：8 项事项、18.5 小时，配额 20 小时用掉 92%',
  )

  /** 归档服务事项 */
  const archiveItems = useNonLitAction(
    [
      { text: '校验 8 条事项的交付物是否齐全', ms: 800, parallel: ['合同审查 2', '出具意见 2', '其余 4'] },
      { text: '按月份分组归档', ms: 600 },
      {
        text: '写入服务台账',
        ms: 700,
        retry: { times: 1, delay: 900, reason: '台账接口限流' },
      },
      { text: '同步到合同文件夹', ms: 500 },
    ],
    '8 条服务事项已归档，明细写入服务台账并同步合同文件夹',
  )

  const s = DEMO_NL3_SERVICE_STATS
  const quotaPct = quotaUsage(s.totalHours, s.monthlyQuota)
  const pendingDeliver = DEMO_NL3_SERVICE_ITEMS.filter((i) => !i.delivered).length
  const closedRisks = DEMO_NL3_RISKS.filter((r) => r.closed).length
  const avgScore = (
    DEMO_NL3_SATISFACTION.reduce((sum, r) => sum + r.score, 0) / DEMO_NL3_SATISFACTION.length
  ).toFixed(1)

  return (
    <div className="flex flex-col gap-3">
      <Card className="px-[18px] py-[15px]">
        <SectionHead title="顾问工作台" hint="服务配额 · 事项流 · 回访 · 风险 · 续签" />
        <StatStrip className="mt-3 grid-cols-2 sm:grid-cols-6">
          <StatCell label="合同剩余" value={`${s.remainDays} 天`} tone={s.remainDays < 90 ? 'yellow' : 'green'} />
          <StatCell label="服务期已用" value={`${s.usedDays}/${s.contractDays} 天`} />
          <StatCell label="本月事项" value={`${s.items} 项`} />
          <StatCell label="本月工时" value={`${s.totalHours}h`} />
          <StatCell label="配额使用" value={`${quotaPct}%`} tone={quotaTone(quotaPct)} />
          <StatCell label="客户评分" value={`${avgScore} 分`} tone="blue" />
        </StatStrip>

        <div className="mt-3.5 flex flex-col gap-2.5">
          <NonLitActionCard
            title="生成本月服务报告"
            desc="按服务事项汇总工时、交付物与要点，生成可直接发给客户的月度报告。配额快用完时会提示续签。"
            actionLabel="生成月报"
            hint="8 项事项 · 约 4 秒"
            state={report}
          />
          <NonLitActionCard
            title="归档服务事项"
            desc="校验每条事项的交付物是否齐全，按月份归档并写入服务台账。缺交付物的会被挑出来。"
            actionLabel="归档事项"
            hint="8 条 · 约 3 秒"
            state={archiveItems}
          />
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-muted-foreground">
          <span>待补交付物 {pendingDeliver} 项</span>
          <span>风险已闭环 {closedRisks}/{DEMO_NL3_RISKS.length} 项</span>
          <span>回访 {DEMO_NL3_SATISFACTION.length} 次</span>
          <span className="ml-auto">数据口径：本月工时含已完成事项，进行中的按计划工时计</span>
        </div>
      </Card>

      <AdvisorQuotaCard />

      <AdvisorRenewCard />

      <AdvisorServiceList
        items={DEMO_NL3_SERVICE_ITEMS}
        onDeliver={(it) =>
          toast.success('已补传交付物', { description: `${it.title}：${it.deliverable}` })
        }
        onOpinion={(it) =>
          toast.success('已转成正式意见书', { description: `按《${it.title}》生成意见书草稿，落到合同文件夹` })
        }
      />

      <AdvisorRiskCard />

      <AdvisorFeedbackCard />
    </div>
  )
}
