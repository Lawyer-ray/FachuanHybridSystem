/**
 * 关厂清盘 · 阶段抽屉（点阶段行打开）
 *
 * 阶段表以前是「死」的：一行阶段只能看名字和状态，律师想追问「这一步到哪了、
 * 凭什么算完成、客户哪天点的头」没有任何入口。抽屉把过程证据摊开成四个页签：
 *
 *   阶段详情 → 起止 / 负责人 / 验收结论 / 客户确认
 *   验收标准 → 逐条标准 + 是否满足 + 谁来认定
 *   交付物   → 每份交付物的页数 / 上传时间 / 上传人 / 版本历史
 *   变更记录 → 谁在什么时候把什么改成了什么（计划日期的每一次挪动都在这里）
 *
 * 三个动作都落在**本地状态**：标记完成 / 重新打开 / 调整计划日期。演示环境后端
 * 没有关厂清盘的阶段契约，这里不假装写入——改完立即回显，并在页脚写清口径。
 */

import { useState } from 'react'
import { BadgeCheck, CalendarClock, CheckCircle2, RotateCcw, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  DEMO_NL1_CHANGE_LOGS,
  DEMO_NL1_CLIENT_CONFIRMS,
  DEMO_NL1_DOC_HISTORY,
  DEMO_NL1_GATE_RULES,
  type DemoNl1ClientConfirm,
  type DemoDeliverable,
} from '../../demo-nonlit'
import { BlockHead, EmptyHint, Inset, MiniButton, SpecialDrawer, TonePill, type Tone } from './special-bits'
import { SPECIAL_DRAWER_TABS, versionRowsOf, type SpecialDrawerTab } from './special-liquidation-model'

/** 抽屉里操作的那个阶段（由调用方从阶段列表挑出来） */
export interface DrawerPhase {
  id: string
  seq: string
  name: string
  planStart: string
  planEnd: string
  status: 'done' | 'doing' | 'todo'
  criterion: string
  deliverables: DemoDeliverable[]
  /** 负责人（演示数据里不存，用甘特图那一份） */
  owner: string
}

const STATUS_TEXT: Record<DrawerPhase['status'], string> = { done: '已完成', doing: '进行中', todo: '未开始' }
const STATUS_TONE: Record<DrawerPhase['status'], Tone> = { done: 'green', doing: 'blue', todo: 'neutral' }
const VERDICT_TONE: Record<DemoNl1ClientConfirm['verdict'], Tone> = {
  确认: 'green',
  附条件确认: 'yellow',
  不确认: 'red',
}

