/**
 * ③ 缺件 —— 系统发现遗漏，自动通知客户补什么
 *
 * 这一步的价值不在「列出来」，而在**通知发出去、客户补齐了、系统认出来了**。
 * 所以版面围绕「每条缺件的通知状态」展开：发了没、走了哪个渠道、客户回了什么。
 *
 * 补件是个**来回拉扯的过程**（发通知 → 已读 → 催办 → 上传 → 认出来），
 * 所以清单之外还要能看每一条的完整沟通过程、能勾选批量催办、能改话术、
 * 能按来源分组 —— 否则律师只能一条条点开猜客户到底卡在哪一步。
 */

import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  CheckSquare,
  Clock,
  FileText,
  Mail,
  MessageSquare,
  Pencil,
  Send,
  Smartphone,
  Square,
  Upload,
  Users,
} from 'lucide-react'
import { useState } from 'react'

import {
  DEMO_GAP_NOTICES,
  DEMO_GAP_RECEIVED,
  DEMO_X2_GAP_SCRIPTS,
  DEMO_X2_GAP_SOURCES,
  DEMO_X2_GAP_TIMELINE,
  type GapSource,
  type GapTimelineKind,
} from '../demo-data'
import { StageActionCard } from './StageActionCard'
import { DetailDrawer } from './DetailDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton, InsetBlock, KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

const CHANNEL_ICON: Record<string, typeof Mail> = {
  '短信 + 邮件': Mail,
  微信: MessageSquare,
  邮件: Mail,
}

/** 客户往来时间线里每类事件的图标（渠道图标） */
const TIMELINE_ICON: Record<GapTimelineKind, typeof Mail> = {
  system: Bell,
  sms: Smartphone,
  mail: Mail,
  wechat: MessageSquare,
  customer: Upload,
  recognize: CheckSquare,
}

/** 分组切换项：全部 + 四个来源 */
const SOURCE_TABS: Array<'全部' | GapSource> = ['全部', '合同类', '催收类', '身份类', '担保类']

function sourceOf(item: string): GapSource {
  return DEMO_X2_GAP_SOURCES.find((s) => s.item === item)?.source ?? '合同类'
}

