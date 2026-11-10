/**
 * 非诉线 · 工作台区块（对标诉讼线的六阶段交互）
 *
 * ═══ 为什么要加 ═══
 * 非诉页原来只有静态的阶段表 / 服务事项流，律师点进去**没有任何可操作的东西**；
 * 录屏时最能说明问题的「点一下、看机器跑」完全缺失，观感上与诉讼线是两个产品。
 *
 * 三个非诉场景各配一组可执行动作：
 *   · 专项服务  → 设计阶段 / 从 0 起草 / 校验交付物
 *   · 跨境审查  → 逐条审查 / 泰文法条核验（三道规则闸 + 判断层）
 *   · 常年顾问  → 配额可视化 / 可展开事项流 / 风险清单 / 续签检测
 *
 * 交互范式与诉讼线完全一致：进度条 + 逐步日志 + 失败重试 + 中途要人确认。
 */

import { useState } from 'react'
import { FileText, GraduationCap, Scale, Sparkles } from 'lucide-react'

import { toast } from 'sonner'

import { cn } from '@/lib/utils'

import {
  DEMO_DRAFT_SUGGESTIONS,
  DEMO_LAW_GATES,
  DEMO_NL1_RISKS,
  DEMO_NL3_RISKS,
  DEMO_NL3_SATISFACTION,
  DEMO_NL3_SERVICE_ITEMS,
  DEMO_NL3_SERVICE_STATS,
  DEMO_NONLIT_PHASES,
  DEMO_PHASE_TEMPLATES,
  DEMO_TH_CONTRACT_REVISIONS,
  DEMO_VERIFY_LOG,
} from './demo-nonlit'
import { NonLitActionCard } from './nonlit-action-card'
import { ForeignLawVerifyCard } from './nonlit/crossborder/ForeignLawVerifyCard'
import { AdvisorFeedbackCard } from './nonlit/advisor/advisor-feedback-card'
import { AdvisorQuotaCard } from './nonlit/advisor/advisor-quota-card'
import { AdvisorRenewCard } from './nonlit/advisor/advisor-renew-card'
import { AdvisorRiskCard } from './nonlit/advisor/advisor-risk-card'
import { AdvisorServiceList } from './nonlit/advisor/advisor-service-list'
import { quotaTone, quotaUsage } from './nonlit/advisor/advisor-domain'
import { SpecialGanttCard } from './nonlit/special/special-gantt-card'
import { SpecialPhaseBoard } from './nonlit/special/special-phase-board'
import { SpecialConfirmCard, SpecialRiskCard } from './nonlit/special/special-risk-card'
import { useNonLitAction } from './use-nonlit-action'
import { CrossBorderViews } from './nonlit/crossborder/CrossBorderViews'
import { Card } from './ui'

/* ═══════════════════════════════════════════════════════════
 * 公共小件
 * ═══════════════════════════════════════════════════════════ */

function SectionHead({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline gap-2">
      <h3 className="text-[13px] font-[620]">{title}</h3>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
      {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
    </div>
  )
}

function StatStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('grid divide-x divide-border-light overflow-hidden rounded-[10px] border border-border-light bg-secondary/30', className)}>
      {children}
    </div>
  )
}

function StatCell({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'green' | 'red' | 'yellow' | 'blue' }) {
  const map = {
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
    blue: 'text-status-blue',
  } as const
  return (
    <div className="px-3 py-2 text-center">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-[14px] font-[620] tabular-nums', tone ? map[tone] : 'text-foreground')}>{value}</div>
    </div>
  )
}

/** 状态胶囊（workbench 的 Pill 不带 tone，这里补一个带语气的） */
function Pill({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue'
}) {
  const map = {
    neutral: 'border-border bg-secondary text-secondary-foreground',
    green: 'border-status-green/40 bg-status-green-bg text-status-green',
    red: 'border-status-red/40 bg-status-red-bg text-status-red',
    yellow: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
    blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  } as const
  return (
    <span className={cn('rounded-[6px] border px-2 text-[11px] leading-[1.6] font-semibold whitespace-nowrap', map[tone])}>
      {children}
    </span>
  )
}

function Inset({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('rounded-[9px] border border-border-light bg-background px-3 py-2', className)}>{children}</div>
}

/* ═══════════════════════════════════════════════════════════
 * A. 专项服务：阶段设计与交付物校验
 * ═══════════════════════════════════════════════════════════ */