export function SpecialPhaseDrawer({
  phase,
  open,
  onClose,
  onComplete,
  onReopen,
  onShiftPlan,
}: {
  /** null = 抽屉关闭 */
  phase: DrawerPhase | null
  open: boolean
  onClose: () => void
  onComplete: (id: string) => void
  onReopen: (id: string) => void
  /** 计划起止各挪 n 天（负数提前） */
  onShiftPlan: (id: string, days: number) => void
}) {
  const [tab, setTab] = useState<SpecialDrawerTab>('detail')
  if (!phase) return null

  const changes = DEMO_NL1_CHANGE_LOGS.filter((c) => c.phase === phase.name)
  const confirms = DEMO_NL1_CLIENT_CONFIRMS.filter((c) => c.phase === phase.name)
  const signed = phase.deliverables.filter((d) => d.status === 'done').length
  const gate = DEMO_NL1_GATE_RULES.find((g) => g.id === 'g2')

  return (
    <SpecialDrawer
      open={open}
      onClose={onClose}
      title={`${phase.seq} ${phase.name}`}
      subtitle={`计划 ${phase.planStart} 至 ${phase.planEnd} · 负责人 ${phase.owner}`}
      badge={<TonePill tone={STATUS_TONE[phase.status]}>{STATUS_TEXT[phase.status]}</TonePill>}
      footer={
        <>
          {phase.status === 'done' ? (
            <MiniButton onClick={() => onReopen(phase.id)} title="把阶段退回「进行中」，交付物与确认记录都保留">
              <RotateCcw className="size-3" /> 重新打开
            </MiniButton>
          ) : (
            <MiniButton onClick={() => onComplete(phase.id)} title="标记完成前会先看验收标准是否满足">
              <CheckCircle2 className="size-3" /> 标记完成
            </MiniButton>
          )}
          <MiniButton onClick={() => onShiftPlan(phase.id, 7)} title="计划起止整体后移 7 天">
            <CalendarClock className="size-3" /> 计划后移 7 天
          </MiniButton>
          <MiniButton onClick={() => onShiftPlan(phase.id, -3)} title="计划起止整体提前 3 天">
            提前 3 天
          </MiniButton>
          <span className="ml-auto text-[10px] text-muted-foreground">演示数据 · 改动只在本页生效</span>
        </>
      }
    >
      {/* 页签 */}
      <div className="mb-3 flex flex-wrap gap-1">
        {SPECIAL_DRAWER_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              'rounded-[7px] border px-2.5 py-[3px] text-[11.5px] font-[550] transition-colors',
              tab === t.id
                ? 'border-foreground bg-foreground text-background'
                : 'border-border-light bg-background text-muted-foreground hover:bg-secondary',
            )}
          >
            {t.label}
            {t.id === 'changes' ? ` ${changes.length}` : ''}
            {t.id === 'docs' ? ` ${phase.deliverables.length}` : ''}
          </button>
        ))}
      </div>

      {tab === 'detail' ? (
        <div className="flex flex-col gap-2.5">
          <Inset>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <Field k="当前状态" v={STATUS_TEXT[phase.status]} />
              <Field k="负责人" v={phase.owner} />
              <Field k="计划开始" v={phase.planStart} />
              <Field k="计划结束" v={phase.planEnd} />
              <Field k="交付物" v={`${phase.deliverables.length} 份（${signed} 份已定稿）`} />
              <Field k="变更次数" v={`${changes.length} 次`} />
            </div>
          </Inset>

          <div>
            <BlockHead title="验收口径" hint="到什么程度算这一步做完" />
            <Inset className="text-[12px] leading-[1.65] text-secondary-foreground">{phase.criterion}</Inset>
          </div>

          <div>
            <BlockHead title="客户确认" hint={`${confirms.length} 条`} />
            {confirms.length === 0 ? (
              <EmptyHint>本阶段还没有客户确认记录，推进前需要补一次书面确认</EmptyHint>
            ) : (
              <div className="flex flex-col gap-1.5">
                {confirms.map((c) => (
                  <Inset key={c.id}>
                    <div className="flex items-center gap-2">
                      <TonePill tone={VERDICT_TONE[c.verdict]}>{c.verdict}</TonePill>
                      <span className="text-[10.5px] tabular-nums text-muted-foreground">{c.at}</span>
                      <span className="ml-auto truncate text-[10.5px] text-muted-foreground">{c.channel}</span>
                    </div>
                    <div className="mt-1 text-[12px] leading-[1.6]">{c.what}</div>
                    <div className="mt-0.5 text-[10.5px] text-muted-foreground">{c.by}</div>
                  </Inset>
                ))}
              </div>
            )}
          </div>

          <div>
            <BlockHead title="最近一次变更" />
            {changes.length === 0 ? (
              <EmptyHint>本阶段没有变更记录</EmptyHint>
            ) : (
              <Inset className="bg-secondary/25 text-[11.5px] leading-[1.65]">
                <span className="tabular-nums text-muted-foreground">{changes[0]!.at}</span>
                <span className="mx-1.5 text-border">·</span>
                {changes[0]!.who}
                <span className="mx-1.5 text-border">·</span>
                {changes[0]!.kind}：<span className="text-muted-foreground line-through">{changes[0]!.from}</span> →{' '}
                <span className="font-medium">{changes[0]!.to}</span>
              </Inset>
            )}
          </div>
        </div>
      ) : null}

      {tab === 'acceptance' ? (
        <div className="flex flex-col gap-2">
          <Inset className="border-status-blue/40 bg-status-blue-bg/40">
            <div className="flex items-start gap-2">
              <BadgeCheck className="mt-[2px] size-3.5 flex-none text-status-blue" />
              <div>
                <div className="text-[11.5px] font-medium">本阶段的验收标准</div>
                <p className="mt-0.5 text-[12px] leading-[1.65]">{phase.criterion}</p>
              </div>
            </div>
          </Inset>

          <AcceptanceRow
            label="全部交付物已定稿"
            detail={`${signed} / ${phase.deliverables.length} 份已定稿`}
            ok={phase.deliverables.length > 0 && signed === phase.deliverables.length}
            fix="走「交付物清单」页签逐份定稿，草稿状态的文件不计入验收"
          />
          <AcceptanceRow
            label="职工安置协议签署率达标"
            detail={gate?.detail ?? '—'}
            ok={!gate || gate.ok}
            fix={gate?.fix}
          />
          <AcceptanceRow
            label="客户已书面确认"
            detail={
              confirms.some((c) => c.verdict === '确认')
                ? `已有 ${confirms.filter((c) => c.verdict === '确认').length} 条确认记录`
                : '尚无「确认」结论的客户记录'
            }
            ok={confirms.some((c) => c.verdict === '确认')}
            fix="附条件确认与不确认都不算通过，需要拿到无保留的书面确认"
          />
          <div className="mt-1 text-[10.5px] leading-[1.6] text-muted-foreground">
            三条标准全部满足才能「标记完成」；系统只提示，不替律师决定。
          </div>
        </div>
      ) : null}

      {tab === 'docs' ? <DocsTab deliverables={phase.deliverables} /> : null}

      {tab === 'changes' ? (
        <div className="flex flex-col gap-1.5">
          {changes.length === 0 ? (
            <EmptyHint>本阶段没有变更记录</EmptyHint>
          ) : (
            changes.map((c) => (
              <Inset key={c.id}>
                <div className="flex items-center gap-2">
                  <TonePill tone="blue">{c.kind}</TonePill>
                  <span className="text-[10.5px] tabular-nums text-muted-foreground">{c.at}</span>
                  <span className="text-[10.5px] text-muted-foreground">{c.who}</span>
                </div>
                <div className="mt-1 text-[12px] leading-[1.6]">
                  <span className="text-muted-foreground line-through">{c.from}</span>
                  <span className="mx-1 text-border">→</span>
                  <span className="font-[550]">{c.to}</span>
                </div>
                <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">原因：{c.reason}</div>
              </Inset>
            ))
          )}
        </div>
      ) : null}
    </SpecialDrawer>
  )
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-[52px] flex-none text-[10.5px] text-muted-foreground">{k}</span>
      <span className="min-w-0 truncate text-[12px] font-[550] tabular-nums">{v}</span>
    </div>
  )
}