export function GapPanel() {
  /** 点开的缺件项 */
  const [picked, setPicked] = useState<string | null>(null)
  /** 演示：手动关闭的缺件（律师判断这条不用补） */
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  /** 批量操作勾选的缺件项 */
  const [checked, setChecked] = useState<Set<string>>(new Set())
  /** 缺件按来源分组 */
  const [sourceTab, setSourceTab] = useState<'全部' | GapSource>('全部')
  /** 演示：批量操作回执 */
  const [batchNote, setBatchNote] = useState('')
  /** 可编辑的通知话术（按 id 覆盖默认正文） */
  const [scripts, setScripts] = useState<Record<string, string>>({})
  /** 正在编辑的话术模板 */
  const [editing, setEditing] = useState<string | null>(null)
  /** 编辑中的草稿 */
  const [draft, setDraft] = useState('')

  /* 重新检测缺件：演示时会话可反复触发 */
  const detect = useStageAction({
    steps: [
      { text: '加载借贷类必备清单（6 项）', ms: 400 },
      { text: '逐份材料比对槽位', ms: 900, parallel: ['合同类', '借据类', '还款类', '催收类', '身份类'] },
      { text: '催收记录：止于 2025-06，缺最近 12 个月 → 硬阻塞', ms: 500 },
      { text: '抵押物权属证明：未见不动产权证 → 硬阻塞', ms: 450 },
      { text: '共同借款人身份证明：2 人仅见 1 人 → 硬阻塞', ms: 450 },
      { text: '还款账户流水：止于 2026-04 → 建议补', ms: 400 },
      {
        text: '生成补件清单',
        ms: 600,
        confirm: '共 5 项缺件，其中 3 项硬阻塞。确认全部发给客户，还是先发硬阻塞的 3 项？',
      },
      {
        text: '推送客户（短信 + 邮件）',
        ms: 800,
        retry: { times: 1, delay: 1200, reason: '短信网关超时，重试中' },
      },
      { text: '同步通知主办律师', ms: 350 },
    ],
    toSummary: () => '发现 5 项缺件（3 项硬阻塞），已通过短信+邮件推送给客户经理',
  })
  /* 催办：给还没补的项再发一次 */
  const remind = useStageAction({
    steps: [
      { text: '统计仍未补齐项：2 项', ms: 320 },
      { text: '发送催办短信（含免登录上传链接）', ms: 480 },
      { text: '同步通知主办律师', ms: 280 },
    ],
    toSummary: () => '已向客户发送催办提醒，2 项待补',
  })

  const blockers = DEMO_GAP_NOTICES.filter((g) => g.severity === 'blocker')
  const received = DEMO_GAP_NOTICES.filter((g) => g.status === 'received')
  const waiting = DEMO_GAP_NOTICES.filter((g) => g.status !== 'received')
  const blockerOpen = blockers.filter((g) => g.status !== 'received').length

  const visible = sourceTab === '全部' ? DEMO_GAP_NOTICES : DEMO_GAP_NOTICES.filter((g) => sourceOf(g.item) === sourceTab)
  /** 勾选里还没补齐的那些 —— 批量催办只该发给它们 */
  const checkedOpen = [...checked].filter((k) => DEMO_GAP_NOTICES.some((g) => g.item === k && g.status !== 'received'))
  const allChecked = visible.length > 0 && visible.every((g) => checked.has(g.item))

  const toggleOne = (item: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(item)) next.delete(item)
      else next.add(item)
      return next
    })
  const toggleAll = () =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (allChecked) visible.forEach((g) => next.delete(g.item))
      else visible.forEach((g) => next.add(g.item))
      return next
    })

  /* 批量催办：把勾选里未补齐的一次性催出去 */
  const batchRemind = useStageAction({
    steps: [
      { text: '汇总勾选项', ms: 260, fixed: true },
      { text: '发送催办短信（含免登录上传链接）', ms: 620 },
      { text: '同步给客户经理与主办律师', ms: 300 },
    ],
    toSummary: () => '已批量催办',
  })
  /* 批量标记已收：行政确认纸质件到了，不用等系统识别 */
  const batchReceive = useStageAction({
    steps: [
      { text: '核对纸质件签收记录', ms: 420 },
      { text: '写入槽位并标记「已收」', ms: 560 },
      { text: '重跑缺件检测', ms: 480 },
    ],
    toSummary: () => '已批量标记已收',
  })
  const batchRunning = batchRemind.phase === 'running' || batchReceive.phase === 'running'

  const timelineOf = (item: string) => DEMO_X2_GAP_TIMELINE.filter((t) => t.item === item)

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="重新检测缺件并通知客户"
        desc="系统拿已转换的正文比对必备清单，缺什么当场列出来。硬阻塞项会随通知一起发出去，客户点短信里的免登录链接就能补。"
        actionLabel="检测并通知"
        hint="5 项缺件 · 约 2.7 秒"
        state={detect}
        execute={() => void detect.execute()}
        reset={detect.reset}
        confirm={detect.confirm}
      />

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

          {/* 逐项缺件：按来源分组 + 可勾选批量操作 */}
          <WorkCard padded={false}>
            <div className="flex flex-wrap items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="缺件清单" hint="硬阻塞项不补齐无法送法院" className="w-full" action={
                <span className="text-[10.5px] tabular-nums text-muted-foreground">
                  {sourceTab === '全部' ? `${DEMO_GAP_NOTICES.length} 项` : `${visible.length} / ${DEMO_GAP_NOTICES.length} 项`}
                </span>
              } />
            </div>

            {/* 来源分组切换 */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-border-light px-5 py-2.5">
              <span className="text-[10.5px] text-muted-foreground">按来源</span>
              {SOURCE_TABS.map((tab) => {
                const n = tab === '全部' ? DEMO_GAP_NOTICES.length : DEMO_GAP_NOTICES.filter((g) => sourceOf(g.item) === tab).length
                return (
                  <button
                    key={tab}
                    type="button"
                    aria-pressed={sourceTab === tab}
                    onClick={() => setSourceTab(tab)}
                    className={cn(
                      'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
                      sourceTab === tab
                        ? 'border-foreground bg-foreground font-semibold text-background'
                        : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
                    )}
                  >
                    {tab}
                    <span className={cn('ml-1 tabular-nums', sourceTab === tab ? 'opacity-70' : 'text-muted-foreground')}>{n}</span>
                  </button>
                )
              })}
            </div>

            {/* 批量操作条 */}
            <div className="flex flex-wrap items-center gap-2 border-b border-border-light bg-secondary/25 px-5 py-2">
              <button
                type="button"
                onClick={toggleAll}
                aria-label={allChecked ? '取消全选' : '全选当前分组'}
                className="flex items-center gap-1 text-[11px] text-secondary-foreground"
              >
                {allChecked ? (
                  <CheckSquare className="size-3.5 text-foreground" />
                ) : (
                  <Square className="size-3.5 text-muted-foreground" />
                )}
                {allChecked ? '取消全选' : '全选'}
              </button>
              <span className="text-[10.5px] tabular-nums text-muted-foreground">
                已选 {checkedOpen.length} 项
              </span>
              <div className="ml-auto flex items-center gap-1.5">
                <ActionButton
                  sm
                  dark
                  disabled={checkedOpen.length === 0 || batchRunning}
                  onClick={() => {
                    setBatchNote('')
                    void batchRemind.execute().then(() =>
                      setBatchNote(`已批量催办 ${checkedOpen.length} 项：${checkedOpen.join('、')}`),
                    )
                  }}
                >
                  {batchRemind.phase === 'running' ? '催办中…' : '批量催办'}
                </ActionButton>
                <ActionButton
                  sm
                  disabled={checkedOpen.length === 0 || batchRunning}
                  onClick={() => {
                    setBatchNote('')
                    void batchReceive.execute().then(() =>
                      setBatchNote(`已批量标记已收 ${checkedOpen.length} 项：${checkedOpen.join('、')}`),
                    )
                  }}
                >
                  {batchReceive.phase === 'running' ? '处理中…' : '批量标记已收'}
                </ActionButton>
                {checked.size > 0 ? (
                  <ActionButton sm onClick={() => { setChecked(new Set()); setBatchNote('') }}>
                    清空
                  </ActionButton>
                ) : null}
              </div>
            </div>
            {batchNote ? (
              <div className="flex items-center gap-1.5 border-b border-border-light bg-status-green-bg/40 px-5 py-1.5 text-[10.5px] text-status-green">
                <CheckCircle2 className="size-3" />
                {batchNote}
              </div>
            ) : null}

            <ul className="divide-y divide-border-light">
              {visible.map((g) => {
                const Icon = CHANNEL_ICON[g.channel] ?? Mail
                const done = g.status === 'received'
                const isChecked = checked.has(g.item)
                return (
                  <li
                    key={g.item}
                    onClick={() => setPicked(g.item)}
                    className={cn(
                      'flex cursor-pointer items-start gap-2.5 px-5 py-3 transition-colors hover:bg-secondary/40',
                      isChecked && 'bg-secondary/50',
                    )}
                  >
                    <button
                      type="button"
                      aria-label={`勾选 ${g.item}`}
                      aria-pressed={isChecked}
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleOne(g.item)
                      }}
                      className="mt-[2px] flex-none text-muted-foreground hover:text-foreground"
                    >
                      {isChecked ? (
                        <CheckSquare className="size-3.5 text-foreground" />
                      ) : (
                        <Square className="size-3.5" />
                      )}
                    </button>

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
                        <span className="rounded-[4px] border border-border-light bg-background px-1 text-[9.5px] text-muted-foreground">
                          {sourceOf(g.item)}
                        </span>
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
                      <div className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
                        <FileText className="size-2.5" />
                        {timelineOf(g.item).length} 条往来记录 · 点开看完整沟通
                      </div>
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
            {visible.length === 0 ? (
              <div className="px-5 py-6 text-center text-[11.5px] text-muted-foreground">
                「{sourceTab}」下没有待补材料
              </div>
            ) : null}
          </WorkCard>

          {/* 通知模板：话术可编辑 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="通知模板" hint="按缺件等级自动选话术 · 可编辑" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_X2_GAP_SCRIPTS.map((t) => {
                const body = scripts[t.id] ?? t.body
                const isEditing = editing === t.id
                return (
                  <li key={t.id} className="px-5 py-2.5">
                    <div className="flex items-center gap-2">
                      <Pill tone={t.severity === '硬阻塞' ? 'red' : t.severity === '催办' ? 'yellow' : 'blue'}>{t.severity}</Pill>
                      <span className="text-[12px] font-medium">{t.title}</span>
                      {scripts[t.id] !== undefined ? (
                        <span className="rounded-[4px] border border-status-blue/40 bg-status-blue-bg px-1 text-[9.5px] text-status-blue">
                          已改过
                        </span>
                      ) : null}
                      <div className="ml-auto flex items-center gap-1.5">
                        {isEditing ? (
                          <>
                            <ActionButton
                              sm
                              dark
                              onClick={() => {
                                setScripts((prev) => ({ ...prev, [t.id]: draft }))
                                setEditing(null)
                              }}
                            >
                              保存
                            </ActionButton>
                            <ActionButton sm onClick={() => setEditing(null)}>
                              取消
                            </ActionButton>
                          </>
                        ) : (
                          <ActionButton
                            sm
                            title="改这段话术，之后发送用新版本"
                            onClick={() => {
                              setEditing(t.id)
                              setDraft(body)
                            }}
                          >
                            <Pencil className="size-3" />
                            编辑话术
                          </ActionButton>
                        )}
                      </div>
                    </div>
                    {isEditing ? (
                      <textarea
                        aria-label={`编辑「${t.title}」话术`}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={4}
                        className="mt-1.5 w-full resize-y rounded-[8px] border border-border bg-background px-2.5 py-2 text-[11px] leading-[1.7] text-secondary-foreground outline-none focus:border-foreground"
                      />
                    ) : (
                      <div className="mt-0.5 text-[10.5px] leading-[1.7] text-muted-foreground">{body}</div>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span>占位符 {'{n}'} {'{list}'} {'{days}'} {'{link}'} 发送时自动替换</span>
                      {scripts[t.id] !== undefined ? (
                        <button
                          type="button"
                          onClick={() =>
                            setScripts((prev) => {
                              const next = { ...prev }
                              delete next[t.id]
                              return next
                            })
                          }
                          className="ml-auto text-status-blue hover:underline"
                        >
                          恢复默认
                        </button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
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
                <div className="mt-2">
                  <ActionButton sm dark disabled={remind.phase === 'running'} onClick={() => void remind.execute()}>
                    {remind.phase === 'running' ? '发送中…' : '催办这 2 项'}
                  </ActionButton>
                </div>
                {remind.phase === 'done' ? (
                  <div className="mt-1.5 text-[10.5px] text-status-green">{remind.summary}</div>
                ) : null}
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

      <GapDrawer
        item={picked}
        onClose={() => setPicked(null)}
        dismissed={dismissed}
        onDismiss={(k) => {
          setDismissed((prev) => new Set(prev).add(k))
          setPicked(null)
        }}
      />
    </div>
  )
}

/** 缺件详情：能看完整沟通时间线、判定依据、改等级、单独重发、或判定不用补 */
function GapDrawer({
  item,
  onClose,
  dismissed,
  onDismiss,
}: {
  item: string | null
  onClose: () => void
  dismissed: Set<string>
  onDismiss: (item: string) => void
}) {
  const g = item ? DEMO_GAP_NOTICES.find((x) => x.item === item) : null
  const isDismissed = g ? dismissed.has(g.item) : false
  const timeline = g ? DEMO_X2_GAP_TIMELINE.filter((t) => t.item === g.item) : []

  return (
    <DetailDrawer
      open={g != null}
      onClose={onClose}
      title={g?.item ?? ''}
      subtitle={g ? `${g.severity === 'blocker' ? '硬阻塞' : '一般'} · ${sourceOf(g.item)} · ${g.channel} · ${g.sentAt}` : undefined}
      badge={
        g ? (
          <Pill tone={isDismissed ? 'neutral' : g.status === 'received' ? 'green' : g.status === 'pending' ? 'yellow' : 'red'}>
            {isDismissed ? '已忽略' : g.status === 'received' ? '已补齐' : g.status === 'pending' ? '已发出' : '等待客户'}
          </Pill>
        ) : null
      }
      footer={
        g ? (
          <>
            <ActionButton dark onClick={onClose}>
              重新发送通知
            </ActionButton>
            <ActionButton onClick={() => onDismiss(g.item)}>判定不用补</ActionButton>
          </>
        ) : null
      }
    >
      {g ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="缺件原因">{g.reason}</KeyValueRow>
            <KeyValueRow label="等级">
              <span className={g.severity === 'blocker' ? 'text-status-red' : 'text-muted-foreground'}>
                {g.severity === 'blocker' ? '硬阻塞 —— 不补齐无法送法院' : '一般 —— 不影响先立案'}
              </span>
            </KeyValueRow>
            <KeyValueRow label="来源">{sourceOf(g.item)}</KeyValueRow>
            <KeyValueRow label="通知渠道">{g.channel}</KeyValueRow>
            <KeyValueRow label="发出时间">{g.sentAt}</KeyValueRow>
            <KeyValueRow label="客户回复">{g.reply}</KeyValueRow>
          </dl>

          {/* 客户往来时间线：这一条缺件的完整沟通过程 */}
          <InsetBlock>
            <div className="flex items-center gap-1.5">
              <Users className="size-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">客户往来时间线（{timeline.length} 条）</span>
            </div>
            {timeline.length === 0 ? (
              <p className="mt-1.5 text-[10.5px] text-muted-foreground">还没有往来记录</p>
            ) : (
              <ol className="mt-2 flex flex-col">
                {timeline.map((t, i) => {
                  const Icon = TIMELINE_ICON[t.kind]
                  const last = i === timeline.length - 1
                  return (
                    <li key={`${t.at}-${t.title}`} className="flex gap-2.5">
                      <div className="flex flex-none flex-col items-center">
                        <span
                          className={cn(
                            'grid size-[18px] place-items-center rounded-full border',
                            t.kind === 'recognize'
                              ? 'border-status-green/40 bg-status-green-bg text-status-green'
                              : t.kind === 'customer'
                                ? 'border-status-blue/40 bg-status-blue-bg text-status-blue'
                                : 'border-border bg-secondary text-muted-foreground',
                          )}
                        >
                          <Icon className="size-2.5" />
                        </span>
                        <span className={cn('mt-1 w-px flex-1 bg-border-light', last && 'hidden')} />
                      </div>
                      <div className="min-w-0 pb-3">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <span className="text-[11.5px] font-medium">{t.title}</span>
                          <span className="text-[10px] tabular-nums text-muted-foreground">{t.at}</span>
                          <span className="rounded-[4px] border border-border-light bg-card px-1 text-[9.5px] text-muted-foreground">
                            {t.channel}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">{t.detail}</div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            )}
          </InsetBlock>

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">系统判定依据</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              {g.severity === 'blocker'
                ? '这项材料属于「借贷类必备清单」中的必需项。信源比对时在已转换的 markdown 正文里没找到对应内容，且该清单项在合同条款中明确要求提供。'
                : '这项材料不在必备清单里，但同类案件基本都会提交。缺失不会导致立案被拒，但可能在审理中被法官要求补充。'}
            </p>
          </InsetBlock>

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">发给客户的话术</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              【{g.severity === 'blocker' ? '影响立案的缺件' : '建议补充的材料'}】
              您好，关于「{g.item}」还需要补充：{g.reason}。
              请点此链接上传（免登录）：https://…/u/xxxx  或直接微信发给经办律师。
            </p>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