export function SpecialPhaseWorkbench() {
  /** 甘特图点条 → 直接打开该阶段的抽屉（用递增计数驱动，点同一条也能再开） */
  const [focus, setFocus] = useState<{ phaseId: string; n: number } | null>(null)

  /** 设计阶段：AI 根据项目信息生成阶段划分 */
  const design = useNonLitAction(
    [
      { text: '读取项目类型与合同约定', ms: 500, parallel: ['合同期限', '服务范围', '验收条件'] },
      { text: '匹配「关厂清盘」阶段模板（7 阶段）', ms: 900 },
      { text: '按项目周期把阶段摊到日历上', ms: 700 },
      {
        text: '写入阶段树',
        ms: 800,
        retry: { times: 1, delay: 1100, reason: '阶段接口超时，重试中' },
      },
      { text: '生成对应合同文件夹目录', ms: 600 },
      {
        text: '检查阶段完整性',
        ms: 500,
        confirm: '检测到「税务清算」未单独成阶段。关厂项目通常需要单独走税务注销，是否插入该阶段？',
      },
      { text: '阶段设计与目录同步完成', ms: 400 },
    ],
    '7 个阶段已设计并写入，合同文件夹目录同步生成',
  )

  /** 从 0 起草：给出改进建议 */
  const draft = useNonLitAction(
    [
      { text: '读取当前阶段树（7 节点）', ms: 500 },
      { text: '比对同类关厂项目（12 个）的阶段划分', ms: 1200, parallel: ['样本 1-4', '样本 5-8', '样本 9-12'] },
      { text: '识别差异点', ms: 800 },
      { text: '生成 3 条改进建议', ms: 700 },
    ],
    '生成 3 条建议：补税务清算阶段、拆职工安置子阶段、增加清税证明交付物',
  )

  /** 校验交付物 */
  const verifyDocs = useNonLitAction(
    [
      { text: '扫描各阶段交付物（3 份已上传）', ms: 700 },
      { text: '核对阶段 1 尽职调查：2 份齐全', ms: 600 },
      { text: '核对阶段 2 方案设计：1 份齐全', ms: 500 },
      {
        text: '核对阶段 3 文件起草',
        ms: 900,
        retry: { times: 2, delay: 900, reason: '职工安置方案页数解析失败' },
      },
      {
        text: '发现阶段 3 缺「经济补偿测算表」签字版',
        ms: 600,
        confirm: '职工安置方案已上传但缺签字版测算表。按验收标准，未签署的交付物不能标记完成。是否标记为「待补签」？',
      },
      { text: '校验完成', ms: 400 },
    ],
    '3 个阶段通过验收，1 项待补签（经济补偿测算表）',
  )

  /** 点风险登记表的「重新评估」：走一段可看的过程，而不是弹个 toast 了事 */
  const riskAssess = useNonLitAction(
    [
      { text: '读取风险台账（7 条）与应对措施', ms: 500 },
      { text: '比对交付物与客户确认记录的当前状态', ms: 800, parallel: ['职工安置', '税务清算', '债权人决议'] },
      { text: '重算风险等级与到期日', ms: 700 },
      {
        text: '发现 1 条风险等级上升（职工安置未签）',
        ms: 700,
        confirm: '「职工安置方案未签」签署率停在 78%，已连续两周未上升。是否升级为「待决断」并提示客户？',
      },
      { text: '风险等级已更新', ms: 500 },
    ],
    '7 条风险复评完成：1 条升级为待决断，2 条维持监控',
  )

  const doneCount = DEMO_NONLIT_PHASES.filter((p) => p.status === 'done').length
  const doingCount = DEMO_NONLIT_PHASES.filter((p) => p.status === 'doing').length
  const docCount = DEMO_NONLIT_PHASES.reduce((n, p) => n + p.deliverables.length, 0)
  const openRisk = DEMO_NL1_RISKS.filter((r) => r.status !== '已闭环').length

  return (
    <>
      <Card className="px-[18px] py-[15px]">
        <SectionHead title="专项工作台" hint="设计阶段 → 起草 → 校验交付物" />
        <StatStrip className="mt-3 grid-cols-2 sm:grid-cols-4">
          <StatCell label="阶段" value={`${DEMO_NONLIT_PHASES.length}`} />
          <StatCell label="已完成" value={`${doneCount}`} tone="green" />
          <StatCell label="进行中" value={`${doingCount}`} tone="blue" />
          <StatCell label="交付物" value={`${docCount} 份`} />
          <StatCell label="未闭环风险" value={`${openRisk} 条`} tone={openRisk > 0 ? 'yellow' : 'green'} />
        </StatStrip>

        <div className="mt-3.5 flex flex-col gap-2.5">
          <NonLitActionCard
            title="设计阶段"
            desc="按合同约定的服务范围，把项目拆成若干可验收的阶段。阶段名会派生合同文件夹目录，改名后自动同步。"
            actionLabel="设计阶段"
            hint="7 阶段 · 约 4 秒"
            state={design}
          />
          <NonLitActionCard
            title="从 0 起草阶段划分"
            desc="拿同类项目做参照，指出当前阶段划分缺什么、该怎么拆。只给建议，改不改由律师定。"
            actionLabel="从 0 起草"
            hint="3 条建议 · 约 3 秒"
            state={draft}
          />
          <NonLitActionCard
            title="校验交付物"
            desc="逐阶段核对交付物是否齐全、是否按验收标准签署。未签署的不算完成。"
            actionLabel="校验交付物"
            hint="3 阶段 · 约 3 秒"
            state={verifyDocs}
          />
        </div>

        {/* 起草建议 */}
        {draft.phase === 'done' ? (
          <div className="mt-3.5">
            <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">AI 给出的改进建议</div>
            <div className="flex flex-col gap-1.5">
              {DEMO_DRAFT_SUGGESTIONS.map((s) => (
                <Inset key={s.name}>
                  <div className="flex items-start gap-2">
                    <Sparkles className="mt-[2px] size-3.5 flex-none text-status-blue" />
                    <div className="min-w-0">
                      <div className="text-[12px] font-medium">{s.name}</div>
                      <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">{s.reason}</div>
                    </div>
                  </div>
                </Inset>
              ))}
            </div>
          </div>
        ) : null}

        {/* 阶段模板 */}
        <div className="mt-3.5">
          <div className="mb-2 text-[11px] font-medium text-muted-foreground">可用的阶段模板</div>
          <div className="flex flex-col gap-1.5">
            {DEMO_PHASE_TEMPLATES.map((t) => (
              <div key={t.name} className="flex items-center gap-2 rounded-[8px] bg-secondary/35 px-2.5 py-2">
                <span className="text-[12px] font-medium">{t.name}</span>
                <Pill>{t.phases} 阶段</Pill>
                <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground">{t.desc}</span>
                <span className="flex-none text-[10px] tabular-nums text-muted-foreground">用过 {t.used} 次</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* 阶段清单 + 交付物清单 + 推进到下一阶段（每行都能点开抽屉） */}
      <SpecialPhaseBoard initialPhaseId={focus?.phaseId} phaseFocus={focus?.n ?? 0} />

      {/* 7 阶段时间轴甘特（div 画的条形，计划工期 / 实际进度 / 是否延期） */}
      <SpecialGanttCard onPickPhase={(phaseId: string) => setFocus((v) => ({ phaseId, n: (v?.n ?? 0) + 1 }))} />

      {/* 风险登记表 + 客户确认记录 */}
      <SpecialRiskCard onAssess={() => void riskAssess.execute()} />
      <Card className="px-[18px] py-[15px]">
        <SectionHead title="风险复评" hint="点风险登记表的「重新评估」触发" />
        <div className="mt-3">
          <NonLitActionCard
            title="风险复评"
            desc="按交付物与客户确认的当前状态重算每条风险的等级与到期日；等级上升的会停下问人，不自动升级。"
            actionLabel="复评风险"
            hint={`${DEMO_NL1_RISKS.length} 条 · 约 3 秒`}
            state={riskAssess}
          />
        </div>
      </Card>
      <SpecialConfirmCard />
    </>
  )
}

/* ═══════════════════════════════════════════════════════════
 * B. 跨境合同审查：逐条审查 + 法条核验
 * ═══════════════════════════════════════════════════════════ */

export function CrossBorderWorkbench() {
  /** 逐条审查整份合同 */
  const review = useNonLitAction(
    [
      { text: '读取合同全文（3 语版本，9 条）', ms: 600, parallel: ['英文版', '中文版', '泰文版'] },
      { text: '识别我方立场：承租方（Lessee）', ms: 700 },
      {
        text: '逐条比对风险点',
        ms: 1400,
        retry: { times: 1, delay: 1000, reason: '泰文版排版异常，重新解析' },
      },
      { text: '检出 5 处需修订条款', ms: 700 },
      {
        text: '给每处挂法条依据',
        ms: 800,
        confirm: '5 处修订中 4 处有泰国法条支持，第 5 处「泰文优先」无外国法依据。是否保留为「需律师判断」？',
      },
      { text: '审查完成', ms: 400 },
    ],
    '检出 5 处风险：2 高 2 中 1 低，其中 4 处已挂泰国法条',
  )

  /** 法条核验：三道规则闸 + 判断层 */
  const verify = useNonLitAction(
    DEMO_LAW_GATES.map((g) => ({
      text: `规则闸 ${g.n} · ${g.name}（${g.ms} ms）`,
      ms: g.ms,
      ...(g.n === '02' ? { retry: { times: 1, delay: 900, reason: 'BARLC 接口超时' } } : {}),
    })),
    '4 道闸全部通过：法存在、有正文、条款号在范围内、条文支持该主张',
  )

  const highCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'high').length
  const midCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'mid').length
  const lowCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.severity === 'low').length
  const verifiedCount = DEMO_TH_CONTRACT_REVISIONS.filter((r) => r.verified).length

  return (
    /* 这一张是**容器卡**，里面还要塞 7 张子卡：容器自己再画边框就成了三层同心矩形，
       所以这里按「无边框区段」处理（只用标题分隔），子卡各自是独立的卡。 */
    <Card className="border-0 bg-transparent px-0 py-0 shadow-none">
      <SectionHead title="跨境合同审查" hint="逐条审 + 外国法核验" />
      <StatStrip className="mt-2.5 grid-cols-2 sm:grid-cols-4">
        <StatCell label="风险条款" value={`${DEMO_TH_CONTRACT_REVISIONS.length}`} />
        <StatCell label="高 / 中 / 低" value={`${highCount}/${midCount}/${lowCount}`} />
        <StatCell label="已挂法条" value={`${verifiedCount}`} tone="green" />
        <StatCell label="核验闸" value={`${DEMO_LAW_GATES.length} 道`} tone="blue" />
      </StatStrip>

      <div className="mt-3.5 flex flex-col gap-2.5">
        <NonLitActionCard
          title="逐条审查合同"
          desc="按我方立场逐条比对风险点，每处修订都挂外国法依据。挂不上法条的不硬编，标成「需律师判断」。"
          actionLabel="开始审查"
          hint="9 条 · 约 4 秒"
          state={review}
        />
        <NonLitActionCard
          title="外国法条核验"
          desc="先过三道规则闸（法是否存在、有没有正文、条款号在不在范围内），才交给判断层比对语义。编造的法条在这三道闸上就死了。"
          actionLabel="核验法条"
          hint="4 道闸 · 约 5 秒"
          state={verify}
        />
      </div>

      {/* 核验日志 */}
      {verify.phase === 'done' ? (
        <div className="mt-3.5">
          <div className="mb-2 text-[11px] font-medium text-muted-foreground">核验日志</div>
          <Inset className="bg-secondary/25">
            <ul className="flex flex-col gap-[2px]">
              {DEMO_VERIFY_LOG.map((l) => (
                <li key={l.at} className="flex items-start gap-2 text-[10.5px] leading-[1.5]">
                  <span className="flex-none tabular-nums text-muted-foreground">{l.at}</span>
                  <span
                    className={cn(
                      'min-w-0 flex-1',
                      l.kind === 'ok' ? 'text-status-green' : l.kind === 'warn' ? 'text-status-yellow' : 'text-secondary-foreground',
                    )}
                  >
                    {l.text}
                  </span>
                </li>
              ))}
            </ul>
          </Inset>
        </div>
      ) : null}

      {/* 机器跑完之后律师真正要用的四块：双语正文 / 法条依据 / 维度筛选 / 逐条采纳。
          四块共享「当前选中修订」，见 nonlit/crossborder/CrossBorderViews。 */}
      <div className="mt-3.5">
        <ForeignLawVerifyCard />
      </div>

      <CrossBorderViews lawVerified={verify.phase !== 'idle'} />
    </Card>
  )
}

/* ═══════════════════════════════════════════════════════════
 * C. 常年顾问：服务配额 + 事项流 + 回访 + 风险 + 续签
 *
 * 常法合同卖的是「一年 20 小时/月」，所以这一页要回答的是「服务期走了多少、
 * 每月忙不忙、配额还能撑多久、要不要续签」。卡片全部落在 nonlit/advisor/ 下，
 * 这里只做汇总条与编排（单卡实现见各文件头注释）。
 * ═══════════════════════════════════════════════════════════ */

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

/* ═══════════════════════════════════════════════════════════
 * 导出：按 case_type 选对应工作台
 * ═══════════════════════════════════════════════════════════ */

export function NonLitWorkbench({ caseType }: { caseType: string }) {
  if (caseType === 'advisor') return <AdvisorWorkbench />
  return <CrossBorderWorkbench />
}

/** 专项服务专用（有阶段树的那条） */
export function SpecialWorkbench() {
  return <SpecialPhaseWorkbench />
}

/** 供页面判断用：无阶段树时给专项工作台，有阶段树时也用同一个 */
export const CROSS_BORDER_HINT = '跨境合同审查'
export const FILE_ICON = FileText
export const SCALE_ICON = Scale
export const EDU_ICON = GraduationCap
