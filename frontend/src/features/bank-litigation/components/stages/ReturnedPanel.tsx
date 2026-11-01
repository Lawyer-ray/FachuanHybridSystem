/**
 * ⑤ 回扫 —— 客户寄回、行政扫描、邮箱自动扫到，材料自动归到本案
 *
 * 这一阶段解决的问题：**材料的回流是分散的**（快递、扫描仪、邮箱、微信），
 * 律师不该挨个去找「刚才那份传票放哪了」。系统扫邮箱、认案号、认当事人，
 * 认出来的自动下载并挂到对应案件。
 *
 * 认不准的不硬塞 —— 低于阈值进「待处理」，让人来定。
 *
 * 所以这一屏要能回答四件事：扫的是哪些邮箱、它们怎么配的（能改）；
 * 扫到的邮件里附件长什么样（能预览）；哪些归上了、哪些没归上（能筛）；
 * 没归上的怎么手工挂到案子上去（搜案件 → 选槽位 → 确认）。
 */

import { CheckCircle2, FileImage, FileText, HelpCircle, Inbox, Mail, Search, Settings2 } from 'lucide-react'
import { useState } from 'react'

import {
  DEMO_RETURNED_DIFF,
  DEMO_RETURNED_MAILS,
  DEMO_SCAN_BATCHES,
  DEMO_X2_ASSIGN_CANDIDATES,
  DEMO_X2_CLAIM_FILTERS,
  DEMO_X2_MAIL_ATTACHMENTS,
  DEMO_X2_SCAN_INTERVALS,
  DEMO_X2_SCAN_MAILBOXES,
  type AssignCandidate,
  type ClaimFilter,
  type MailAttachment,
  type ScanMailboxConfig,
} from '../demo-data'
import { StageActionCard } from './StageActionCard'
import { DetailDrawer } from './DetailDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

/** 归案日志里一封邮件的筛选口径 */
type ClaimKind = 'auto' | 'manual' | 'ignored'

function claimKindOf(action: string): ClaimKind {
  if (action.startsWith('已标记无关')) return 'ignored'
  if (action.startsWith('已自动') || action.startsWith('已归案')) return 'auto'
  return 'manual'
}

