/**
 * ③ 缺件 —— 系统发现遗漏，自动通知客户补什么
 *
 * 这一步的价值不在「列出来」，而在**通知发出去、客户补齐了、系统认出来了**。
 * 所以版面围绕「每条缺件的通知状态」展开：发了没、走了哪个渠道、客户回了什么。
 */

import { AlertTriangle, CheckCircle2, Clock, Mail, MessageSquare, Send } from 'lucide-react'

import { DEMO_GAP_NOTICES, DEMO_GAP_RECEIVED, DEMO_GAP_TEMPLATES } from '../demo-data'
import { InsetBlock, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

const CHANNEL_ICON: Record<string, typeof Mail> = {
  '短信 + 邮件': Mail,
  微信: MessageSquare,
  邮件: Mail,
}

export function GapPanel() {
  const blockers = DEMO_GAP_NOTICES.filter((g) => g.severity === 'blocker')
  const received = DEMO_GAP_NOTICES.filter((g) => g.status === 'received')
  const waiting = DEMO_GAP_NOTICES.filter((g) => g.status !== 'received')
  const blockerOpen = blockers.filter((g) => g.status !== 'received').length

  return (
    <div className="flex flex-col gap-3.5">
      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="发现缺件" value={`${DEMO_GAP_NOTICES.length} 项`} tone="yellow" />
        <StatCell label="硬阻塞" value={`${blockers.length} 项`} tone="red" />
        <StatCell label="客户已补" value={`${received.length} 项`} tone="green" />
        <StatCell label="仍待补" value={`${waiting.length} 项`} tone={waiting.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 通知是自动发出去的 */}
          <WorkCard>
            <SectionTitle title="补件通知已自动发出" hint="识别到缺件后 3 分钟内" />
            <InsetBlock className="mt-2.5">
              <div className="flex items-start gap-2.5">
                <Send className="mt-[2px] size-3.5 flex-none text-status-blue" />
                <div className="min-w-0">
                  <div className="text-[12px] font-medium">
                    已向客户经理 王某某 发送补件清单（{DEMO_GAP_NOTICES.length} 项）
                  </div>
                  <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                    短信 + 邮件双通道 · 10-28 14:02 · 附带客户上传链接（免登录，链接即凭证）
                  </div>
                </div>
              </div>
            </InsetBlock>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Pill tone="blue">短信已送达</Pill>
              <Pill tone="blue">邮件已送达</Pill>
              <Pill tone="green">客户已读</Pill>
            </div>
          </WorkCard>

          {/* 逐项缺件 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="缺件清单" hint="硬阻塞项不补齐无法送法院" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_GAP_NOTICES.map((g) => {
                const Icon = CHANNEL_ICON[g.channel] ?? Mail
                const done = g.status === 'received'
                return (
                  <li key={g.item} className="flex items-start gap-3 px-5 py-3">
                    <span
                      className={cn(
                        'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                        done ? 'bg-status-green' : g.severity === 'blocker' ? 'bg-status-red' : 'bg-status-yellow',
                      )}
                    >
                      {done ? (
                        <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                      ) : g.severity === 'blocker' ? (
                        <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
                      ) : (
                        <Clock className="size-2.5 text-white" strokeWidth={3} />
                      )}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-[12.5px] font-medium">{g.item}</span>
                        {g.severity === 'blocker' ? (
                          <span className="text-[9.5px] font-semibold text-status-red">硬阻塞</span>
                        ) : null}
                      </div>
                      <div className="mt-0.5 text-[10.5px] leading-[1.55] text-muted-foreground">{g.reason}</div>
                      {done ? (
                        <div className="mt-1 flex items-center gap-1.5 text-[10.5px] text-status-green">
                          <CheckCircle2 className="size-2.5" />
                          {g.reply}
                        </div>
                      ) : null}
                    </div>

                    <div className="flex flex-none flex-col items-end gap-1">
                      <div className="flex items-center gap-1 text-[10.5px] text-muted-foreground">
                        <Icon className="size-2.5" />
                        {g.channel}
                      </div>
                      <span className="text-[10px] tabular-nums text-muted-foreground">{g.sentAt}</span>
                      <Pill tone={done ? 'green' : g.status === 'pending' ? 'yellow' : 'red'}>
                        {done ? '已补齐' : g.status === 'pending' ? '已发出' : '等待客户'}
                      </Pill>
                    </div>
                  </li>
                )
              })}
            </ul>
          </WorkCard>
          {/* 通知模板 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="通知模板" hint="按缺件等级自动选话术" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_GAP_TEMPLATES.map((t) => (
                <li key={t.title} className="px-5 py-2.5">
                  <div className="flex items-center gap-2">
                    <Pill tone={t.severity === '硬阻塞' ? 'red' : t.severity === '催办' ? 'yellow' : 'blue'}>{t.severity}</Pill>
                    <span className="text-[12px] font-medium">{t.title}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{t.channel}</span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">{t.body}</div>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 客户补回来的东西 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="客户补回来的材料" hint="系统自动识别并归入对应槽位" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_GAP_RECEIVED.map((r) => (
                <li key={r.item} className="flex items-start gap-3 px-5 py-3">
                  <CheckCircle2 className="mt-[3px] size-4 flex-none text-status-green" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-[12px] font-medium">{r.item}</span>
                      <Pill tone="green">已补齐</Pill>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                      <span>{r.fileName}</span>
                      <span className="text-border">·</span>
                      <span>{r.pages} 页</span>
                      <span className="text-border">·</span>
                      <span>{r.receivedAt}</span>
                    </div>
                    <div className="mt-0.5 text-[10.5px] text-status-green">{r.note}</div>
                  </div>
                </li>
              ))}
            </ul>
          </WorkCard>
        </div>

        <WorkCard padded={false}>
          <RailSection title="现在卡在哪">
            {blockerOpen > 0 ? (
              <div className="rounded-[8px] border border-status-red/40 bg-status-red-bg/60 px-2.5 py-2">
                <div className="text-[11.5px] font-medium text-status-red">
                  还有 {blockerOpen} 项硬阻塞未补齐
                </div>
                <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                  抵押物权属证明与共同借款人身份证明未到位，
                  这两项不齐无法确认抵押关系与共同债务，诉讼请求会缺依据。
                </p>
              </div>
            ) : (
              <div className="rounded-[8px] border border-status-green/40 bg-status-green-bg/60 px-2.5 py-2">
                <div className="text-[11.5px] font-medium text-status-green">硬阻塞项已全部补齐</div>
              </div>
            )}
          </RailSection>

          <RailSection title="客户怎么补">
            <div className="flex flex-col gap-2 text-[10.5px] leading-[1.65] text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">1. 点链接直接传</span>
                <div className="mt-0.5">短信里的链接免登录，链接本身即凭证，客户手机拍完就传。</div>
              </div>
              <div>
                <span className="font-medium text-foreground">2. 微信发文件</span>
                <div className="mt-0.5">收到的文件系统会自动识别属于哪个案件、放进哪个槽位。</div>
              </div>
              <div>
                <span className="font-medium text-foreground">3. 纸质邮寄</span>
                <div className="mt-0.5">寄回后行政扫描，系统扫邮箱自动归案（见「⑤ 回扫」）。</div>
              </div>
            </div>
          </RailSection>

          <RailSection title="补件到位后">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 自动重新校验缺件清单</div>
              <div>→ 硬阻塞清零后解锁「④ 文书」阶段</div>
              <div>→ 客户会收到「已收妥」回执</div>
            </div>
          </RailSection>
        </WorkCard>
      </div>
    </div>
  )
}
