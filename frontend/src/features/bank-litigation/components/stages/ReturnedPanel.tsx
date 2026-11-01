/**
 * ⑤ 回扫 —— 客户寄回、行政扫描、邮箱自动扫到，材料自动归到本案
 *
 * 这一阶段解决的问题：**材料的回流是分散的**（快递、扫描仪、邮箱、微信），
 * 律师不该挨个去找「刚才那份传票放哪了」。系统扫邮箱、认案号、认当事人，
 * 认出来的自动下载并挂到对应案件。
 *
 * 认不准的不硬塞 —— 低于阈值进「待处理」，让人来定。
 */

import { CheckCircle2, HelpCircle, Inbox, Mail } from 'lucide-react'

import { DEMO_RETURNED_DIFF, DEMO_RETURNED_MAILS, DEMO_SCAN_BATCHES } from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { DetailDrawer } from './DetailDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function ReturnedPanel() {
  const [mailOpen, setMailOpen] = useState<string | null>(null)

  /* 立刻扫一轮邮箱 */
  const scanNow = useStageAction({
    steps: [
      { text: '连接 3 个邮箱', ms: 600, parallel: ['一张网收件箱', '行政扫描仪', '客户往来邮箱'] },
      {
        text: '拉取新到邮件',
        ms: 700,
        retry: { times: 1, delay: 1000, reason: 'IMAP 连接被限流，等待后重试' },
      },
      { text: '下载附件 5 份（18.2 MB）', ms: 1100 },
      { text: '「Re: 谭某某案 补充材料」→ 案号+当事人名匹配 → 归案', ms: 500 },
      { text: '「扫描件-不动产权证」→ 文件名关键词匹配 → 归案', ms: 450 },
      { text: '「（20XX）粤0106民初XXXX号 受理通知书」→ 案号精确匹配 → 回填案号', ms: 550 },
      {
        text: '「FW: 律师函签收回执」→ 匹配度 62%，低于阈值',
        ms: 500,
        confirm: '这封邮件匹配度只有 62%，低于 80% 阈值。要放进「待处理」让人来定，还是按发送人自动归到本案？',
      },
      { text: '重跑缺件检测', ms: 700 },
    ],
    toSummary: () => '3 封自动归案、1 封进待处理；缺件从 5 项降到 3 项',
  })
  /* 对低匹配度的那封手动指定归属 */
  const assignManual = useStageAction({
    steps: [
      { text: '读取待处理邮件附件 1 份', ms: 320 },
      { text: '按发送人「客户 李某某」关联到本案共同借款人', ms: 420 },
      { text: '归入「送达地址确认书」槽位', ms: 340 },
    ],
    toSummary: () => '律师函签收回执已手动归属到本案',
  })

  const auto = DEMO_RETURNED_MAILS.filter((m) => m.action.startsWith('已'))
  const manual = DEMO_RETURNED_MAILS.filter((m) => !m.action.startsWith('已'))
  const attachments = DEMO_RETURNED_MAILS.reduce((n, m) => n + m.attachments, 0)

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="扫描邮箱，把新到的材料认领回来"
        desc="客户寄回、行政扫描、法院短信转发都会落到邮箱。系统按案号、当事人名、文件名认案，认出来的自动下载并挂到本案；认不准的进待处理，不硬塞。"
        actionLabel="立即扫描邮箱"
        hint="3 个邮箱 · 约 3 秒"
        state={scanNow}
        execute={() => void scanNow.execute()}
        reset={scanNow.reset}
        confirm={scanNow.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="扫到邮件" value={`${DEMO_RETURNED_MAILS.length} 封`} />
        <StatCell label="附件" value={`${attachments} 份`} />
        <StatCell label="自动归案" value={`${auto.length} 封`} tone="green" />
        <StatCell label="待人工" value={`${manual.length} 封`} tone={manual.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 邮箱自动扫描 */}
          <WorkCard>
            <SectionTitle title="系统正在扫这些邮箱" hint="每 5 分钟一轮" />
            <div className="mt-2.5 flex flex-col gap-1.5">
              {[
                { addr: 'courts@某某律所.邮箱', note: '一张网收件箱 · 法院送达文书', count: 128 },
                { addr: 'admin@某某律所.邮箱', note: '行政扫描仪自动转发', count: 42 },
                { addr: 'client@某某律所.邮箱', note: '客户往来附件', count: 67 },
              ].map((m) => (
                <InsetBlock key={m.addr}>
                  <div className="flex items-center gap-2.5">
                    <Mail className="size-3.5 flex-none text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px]">{m.addr}</div>
                      <div className="mt-0.5 text-[10.5px] text-muted-foreground">{m.note}</div>
                    </div>
                    <Pill tone="green">监听中</Pill>
                    <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
                      本月 {m.count} 封
                    </span>
                  </div>
                </InsetBlock>
              ))}
            </div>
          </WorkCard>

          {/* 行政扫描批次 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="行政扫描批次" hint="扫描仪自动转发到邮箱" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_SCAN_BATCHES.map((b) => (
                <li key={b.batch} className="flex items-center gap-3 px-5 py-2.5">
                  <span className="min-w-0 flex-1 truncate text-[12px]" title={b.batch}>{b.batch}</span>
                  <span className="w-[54px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">{b.pages} 页</span>
                  <span className="w-[150px] flex-none truncate text-[10.5px] text-muted-foreground" title={b.matched}>{b.matched}</span>
                  <span className="w-[44px] flex-none text-right text-[10.5px] tabular-nums"
                    style={{color: b.confidence >= 0.8 ? undefined : 'var(--status-yellow)'}}>
                    {(b.confidence * 100).toFixed(0)}%
                  </span>
                  <Pill tone={b.status === 'auto' ? 'green' : 'yellow'}>{b.status === 'auto' ? '自动归案' : '待人工'}</Pill>
                  <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{b.scannedAt}</span>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 归案前后 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="回扫带来的变化" hint="材料补齐后各指标怎么动" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_RETURNED_DIFF.map((r) => (
                <li key={r.stage} className="flex items-center gap-3 px-5 py-2.5">
                  <span className="w-[84px] flex-none text-[11.5px] text-muted-foreground">{r.stage}</span>
                  <span className="w-[92px] flex-none text-[12px]">{r.before}</span>
                  <span className="flex-none text-[10px] text-border">→</span>
                  <span className="w-[92px] flex-none text-[12px] font-medium">{r.after}</span>
                  <Pill tone={r.delta.startsWith('+') ? 'green' : 'blue'}>{r.delta}</Pill>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 归案结果 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <Inbox className="size-3.5 flex-none text-muted-foreground" />
              <SectionTitle title="已自动认领并归案" hint="按案号 / 当事人名 / 文件名关键词匹配" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_RETURNED_MAILS.map((m) => {
                const isAuto = m.action.startsWith('已自动') || m.action.startsWith('已归案')
                return (
                  <li
                    key={m.subject}
                    onClick={() => setMailOpen(m.subject)}
                    className="flex cursor-pointer items-start gap-3 px-5 py-3 transition-colors hover:bg-secondary/40"
                  >
                    <span
                      className={cn(
                        'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                        isAuto ? 'bg-status-green' : 'bg-status-yellow',
                      )}
                    >
                      {isAuto ? (
                        <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                      ) : (
                        <HelpCircle className="size-2.5 text-white" strokeWidth={3} />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12.5px] font-medium" title={m.subject}>
                        {m.subject}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                        <span>{m.from}</span>
                        <span className="text-border">·</span>
                        <span>{m.attachments} 个附件</span>
                        <span className="text-border">·</span>
                        <span>匹配依据：{m.matchedBy}</span>
                      </div>
                      <div
                        className={cn(
                          'mt-1 text-[10.5px]',
                          isAuto ? 'text-status-green' : 'text-status-yellow',
                        )}
                      >
                        {m.action}
                      </div>
                    </div>
                    <div className="flex flex-none flex-col items-end gap-1">
                      <Pill tone={isAuto ? 'green' : 'yellow'}>{m.matchedCase}</Pill>
                      <span className="text-[10px] tabular-nums text-muted-foreground">{m.at}</span>
                      {!isAuto ? (
                        <ActionButton sm onClick={() => void assignManual.execute()}>
                          指定归属
                        </ActionButton>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          </WorkCard>
        </div>

        <WorkCard padded={false}>
          <RailSection title="这一阶段在解决什么">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              材料回流是散的：快递寄回、行政扫描、法院短信、客户微信。
              律师不该挨个去找「刚才那份传票放哪了」。
              系统扫邮箱、认案号、认当事人，认出来的直接挂到本案。
            </p>
          </RailSection>

          <RailSection title="怎么认案">
            <div className="flex flex-col gap-2 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">案号精确匹配</span>
                <div className="mt-0.5">（20XX）粤0106民初XXXX号 → 直接定位到案件</div>
              </div>
              <div>
                <span className="font-medium text-foreground">当事人名 + 案由</span>
                <div className="mt-0.5">「谭某某 金融借款」命中唯一在办案件</div>
              </div>
              <div>
                <span className="font-medium text-foreground">文件名关键词</span>
                <div className="mt-0.5">「不动产权证」「催收记录」按类型归槽</div>
              </div>
            </div>
          </RailSection>

          <RailSection title="认不准怎么办">
            <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
              <div className="text-[11px] font-medium">低于 80% 匹配度不硬塞</div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                放进「待处理」让律师定。硬塞错案的代价远大于让律师多点一下。
              </p>
            </div>
          </RailSection>

          <RailSection title="归案之后">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 自动拆分成单份材料</div>
              <div>→ 自动转 markdown</div>
              <div>→ 重跑缺件检测（见「③ 缺件」）</div>
            </div>
          </RailSection>
        </WorkCard>
      </div>

      <MailDrawer subject={mailOpen} onClose={() => setMailOpen(null)} />
    </div>
  )
}

/** 邮件详情：能看到附件、匹配依据、可改归属 */
function MailDrawer({ subject, onClose }: { subject: string | null; onClose: () => void }) {
  const m = subject ? DEMO_RETURNED_MAILS.find((x) => x.subject === subject) : null
  const isAuto = m ? m.action.startsWith('已') : false

  return (
    <DetailDrawer
      open={m != null}
      onClose={onClose}
      title={m?.subject ?? ''}
      subtitle={m ? `${m.from} · ${m.attachments} 个附件 · ${m.at}` : undefined}
      badge={m ? <Pill tone={isAuto ? 'green' : 'yellow'}>{isAuto ? '已自动归案' : '待人工'}</Pill> : null}
      footer={
        m ? (
          <>
            <ActionButton dark onClick={onClose}>
              确认归属
            </ActionButton>
            <ActionButton onClick={onClose}>改归其他案件</ActionButton>
            <ActionButton onClick={onClose}>标记为无关</ActionButton>
          </>
        ) : null
      }
    >
      {m ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="发件人">{m.from}</KeyValueRow>
            <KeyValueRow label="匹配案件">{m.matchedCase}</KeyValueRow>
            <KeyValueRow label="匹配依据">{m.matchedBy}</KeyValueRow>
            <KeyValueRow label="处理结果">{m.action}</KeyValueRow>
          </dl>

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">附件（{m.attachments}）</div>
            <div className="mt-1.5 flex flex-col gap-1">
              {Array.from({ length: m.attachments }).map((_, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="size-3 rounded-[2px] bg-secondary" />
                  <span className="min-w-0 flex-1 truncate">附件_{i + 1}.pdf</span>
                  <span className="text-[10px] text-muted-foreground">{(1.2 + i * 0.4).toFixed(1)} MB</span>
                </div>
              ))}
            </div>
          </InsetBlock>

          {!isAuto ? (
            <InsetBlock className="border-status-yellow/40 bg-status-yellow-bg/60">
              <div className="text-[10.5px] font-medium">匹配度低于阈值</div>
              <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
                系统没法确定这封邮件属于哪个案子，放进了待处理。硬塞错案的代价远大于让律师多点一下。
              </p>
            </InsetBlock>
          ) : null}
        </div>
      ) : null}
    </DetailDrawer>
  )
}