export function ReturnedPanel() {
  const [mailOpen, setMailOpen] = useState<string | null>(null)
  /** 归案日志筛选 */
  const [claimFilter, setClaimFilter] = useState<ClaimFilter>('全部')
  /** 正在配置的邮箱地址 */
  const [configAddr, setConfigAddr] = useState<string | null>(null)
  /** 已保存的邮箱配置（按地址覆盖默认值） */
  const [mailboxConfig, setMailboxConfig] = useState<Record<string, ScanMailboxConfig>>({})
  /** 正在做手动归案的那封邮件 */
  const [assignSubject, setAssignSubject] = useState<string | null>(null)
  /** 演示：标记为无关的邮件 */
  const [ignored, setIgnored] = useState<Set<string>>(new Set())

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

  const rows = DEMO_RETURNED_MAILS.map((m) => (ignored.has(m.subject) ? { ...m, action: '已标记无关' } : m))
  const auto = rows.filter((m) => claimKindOf(m.action) === 'auto')
  const manual = rows.filter((m) => claimKindOf(m.action) === 'manual')
  const ignoredCount = rows.filter((m) => claimKindOf(m.action) === 'ignored').length
  const attachments = rows.reduce((n, m) => n + m.attachments, 0)

  const claimCount = (f: ClaimFilter) =>
    f === '全部'
      ? rows.length
      : rows.filter((m) => claimKindOf(m.action) === (f === '自动归案' ? 'auto' : f === '待人工' ? 'manual' : 'ignored')).length
  const shownMails =
    claimFilter === '全部'
      ? rows
      : rows.filter(
          (m) => claimKindOf(m.action) === (claimFilter === '自动归案' ? 'auto' : claimFilter === '待人工' ? 'manual' : 'ignored'),
        )

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
        <StatCell label="扫到邮件" value={`${rows.length} 封`} />
        <StatCell label="附件" value={`${attachments} 份`} />
        <StatCell label="自动归案" value={`${auto.length} 封`} tone="green" />
        <StatCell label="待人工" value={`${manual.length} 封`} tone={manual.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 邮箱自动扫描：每行可改配置 */}
          <WorkCard>
            <SectionTitle title="系统正在扫这些邮箱" hint="每 5 分钟一轮" />
            <div className="mt-2.5 flex flex-col gap-1.5">
              {DEMO_X2_SCAN_MAILBOXES.map((base) => {
                const m = mailboxConfig[base.addr] ?? base
                const changed = mailboxConfig[base.addr] != null
                return (
                  <InsetBlock key={base.addr}>
                    <div className="flex items-center gap-2.5">
                      <Mail className="size-3.5 flex-none text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[12px]">{m.addr}</div>
                        <div className="mt-0.5 truncate text-[10.5px] text-muted-foreground">
                          {m.note} · 每 {m.interval} · {m.folder}
                        </div>
                      </div>
                      {changed ? <Pill tone="blue">已改配置</Pill> : null}
                      <Pill tone="green">监听中</Pill>
                      <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
                        本月 {m.count} 封
                      </span>
                      <ActionButton sm title="改轮询间隔 / 文件夹 / 发件人白名单" onClick={() => setConfigAddr(base.addr)}>
                        <Settings2 className="size-3" />
                        设置
                      </ActionButton>
                    </div>
                  </InsetBlock>
                )
              })}
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

          {/* 归案结果：可筛选 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <Inbox className="size-3.5 flex-none text-muted-foreground" />
              <SectionTitle title="已自动认领并归案" hint="按案号 / 当事人名 / 文件名关键词匹配" className="w-full" />
            </div>

            {/* 归案状态筛选 */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-border-light bg-secondary/25 px-5 py-2">
              <span className="text-[10.5px] text-muted-foreground">筛选</span>
              {DEMO_X2_CLAIM_FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  aria-pressed={claimFilter === f}
                  onClick={() => setClaimFilter(f)}
                  className={cn(
                    'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
                    claimFilter === f
                      ? 'border-foreground bg-foreground font-semibold text-background'
                      : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
                  )}
                >
                  {f}
                  <span className={cn('ml-1 tabular-nums', claimFilter === f ? 'opacity-70' : 'text-muted-foreground')}>
                    {claimCount(f)}
                  </span>
                </button>
              ))}
              {ignoredCount > 0 ? (
                <span className="ml-auto text-[10px] text-muted-foreground">已标记无关 {ignoredCount} 封</span>
              ) : null}
            </div>

            <ul className="divide-y divide-border-light">
              {shownMails.map((m) => {
                const kind = claimKindOf(m.action)
                const isAuto = kind === 'auto'
                return (
                  <li
                    key={m.subject}
                    onClick={() => setMailOpen(m.subject)}
                    className="flex cursor-pointer items-start gap-3 px-5 py-3 transition-colors hover:bg-secondary/40"
                  >
                    <span
                      className={cn(
                        'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                        isAuto ? 'bg-status-green' : kind === 'ignored' ? 'bg-secondary' : 'bg-status-yellow',
                      )}
                    >
                      {isAuto ? (
                        <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                      ) : (
                        <HelpCircle className={cn('size-2.5', kind === 'ignored' ? 'text-muted-foreground' : 'text-white')} strokeWidth={3} />
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
                          isAuto ? 'text-status-green' : kind === 'ignored' ? 'text-muted-foreground' : 'text-status-yellow',
                        )}
                      >
                        {m.action}
                      </div>
                    </div>
                    <div className="flex flex-none flex-col items-end gap-1">
                      <Pill tone={isAuto ? 'green' : kind === 'ignored' ? 'neutral' : 'yellow'}>{m.matchedCase}</Pill>
                      <span className="text-[10px] tabular-nums text-muted-foreground">{m.at}</span>
                      {kind === 'manual' ? (
                        /* 行本身是「打开邮件抽屉」，这里要拦住冒泡，只开归案弹窗 */
                        <span onClick={(e) => e.stopPropagation()}>
                          <ActionButton sm onClick={() => setAssignSubject(m.subject)}>
                            <Search className="size-3" />
                            指定归属
                          </ActionButton>
                        </span>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
            {shownMails.length === 0 ? (
              <div className="px-5 py-6 text-center text-[11.5px] text-muted-foreground">
                「{claimFilter}」下没有邮件
              </div>
            ) : null}
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

      <MailDrawer
        subject={mailOpen}
        onClose={() => setMailOpen(null)}
        ignored={ignored}
        onIgnore={(s) => {
          setIgnored((prev) => new Set(prev).add(s))
          setMailOpen(null)
        }}
        onAssign={(s) => {
          setMailOpen(null)
          setAssignSubject(s)
        }}
      />

      <MailboxConfigDrawer
        addr={configAddr}
        saved={mailboxConfig}
        onClose={() => setConfigAddr(null)}
        onSave={(cfg) => {
          setMailboxConfig((prev) => ({ ...prev, [cfg.addr]: cfg }))
          setConfigAddr(null)
        }}
      />

      <AssignDrawer
        subject={assignSubject}
        onClose={() => setAssignSubject(null)}
        assign={assignManual}
      />
    </div>
  )
}

/** 邮件详情：附件可点开预览、匹配依据、可改归属 */
function MailDrawer({
  subject,
  onClose,
  ignored,
  onIgnore,
  onAssign,
}: {
  subject: string | null
  onClose: () => void
  ignored: Set<string>
  onIgnore: (subject: string) => void
  onAssign: (subject: string) => void
}) {
  const raw = subject ? DEMO_RETURNED_MAILS.find((x) => x.subject === subject) : null
  const m = raw && ignored.has(raw.subject) ? { ...raw, action: '已标记无关' } : raw
  const kind = m ? claimKindOf(m.action) : 'manual'
  const files = m ? DEMO_X2_MAIL_ATTACHMENTS.filter((a) => a.subject === m.subject) : []

  return (
    <DetailDrawer
      open={m != null}
      onClose={onClose}
      title={m?.subject ?? ''}
      subtitle={m ? `${m.from} · ${m.attachments} 个附件 · ${m.at}` : undefined}
      badge={
        m ? (
          <Pill tone={kind === 'auto' ? 'green' : kind === 'ignored' ? 'neutral' : 'yellow'}>
            {kind === 'auto' ? '已自动归案' : kind === 'ignored' ? '已标记无关' : '待人工'}
          </Pill>
        ) : null
      }
      footer={
        m ? (
          <>
            {kind === 'manual' ? (
              <ActionButton dark onClick={() => onAssign(m.subject)}>
                指定归属
              </ActionButton>
            ) : (
              <ActionButton dark onClick={onClose}>
                确认归属
              </ActionButton>
            )}
            <ActionButton onClick={onClose}>改归其他案件</ActionButton>
            <ActionButton onClick={() => onIgnore(m.subject)} disabled={kind === 'ignored'}>
              标记为无关
            </ActionButton>
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
            <div className="text-[10px] text-muted-foreground">附件（{m.attachments}）· 点一行看预览</div>
            <div className="mt-1.5 flex flex-col gap-1">
              {files.length > 0 ? (
                files.map((f) => <AttachmentRow key={f.name} attachment={f} />)
              ) : (
                Array.from({ length: m.attachments }).map((_, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="size-3 rounded-[2px] bg-secondary" />
                    <span className="min-w-0 flex-1 truncate">附件_{i + 1}.pdf</span>
                    <span className="text-[10px] text-muted-foreground">{(1.2 + i * 0.4).toFixed(1)} MB</span>
                  </div>
                ))
              )}
            </div>
          </InsetBlock>

          {kind === 'manual' ? (
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

/** 一个附件：折叠态是一行，点开就地展开预览（图片/PDF 占位） */
function AttachmentRow({ attachment }: { attachment: MailAttachment }) {
  const [preview, setPreview] = useState(false)
  const Icon = attachment.kind === 'image' ? FileImage : FileText
  return (
    <div className="rounded-[8px] border border-border-light bg-card">
      <button
        type="button"
        aria-expanded={preview}
        onClick={() => setPreview((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left transition-colors hover:bg-secondary/40"
      >
        <Icon className="size-3.5 flex-none text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-[11px]">{attachment.name}</span>
        <Pill tone="neutral">{attachment.slot}</Pill>
        <span className="flex-none text-[10px] tabular-nums text-muted-foreground">{attachment.size}</span>
        <span className="flex-none text-[10px] text-status-blue">{preview ? '收起预览' : '预览'}</span>
      </button>
      {preview ? (
        <div className="border-t border-border-light px-2 py-2">
          <div className="flex h-[132px] items-center justify-center rounded-[6px] border border-dashed border-border bg-secondary/40">
            <div className="text-center">
              <Icon className="mx-auto size-5 text-muted-foreground" />
              <div className="mt-1 text-[10.5px] text-muted-foreground">
                {attachment.kind === 'image' ? '图片预览占位' : 'PDF 首页预览占位'}
              </div>
              <div className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">
                {attachment.pages} 页 · 第 1 页 / {attachment.pages}
              </div>
            </div>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span>识别结果：{attachment.slot}</span>
            <span className="ml-auto text-status-blue">下载原件</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}

/** 邮箱配置弹窗：轮询间隔 / 文件夹 / 发件人白名单 */
function MailboxConfigDrawer({
  addr,
  onClose,
  onSave,
  saved,
}: {
  addr: string | null
  onClose: () => void
  onSave: (cfg: ScanMailboxConfig) => void
  /** 已保存过的配置（优先于演示默认值） */
  saved: Record<string, ScanMailboxConfig>
}) {
  const base = addr ? (saved[addr] ?? DEMO_X2_SCAN_MAILBOXES.find((m) => m.addr === addr)) ?? null : null
  return (
    <MailboxConfigForm key={base?.addr ?? 'none'} base={base} onClose={onClose} onSave={onSave} />
  )
}

function MailboxConfigForm({
  base,
  onClose,
  onSave,
}: {
  base: ScanMailboxConfig | null
  onClose: () => void
  onSave: (cfg: ScanMailboxConfig) => void
}) {
  const [interval, setInterval] = useState(base?.interval ?? '')
  const [folder, setFolder] = useState(base?.folder ?? '')
  const [whitelist, setWhitelist] = useState(base?.whitelist ?? '')

  return (
    <DetailDrawer
      open={base != null}
      onClose={onClose}
      title="邮箱扫描设置"
      subtitle={base?.addr}
      badge={<Pill tone="green">监听中</Pill>}
      width={460}
      footer={
        base ? (
          <>
            <ActionButton
              dark
              onClick={() => onSave({ ...base, interval, folder, whitelist })}
            >
              保存配置
            </ActionButton>
            <ActionButton onClick={onClose}>取消</ActionButton>
          </>
        ) : null
      }
    >
      {base ? (
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-interval">
              轮询间隔
            </label>
            <select
              id="x2-interval"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
            >
              {DEMO_X2_SCAN_INTERVALS.map((i) => (
                <option key={i} value={i}>
                  每 {i}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-muted-foreground">法院送达邮箱建议 1 分钟，其他 5 分钟足够。</p>
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-folder">
              监听文件夹
            </label>
            <input
              id="x2-folder"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">多个用 / 分隔，如 INBOX / 送达文书。</p>
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-whitelist">
              发件人白名单
            </label>
            <textarea
              id="x2-whitelist"
              rows={3}
              value={whitelist}
              onChange={(e) => setWhitelist(e.target.value)}
              className="mt-1 w-full resize-y rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[11px] leading-[1.7] outline-none focus:border-foreground"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              只处理白名单里的发件人；其余邮件仍会留档，但不自动归案。
            </p>
          </div>

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">当前账号</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              {base.note} · 本月已扫 {base.count} 封
            </p>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}

/** 手动归案弹窗：搜案件 → 选中 → 选归入槽位 → 确认（带进度） */
function AssignDrawer({
  subject,
  onClose,
  assign,
}: {
  subject: string | null
  onClose: () => void
  assign: ReturnType<typeof useStageAction<void>>
}) {
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<AssignCandidate | null>(null)
  const [slot, setSlot] = useState('')

  const open = subject != null
  const candidates = DEMO_X2_ASSIGN_CANDIDATES.filter(
    (c) => query.trim() === '' || c.name.includes(query.trim()) || c.caseNo.includes(query.trim()),
  )
  const running = assign.phase === 'running'

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      title="指定归属"
      subtitle={subject ?? undefined}
      badge={assign.phase === 'done' ? <Pill tone="green">已归案</Pill> : <Pill tone="yellow">待人工</Pill>}
      width={480}
      footer={
        <>
          <ActionButton
            dark
            disabled={!picked || slot === '' || running}
            onClick={() => {
              if (picked) void assign.execute()
            }}
          >
            {running ? `归案中 ${assign.percent}%` : '确认归案'}
          </ActionButton>
          <ActionButton onClick={onClose}>取消</ActionButton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {/* 第 1 步：搜案件 */}
        <div>
          <div className="text-[10px] text-muted-foreground">1. 搜案件名称或案号</div>
          <input
            aria-label="搜案件名称或案号"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPicked(null)
              setSlot('')
            }}
            placeholder="输入案件名称 / 案号 / 当事人"
            className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
          />
          <ul className="mt-1.5 max-h-[190px] overflow-y-auto rounded-[8px] border border-border-light">
            {candidates.map((c) => {
              const selected = picked?.name === c.name
              return (
                <li key={c.name}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      setPicked(c)
                      setSlot(c.slots[0] ?? '')
                    }}
                    className={cn(
                      'flex w-full items-start gap-2 px-2.5 py-2 text-left transition-colors hover:bg-secondary/50',
                      selected && 'bg-secondary',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-[3px] size-3 flex-none rounded-full border',
                        selected ? 'border-foreground bg-foreground' : 'border-border bg-card',
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11.5px] font-medium">{c.name}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                        {c.caseNo} · {c.court}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{c.party}</span>
                    </span>
                  </button>
                </li>
              )
            })}
            {candidates.length === 0 ? (
              <li className="px-2.5 py-3 text-center text-[10.5px] text-muted-foreground">没有匹配的案件</li>
            ) : null}
          </ul>
        </div>

        {/* 第 2 步：选槽位 */}
        <div>
          <div className="text-[10px] text-muted-foreground">2. 选归入槽位</div>
          {picked ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {picked.slots.map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={slot === s}
                  onClick={() => setSlot(s)}
                  className={cn(
                    'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
                    slot === s
                      ? 'border-foreground bg-foreground font-semibold text-background'
                      : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-[10.5px] text-muted-foreground">先选一个案件，这里会列出它的槽位</p>
          )}
        </div>

        {/* 第 3 步：确认，带进度 */}
        <div>
          <div className="text-[10px] text-muted-foreground">3. 确认并归案</div>
          <InsetBlock className="mt-1">
            <div className="text-[11px]">
              {picked && slot ? (
                <>
                  「{subject}」→ <span className="font-medium">{picked.name}</span> · {slot}
                </>
              ) : (
                <span className="text-muted-foreground">尚未选齐案件与槽位</span>
              )}
            </div>
            {assign.phase !== 'idle' ? (
              <div className="mt-2">
                <div className="h-[5px] overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn(
                      'h-full rounded-full transition-[width] duration-200',
                      assign.phase === 'done' ? 'bg-status-green' : 'bg-foreground',
                    )}
                    style={{ width: `${assign.percent}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span className="min-w-0 flex-1 truncate">
                    {assign.phase === 'done'
                      ? `已归入「${picked?.name ?? ''}」· ${slot}，缺件检测已重跑`
                      : assign.progress || '准备中…'}
                  </span>
                  <span className="tabular-nums">{assign.percent}%</span>
                </div>
                {assign.log.length > 0 ? (
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {assign.log.slice(-3).map((l) => (
                      <li key={`${l.at}-${l.text}`} className="truncate text-[10px] text-muted-foreground">
                        <span className="tabular-nums opacity-70">{l.at}</span> {l.text}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </InsetBlock>
        </div>
      </div>
    </DetailDrawer>
  )
}
