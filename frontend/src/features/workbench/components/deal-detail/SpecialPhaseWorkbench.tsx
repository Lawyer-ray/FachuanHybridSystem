/**
 * 非诉线 A · 专项服务工作台：阶段设计与交付物校验。
 *
 * 从 `nonlit-workbench.tsx` 按「一屏一个工作台」拆出（原文件 532 行越过 450
 * 行硬红线）。本文件只搬移，逐字保持原有的动作脚本、文案与汇总口径——拆分的
 * 判据是「这个屏自己的编排」，不是机械切行。三个工作台共用的汇总小件在
 * nonlit/special/special-stat.tsx，各自的子卡仍在 nonlit/ 下。
 *
 * 交互范式与诉讼线的六阶段一致：进度条 + 逐步日志 + 失败重试 + 中途要人确认。
 */

import { useState } from 'react'
import { Sparkles } from 'lucide-react'

import {
  DEMO_DRAFT_SUGGESTIONS,
  DEMO_NL1_RISKS,
  DEMO_NONLIT_PHASES,
  DEMO_PHASE_TEMPLATES,
} from './demo-nonlit'
import { NonLitActionCard } from './nonlit-action-card'
import { Inset, TonePill } from './nonlit/special/special-bits'
import { SectionHead, StatCell, StatStrip } from './nonlit/special/special-stat'
import { SpecialGanttCard } from './nonlit/special/special-gantt-card'
import { SpecialPhaseBoard } from './nonlit/special/special-phase-board'
import { SpecialConfirmCard, SpecialRiskCard } from './nonlit/special/special-risk-card'
import { useNonLitAction } from './use-nonlit-action'
import { Card } from './ui'

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
                <TonePill>{t.phases} 阶段</TonePill>
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
