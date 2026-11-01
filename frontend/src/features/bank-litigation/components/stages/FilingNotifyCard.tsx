/**
 * ⑥ 校验 —— 校验通过后怎么通知律师去一张网提交
 *
 * 这是两阶段的：
 *   ① 发通知（机器做，可被签章阻塞挡下）
 *   ② 送达情况（站内待办 / 短信 / AI 助手卡片各自到哪一步）
 *
 * 分开是有意义的：发出去 ≠ 对方看见。短信只到「已发送」，
 * 站内待办才会回「已读」，律师不点进来这条通知就是没生效。
 */

import { AlertTriangle, Check, Gavel, MessageSquare, Smartphone, X } from 'lucide-react'

import { DEMO_X3_NOTICE_DELIVERY } from '../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill, SectionTitle, StepItem, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

/** 通知发出后走过的阶段 */
export type NotifyStage = 'idle' | 'sending' | 'sent'

export function FilingNotifyCard({
  blockedCount,
  blockedNotes,
  stage,
  onSend,
}: {
  blockedCount: number
  blockedNotes: string[]
  stage: NotifyStage
  onSend: () => void
}) {
  const sent = stage === 'sent'

  return (
    <WorkCard>
      <SectionTitle title="校验通过后怎么通知律师" hint="机器只做检查，不代提交" />
      <div className="mt-3">
        <StepItem
          index={1}
          title="签字盖章全部齐备"
          desc="机器核对，不齐不通知"
          state={blockedCount ? 'blocked' : 'done'}
        />
        <StepItem
          index={2}
          title="推送待办给主办律师"
          desc="站内通知 + 短信 + AI 助手卡片"
          state={blockedCount ? 'todo' : sent ? 'done' : 'current'}
        />
        <StepItem
          index={3}
          title="律师打开一张网核对表单"
          desc={sent ? '已送达，等律师点开' : '机器已填好，律师逐项看'}
          state={sent ? 'current' : 'todo'}
        />
        <StepItem index={4} title="律师本人点提交" desc="这一步机器不代点，责任在签字律师" state="todo" />
      </div>

      <InsetBlock className="mt-3">
        <div className="flex items-start gap-2.5">
          <Gavel className="mt-[1px] size-3.5 flex-none text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-medium">
                {blockedCount
                  ? `还不能通知律师：${blockedCount} 份文书未通过核对`
                  : sent
                    ? '已通知，律师待办里已出现这条'
                    : '可以通知律师去一张网提交了'}
              </span>
              <span className="ml-auto" />
              <ActionButton sm disabled={stage !== 'idle'} onClick={onSend}>
                {stage === 'sending' ? '发送中…' : sent ? '已发送' : '通知律师去提交'}
              </ActionButton>
            </div>
            <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              {blockedCount
                ? blockedNotes.join('；')
                : sent
                  ? '站内待办已读、短信已发出，AI 助手卡片已进工作台待办区。'
                  : '律师会在待办里收到一条「去一张网提交」的提醒，点开即到立案页。'}
            </div>
          </div>
        </div>

        {sent ? <DeliveryPanel /> : null}
      </InsetBlock>
    </WorkCard>
  )
}

/** 送达回执：三条通道各到哪一步 */
function DeliveryPanel() {
  const icons = {
    站内待办: MessageSquare,
    短信: Smartphone,
    'AI 助手卡片': MessageSquare,
  } as const

  return (
    <div className="mt-2.5 border-t border-border-light pt-2">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[10.5px] font-medium text-secondary-foreground">送达情况</span>
        <Pill tone="green">已送达</Pill>
      </div>
      <dl>
        {DEMO_X3_NOTICE_DELIVERY.map((d) => {
          const Icon = icons[d.channel as keyof typeof icons] ?? MessageSquare
          return (
            <KeyValueRow key={d.channel} label={d.channel}>
              <span className="flex items-center gap-1.5">
                <Icon className="size-3 flex-none text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{d.target}</span>
                <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{d.at}</span>
                <span
                  className={cn(
                    'flex flex-none items-center gap-0.5 text-[10.5px]',
                    d.state === 'read'
                      ? 'text-status-green'
                      : d.state === 'failed'
                        ? 'text-status-red'
                        : 'text-status-blue',
                  )}
                >
                  {d.state === 'read' ? (
                    <>
                      <Check className="size-2.5" strokeWidth={3} /> 已读
                    </>
                  ) : d.state === 'failed' ? (
                    <>
                      <X className="size-2.5" strokeWidth={3} /> 失败
                    </>
                  ) : (
                    '已发送'
                  )}
                </span>
              </span>
            </KeyValueRow>
          )
        })}
      </dl>
      <div className="mt-1 flex items-start gap-1.5 text-[10px] leading-[1.6] text-muted-foreground">
        <AlertTriangle className="mt-[1px] size-2.5 flex-none text-status-yellow" />
        短信只到「已发送」不回执；律师真正干活看的是站内待办这条已读。
      </div>
    </div>
  )
}
