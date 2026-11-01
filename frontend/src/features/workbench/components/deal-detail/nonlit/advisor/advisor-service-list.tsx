/**
 * 常年顾问 · 服务事项清单（按类型分组 + 每条可展开）
 *
 * 常法页原来的事项表只能看：一行一条，交付物是本地的字符串，点不开也改不了。
 * 律师复盘时真正要问的是「这条具体做了什么、花了多久、交付物交了没有」，
 * 以及「能不能把它转成正式意见书」——所以每条都做成可展开的行。
 *
 * 分组用 tabs 而不是折叠面板：类型只有 5 种，tabs 能顺带显示**每类的条数与
 * 工时小计**，正好回答「上个月同事都在审合同还是在开会」。
 */

import { useState } from 'react'
import { CheckCircle2, ChevronRight, FileUp, ScrollText, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { DemoNl3ServiceItem } from '../../demo-nonlit'
import { ActionButton, Card } from '../../ui'
import { effortRows, filterItems, groupByMonth, kindTabs, type KindTab } from './advisor-domain'

const KIND_TONE: Record<string, string> = {
  合同审查: 'border-border bg-secondary text-secondary-foreground',
  咨询: 'border-border bg-secondary text-secondary-foreground',
  出具意见: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  会议出席: 'border-status-purple/40 bg-status-purple-bg text-status-purple',
  培训: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
}

function KindPill({ kind }: { kind: string }) {
  return (
    <span
      className={cn(
        'flex-none rounded-[6px] border px-1.5 text-[10.5px] leading-[1.6] font-semibold whitespace-nowrap',
        KIND_TONE[kind] ?? KIND_TONE['咨询'],
      )}
    >
      {kind}
    </span>
  )
}

export function AdvisorServiceList({
  items,
  onDeliver,
  onOpinion,
}: {
  items: DemoNl3ServiceItem[]
  /** 补传交付物（命中的那条事项提示后置为已交付） */
  onDeliver: (item: DemoNl3ServiceItem) => void
  /** 转成正式意见书 */
  onOpinion: (item: DemoNl3ServiceItem) => void
}) {
  const [tab, setTab] = useState<KindTab['key']>('all')
  const [open, setOpen] = useState<string | null>(null)
  /** 本地已标记完成 / 已转意见书的事项（演示态：不改数据源，只影响这一页） */
  const [doneIds, setDoneIds] = useState<string[]>([])
  const [opinionIds, setOpinionIds] = useState<string[]>([])
  const [deliveredIds, setDeliveredIds] = useState<string[]>([])

  const tabs = kindTabs(items)
  const shown = filterItems(items, tab)
  const groups = groupByMonth(shown)
  const current = tabs.find((t) => t.key === tab) ?? tabs[0]!

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">服务事项</h3>
        <span className="text-[11px] text-muted-foreground">
          {current.count} 项 · 小计 {current.hours}h · 跨 {groups.length} 个月
        </span>
        <span className="ml-auto text-[10.5px] text-muted-foreground">点开一条看做了什么、交付了什么</span>
      </div>

      {/* 类型 tabs：全部 16 / 合同审查 5 / 咨询 4 / 出具意见 4 / 会议出席 2 / 培训 2 */}
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {tabs.map((t) => {
          const on = t.key === tab
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'inline-flex h-[26px] items-center gap-1.5 rounded-[7px] border px-2.5 text-[11.5px] font-[550] transition-colors',
                on
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
              )}
            >
              <span>
                {t.label} {t.count}
              </span>
              <span className={cn('tabular-nums', on ? 'text-background/70' : 'text-muted-foreground')}>
                {t.hours}h
              </span>
            </button>
          )
        })}
      </div>

      <div className="mt-2.5 flex flex-col gap-2">
        {groups.map((g) => (
          <div key={g.month}>
            <div className="mb-1 flex items-baseline gap-2 text-[10.5px] text-muted-foreground">
              <span className="font-[620] text-secondary-foreground">{g.month}</span>
              <span>
                {g.items.length} 项 · 小计{' '}
                {Math.round(g.items.reduce((s, i) => s + i.hours, 0) * 10) / 10}h
              </span>
            </div>
            <div className="flex flex-col divide-y divide-border-light overflow-hidden rounded-[9px] border border-border-light bg-background">
              {g.items.map((it) => (
                <ItemRow
                  key={it.id}
                  item={it}
                  open={open === it.id}
                  done={doneIds.includes(it.id) || it.status === 'done'}
                  delivered={deliveredIds.includes(it.id) || it.delivered}
                  opinion={opinionIds.includes(it.id) || it.opinionIssued}
                  onToggle={() => setOpen(open === it.id ? null : it.id)}
                  onDone={() => setDoneIds((v) => [...v, it.id])}
                  onDeliver={() => {
                    setDeliveredIds((v) => [...v, it.id])
                    onDeliver(it)
                  }}
                  onOpinion={() => {
                    setOpinionIds((v) => [...v, it.id])
                    onOpinion(it)
                  }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function ItemRow({
  item,
  open,
  done,
  delivered,
  opinion,
  onToggle,
  onDone,
  onDeliver,
  onOpinion,
}: {
  item: DemoNl3ServiceItem
  open: boolean
  done: boolean
  delivered: boolean
  opinion: boolean
  onToggle: () => void
  onDone: () => void
  onDeliver: () => void
  onOpinion: () => void
}) {
  const rows = effortRows(item)
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
      >
        <ChevronRight
          className={cn('size-3 flex-none text-muted-foreground transition-transform', open && 'rotate-90')}
        />
        <span className="w-[38px] flex-none text-[10.5px] tabular-nums text-muted-foreground">
          {item.date.slice(5)}
        </span>
        <KindPill kind={item.kind} />
        <span className="min-w-0 flex-1 truncate text-[12px]" title={item.title}>
          {item.title}
        </span>
        {opinion ? (
          <span className="flex-none rounded-[5px] border border-status-blue/40 bg-status-blue-bg px-1.5 text-[10px] font-semibold text-status-blue">
            已出意见书
          </span>
        ) : null}
        <span
          className={cn(
            'flex-none rounded-[5px] border px-1.5 text-[10px] font-semibold',
            delivered
              ? 'border-status-green/40 bg-status-green-bg text-status-green'
              : 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
          )}
        >
          {delivered ? '已交付' : '待补交付物'}
        </span>
        <span className="w-[42px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
          {item.hours}h
        </span>
        {done ? (
          <CheckCircle2 className="size-3 flex-none text-status-green" />
        ) : (
          <XCircle className="size-3 flex-none text-status-yellow" />
        )}
      </button>

      {open ? (
        <div className="flex flex-col gap-2 border-t border-border-light bg-secondary/20 px-3 pt-2 pb-2.5">
          <div>
            <div className="text-[10px] font-medium text-muted-foreground">具体做了什么</div>
            <p className="mt-0.5 text-[11.5px] leading-[1.65]">{item.detail}</p>
          </div>

          <div className="grid grid-cols-2 gap-2 max-[820px]:grid-cols-1">
            <div className="rounded-[7px] border border-border-light bg-background px-2.5 py-1.5">
              <div className="text-[10px] font-medium text-muted-foreground">交付物</div>
              <div className="mt-0.5 flex items-start gap-1.5 text-[11.5px] leading-[1.5]">
                <ScrollText className="mt-[2px] size-3 flex-none text-muted-foreground" />
                <span className="min-w-0 break-all">{item.deliverable}</span>
              </div>
            </div>
            <div className="rounded-[7px] border border-border-light bg-background px-2.5 py-1.5">
              <div className="text-[10px] font-medium text-muted-foreground">耗时明细（合计 {item.hours}h）</div>
              <ul className="mt-1 flex flex-col gap-[3px]">
                {rows.map((r) => (
                  <li key={r.label} className="flex items-center gap-2 text-[10.5px]">
                    <span className="min-w-0 flex-1 truncate text-secondary-foreground">{r.label}</span>
                    <span className="h-[3px] w-[52px] flex-none overflow-hidden rounded-full bg-secondary">
                      <span
                        className="block h-full rounded-full bg-foreground/45"
                        style={{ width: `${Math.min(100, (r.hours / item.hours) * 100)}%` }}
                      />
                    </span>
                    <span className="w-[30px] flex-none text-right tabular-nums text-muted-foreground">{r.hours}h</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <ActionButton sm onClick={onDone}>
              <CheckCircle2 className="size-3" /> 标记完成
            </ActionButton>
            <ActionButton sm onClick={onDeliver}>
              <FileUp className="size-3" /> 补传交付物
            </ActionButton>
            <ActionButton sm onClick={onOpinion}>
              <ScrollText className="size-3" /> 转成正式意见书
            </ActionButton>
            <span className="ml-auto text-[10px] text-muted-foreground">
              {item.status === 'done' ? '台账状态：已办结' : '台账状态：进行中'}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