/** 一条验收标准的判定（过 / 不过 + 怎么补） */
function AcceptanceRow({ label, detail, ok, fix }: { label: string; detail: string; ok: boolean; fix?: string }) {
  return (
    <Inset className={cn(ok ? 'border-status-green/40 bg-status-green-bg/30' : 'border-status-yellow/50 bg-status-yellow-bg/30')}>
      <div className="flex items-start gap-2">
        {ok ? (
          <CheckCircle2 className="mt-[2px] size-3.5 flex-none text-status-green" />
        ) : (
          <XCircle className="mt-[2px] size-3.5 flex-none text-status-yellow" />
        )}
        <div className="min-w-0">
          <div className="text-[12px] font-[550]">{label}</div>
          <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">{detail}</div>
          {!ok && fix ? <div className="mt-1 text-[10.5px] leading-[1.6] text-status-yellow">怎么办：{fix}</div> : null}
        </div>
      </div>
    </Inset>
  )
}

/** 交付物页签：每份交付物的元信息 + 版本历史 */
function DocsTab({ deliverables }: { deliverables: DemoDeliverable[] }) {
  const [expanded, setExpanded] = useState<string | null>(deliverables[0]?.name ?? null)
  if (deliverables.length === 0) return <EmptyHint>本阶段还没有交付物。设计阶段时可以先登记计划项。</EmptyHint>

  return (
    <div className="flex flex-col gap-1.5">
      {deliverables.map((d) => {
        const open = expanded === d.name
        const versions = versionRowsOf(d.name, DEMO_NL1_DOC_HISTORY)
        return (
          <div key={d.name} className="rounded-[9px] border border-border-light bg-background">
            <button
              type="button"
              onClick={() => setExpanded(open ? null : d.name)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
            >
              <span className="min-w-0 flex-1 truncate text-[12.5px] font-[550]">{d.name}</span>
              <TonePill tone={d.status === 'done' ? 'green' : d.status === 'drafting' ? 'yellow' : 'neutral'}>
                {d.status === 'done' ? '已定稿' : d.status === 'drafting' ? '撰写中' : '待开始'}
              </TonePill>
              <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{d.pages} 页</span>
            </button>
            {open ? (
              <div className="border-t border-border-light px-3 py-2">
                <div className="grid grid-cols-3 gap-2">
                  <Field k="页数" v={`${d.pages} 页`} />
                  <Field k="上传时间" v={d.updatedAt} />
                  <Field k="上传人" v={d.owner} />
                </div>
                <div className="mt-2 mb-1 text-[10.5px] font-medium text-muted-foreground">
                  版本历史（{versions.length} 版）
                </div>
                {versions.length === 0 ? (
                  <div className="text-[10.5px] text-muted-foreground">还没上传过文件，无版本记录</div>
                ) : (
                  <table className="w-full table-fixed border-collapse">
                    <colgroup>
                      <col className="w-[44px]" />
                      <col className="w-[110px]" />
                      <col className="w-[56px]" />
                      <col />
                    </colgroup>
                    <tbody>
                      {versions.map((v) => (
                        <tr key={v.version} className="border-t border-border-light first:border-t-0">
                          <td className="py-1 align-top text-[11px] font-[550] tabular-nums">
                            {v.version}
                            {v.current ? <span className="ml-1 text-status-green">·</span> : null}
                          </td>
                          <td className="py-1 align-top text-[10.5px] tabular-nums text-muted-foreground">{v.at}</td>
                          <td className="py-1 align-top text-[10.5px] tabular-nums text-muted-foreground">{v.pages} 页</td>
                          <td className="py-1 align-top text-[10.5px] leading-[1.55] text-secondary-foreground">
                            {v.note}
                            <span className="ml-1 text-muted-foreground">— {v.who}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
