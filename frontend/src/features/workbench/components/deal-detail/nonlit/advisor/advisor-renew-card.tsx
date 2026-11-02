/**
 * 常年顾问 · 续签提醒（本页的主交互）
 *
 * 常法合同到期前如果不主动发起续签，客户往往就流失了；但「什么时候提、提多少钱」
 * 不能凭感觉——它取决于两件事：**还剩多少天**（时间窗）和**工时用了多少**（配额）。
 * 这里把两个信号合成一条可执行的建议，并让律师点一下就能把续签函跑出来。
 *
 * 判定规则在 `advisor-domain.buildRenewSuggestion`（可单测），组件只负责呈现与运行。
 */

import { ArrowRight, RefreshCw, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'

import { NonLitActionCard } from '../../nonlit-action-card'
import { useNonLitAction } from '../../use-nonlit-action'
import { Card } from '../../ui'
import { buildRenewSuggestion, renewSteps, type RenewVerdict } from './advisor-domain'

const VERDICT_TONE: Record<RenewVerdict, { box: string; text: string; label: string }> = {
  renew: { box: 'border-status-green/40 bg-status-green-bg/60', text: 'text-status-green', label: '原价续签' },
  renegotiate: { box: 'border-status-yellow/40 bg-status-yellow-bg/60', text: 'text-status-yellow', label: '调价续签' },
  hold: { box: 'border-border bg-secondary/60', text: 'text-secondary-foreground', label: '暂缓续签' },
}

export function AdvisorRenewCard() {
  const suggestion = buildRenewSuggestion()
  const act = useNonLitAction(renewSteps(), suggestion.headline)
  const tone = VERDICT_TONE[suggestion.verdict]

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">续签提醒</h3>
        <span className="text-[11px] text-muted-foreground">合同剩余天数 → 工时使用率 → 续签建议</span>
        <span
          className={cn(
            'ml-auto rounded-[6px] border px-2 text-[11px] leading-[1.7] font-[620]',
            tone.box,
            tone.text,
          )}
        >
          {tone.label}
        </span>
      </div>

      {/* 两条检测信号 */}
      <div className="mt-2.5 grid grid-cols-2 gap-1.5 max-[820px]:grid-cols-1">
        {suggestion.signals.map((sig) => (
          <div key={sig.key} className="rounded-[8px] border border-border-light bg-background px-2.5 py-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] text-muted-foreground">{sig.label}</span>
              <span
                className={cn(
                  'ml-auto text-[12px] font-[620] tabular-nums',
                  sig.tone === 'red'
                    ? 'text-status-red'
                    : sig.tone === 'yellow'
                      ? 'text-status-yellow'
                      : sig.tone === 'green'
                        ? 'text-status-green'
                        : 'text-secondary-foreground',
                )}
              >
                {sig.value}
              </span>
            </div>
            <div className="mt-0.5 text-[10px] leading-[1.55] text-muted-foreground">{sig.reason}</div>
          </div>
        ))}
      </div>

      {/* 结论 + 动作 */}
      <div className={cn('mt-2.5 rounded-[9px] border px-3 py-2', tone.box)}>
        <div className={cn('flex items-center gap-1.5 text-[11.5px] font-[620]', tone.text)}>
          <ShieldCheck className="size-3.5" /> {suggestion.title}
        </div>
        <p className="mt-1 text-[11px] leading-[1.65] text-secondary-foreground">{suggestion.headline}</p>
        <ul className="mt-1.5 flex flex-col gap-[3px]">
          {suggestion.actions.map((a) => (
            <li key={a} className="flex items-start gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <ArrowRight className="mt-[3px] size-2.5 flex-none" />
              <span className="min-w-0 flex-1">{a}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-2.5">
        <NonLitActionCard
          title="生成续签方案"
          desc="按剩余天数与工时使用率检测续签窗口，结合风险清单里未闭环的高等级项给出报价系数，草拟续签函并落到合同文件夹。"
          actionLabel="检测并生成"
          hint="4 项检测 · 约 4 秒 · 中途要确认"
          state={act}
        />
      </div>

      {act.phase === 'done' ? (
        <div className="mt-2 flex items-center gap-2 rounded-[8px] border border-status-green/40 bg-status-green-bg/50 px-3 py-1.5 text-[10.5px] text-status-green">
          <RefreshCw className="size-3 flex-none" />
          续签函草稿：《法律顾问服务合同（第二期）》，报价 {suggestion.suggestedFee.toLocaleString('zh-CN')} 元／年
        </div>
      ) : null}
    </Card>
  )
}
