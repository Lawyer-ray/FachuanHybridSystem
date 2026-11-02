/**
 * 关厂清盘 · 阶段清单（可点开抽屉）+ 交付物清单（可点开抽屉）+ 推进到下一阶段
 *
 * 这三块原来都只是文字：阶段行没有入口、交付物没有入口、「推进」根本不存在。
 * 现在：
 *   · 每个阶段行点开 → 阶段抽屉（详情 / 验收标准 / 交付物 / 变更记录 + 三个动作）
 *   · 每个交付物行点开 → 交付物抽屉（页数 / 上传时间 / 上传人 / 预览占位 / 版本 + 四个动作）
 *   · 「推进到下一阶段」是主交互：先跑三项前置校验，校验不过就停在确认上等人
 *
 * 三个动作直接改本页状态（标记完成 / 重新打开 / 调整计划日期），演示环境不回写
 * 后端——关厂清盘的阶段契约还没有。页面底部一行小字把这条口径写清楚。
 */

import { useMemo, useState } from 'react'
import { ChevronRight, FileText, ListChecks, ShieldQuestion, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'

import {
  DEMO_NL1_CHANGE_LOGS,
  DEMO_NL1_CLIENT_CONFIRMS,
  DEMO_NL1_GATE_RULES,
  DEMO_NL1_GANTT,
  DEMO_NONLIT_PHASES,
} from '../../demo-nonlit'
import { NonLitActionCard } from '../../nonlit-action-card'
import { useNonLitAction } from '../../use-nonlit-action'
import { Card } from '../../ui'
import { BlockHead, Inset, TonePill, type Tone } from './special-bits'
import { SpecialDocDrawer, type DrawerDoc } from './special-doc-drawer'
import { SpecialPhaseDrawer, type DrawerPhase } from './special-phase-drawer'
import { addDays, evaluateGate } from './special-liquidation-model'

const STATUS_TEXT: Record<DrawerPhase['status'], string> = { done: '已完成', doing: '进行中', todo: '未开始' }
const STATUS_TONE: Record<DrawerPhase['status'], Tone> = { done: 'green', doing: 'blue', todo: 'neutral' }

/** 演示数据 → 抽屉用的阶段（负责人取自甘特图的同一份分配） */
function toDrawerPhases(rows: typeof DEMO_NONLIT_PHASES): DrawerPhase[] {
  const ownerOf = new Map(DEMO_NL1_GANTT.map((g) => [g.phaseId, g.owner]))
  return rows.map((p) => ({ ...p, owner: ownerOf.get(p.id) ?? '—' }))
}

/**
 * @param initialPhaseId 外部（甘特图）指定要直接打开的阶段抽屉；
 *   `phaseFocus` 递增一次就重新打开一次，避免「点同一条两次没反应」。
 */
export function SpecialPhaseBoard({ initialPhaseId, phaseFocus = 0 }: { initialPhaseId?: string; phaseFocus?: number }) {
  const [phases, setPhases] = useState<DrawerPhase[]>(() => toDrawerPhases(DEMO_NONLIT_PHASES))
  /** 被删 / 改名过的交付物：key = `${phaseId}:${原交付物名}` */
  const [docPatches, setDocPatches] = useState<Record<string, string>>({})
  const [removedDocs, setRemovedDocs] = useState<string[]>([])
  const [openPhaseId, setOpenPhaseId] = useState<string | null>(initialPhaseId ?? null)
  /** 上一次响应过的 focus 计数（脏检查放在渲染里，不额外开 effect） */
  const [seenFocus, setSeenFocus] = useState(phaseFocus)
  if (phaseFocus !== seenFocus) {
    setSeenFocus(phaseFocus)
    if (initialPhaseId) setOpenPhaseId(initialPhaseId)
  }
  const [openDoc, setOpenDoc] = useState<DrawerDoc | null>(null)

  const gate = evaluateGate(DEMO_NL1_GATE_RULES)
  /** 当前阶段 = 第一个未完成的阶段（推进的对象） */
  const current = phases.find((p) => p.status === 'doing') ?? phases.find((p) => p.status === 'todo') ?? null
  const nextPhase = current ? (phases[phases.findIndex((p) => p.id === current.id) + 1] ?? null) : null

  const docs = useMemo(
    () =>
      phases.flatMap((p) =>
        p.deliverables.map((d) => ({
          ...d,
          name: docPatches[`${p.id}:${d.name}`] ?? d.name,
          phaseId: p.id,
          phaseName: p.name,
          phaseSeq: p.seq,
        })),
      ),
    [phases, docPatches],
  )

  /* ---------------- 阶段动作 ---------------- */

  const markDone = (id: string) => {
    setPhases((v) => v.map((p) => (p.id === id ? { ...p, status: 'done' } : p)))
    const p = phases.find((x) => x.id === id)
    toast.success(`「${p?.name ?? ''}」已标记完成`, { description: '验收结论写入变更记录，交付物与客户确认保持原样' })
  }

  const reopen = (id: string) => {
    setPhases((v) => v.map((p) => (p.id === id ? { ...p, status: 'doing' } : p)))
    const p = phases.find((x) => x.id === id)
    toast.info(`「${p?.name ?? ''}」已重新打开`, { description: '已归档的交付物不会被删除，可直接补新版' })
  }

  const shiftPlan = (id: string, days: number) => {
    setPhases((v) =>
      v.map((p) =>
        p.id === id ? { ...p, planStart: addDays(p.planStart, days), planEnd: addDays(p.planEnd, days) } : p,
      ),
    )
    toast.success(`「${phases.find((x) => x.id === id)?.name ?? ''}」计划${days > 0 ? '后移' : '提前'} ${Math.abs(days)} 天`)
  }

  /* ---------------- 交付物动作 ---------------- */

  const patchDoc = (doc: DrawerDoc, next: string) => setDocPatches((v) => ({ ...v, [`${doc.phaseId}:${doc.name}`]: next }))

  const renameDoc = (doc: DrawerDoc, next: string) => {
    patchDoc(doc, next)
    setOpenDoc({ ...doc, name: next })
    toast.success(`已重命名为《${next}》`)
  }

  const deleteDoc = (doc: DrawerDoc) => {
    setRemovedDocs((v) => [...v, `${doc.phaseId}:${doc.name}`])
    setPhases((v) => v.map((p) => (p.id === doc.phaseId ? { ...p, deliverables: p.deliverables.filter((d) => d.name !== doc.name) } : p)))
    setOpenDoc(null)
    toast.success(`《${doc.name}》已移入回收站`, { description: '版本历史一并归档，30 天内可恢复' })
  }

  const redraftDoc = (doc: DrawerDoc) => {
    setPhases((v) =>
      v.map((p) =>
        p.id === doc.phaseId
          ? { ...p, deliverables: p.deliverables.map((d) => (d.name === doc.name ? { ...d, status: 'drafting' } : d)) }
          : p,
      ),
    )
    toast.success(`已按 ${doc.name} 当前版重新起草`, { description: `落到「${doc.phaseName}」，保存前不影响已定稿版本` })
  }

  /* ---------------- 主交互：推进到下一阶段 ---------------- */

  const advance = useNonLitAction(
    [
      { text: '读取当前阶段（文件起草）的验收口径', ms: 500 },
      { text: '校验前置条件', ms: 900, parallel: ['交付物齐全', '验收标准满足', '客户书面确认'] },
      { text: `交付物检查：${docs.length} 份均可打开，无缺件`, ms: 700 },
      {
        text: '验收标准检查：187 人中已签 146 人（78%），未达 100%',
        ms: 800,
        retry: { times: 1, delay: 900, reason: '签署率统计接口超时，按最近一次台账重算' },
      },
      {
        text: '客户确认检查：职工安置方案 v1.3 签字页缺失',
        ms: 700,
        confirm:
          '3 项前置检查过了 1 项：交付物齐全，「验收标准满足」与「客户书面确认」均未通过。' +
          '按推进纪律，未签署的交付物不能作为阶段完成依据。是否仍然强行推进到「登记与注销」？',
      },
      { text: '写入推进记录（带未通过项说明）', ms: 600 },
    ],
    `已推进到「${nextPhase?.name ?? '下一阶段'}」，2 项未通过已写入推进记录并挂到风险登记表`,
  )

  return (
    <>
      <NonLitActionCard
        title="推进到下一阶段"
        desc="推进前先跑三项前置校验：交付物是否齐全、验收标准是否满足、客户是否书面确认。有一项不过就停下问人，不静默推进。"
        actionLabel="推进到下一阶段"
        hint={current ? `${current.seq} ${current.name} → ${nextPhase?.seq ?? '—'} ${nextPhase?.name ?? '（末阶段）'}` : '已无待推进阶段'}
        state={advance}
      />

      {/* 前置校验结果 */}
      <Card className="px-[18px] py-[15px]">
        <div className="flex items-baseline gap-2">
          <h3 className="flex items-center gap-1.5 text-[13px] font-[620]">
            <ListChecks className="size-3.5 text-muted-foreground" />
            推进前置校验
          </h3>
          <span className="text-[11px] text-muted-foreground">
            通过 {gate.passed} / {gate.total}
          </span>
          <div className="ml-auto">
            <TonePill tone={gate.canAdvance ? 'green' : 'yellow'}>
              {gate.canAdvance ? '可以推进' : `阻断 ${gate.blocked} 项`}
            </TonePill>
          </div>
        </div>
        <div className="mt-2.5 flex flex-col gap-1.5">
          {DEMO_NL1_GATE_RULES.map((r) => (
            <Inset key={r.id} className={cn(r.ok ? 'border-status-green/35' : 'border-status-yellow/50 bg-status-yellow-bg/25')}>
              <div className="flex items-center gap-2">
                <TonePill tone={r.ok ? 'green' : 'yellow'}>{r.ok ? '通过' : '未通过'}</TonePill>
                <span className="text-[12px] font-[550]">{r.label}</span>
                <span className="ml-auto truncate text-[10.5px] text-muted-foreground">{r.detail}</span>
              </div>
              {!r.ok && r.fix ? (
                <div className="mt-1 text-[10.5px] leading-[1.6] text-status-yellow">怎么办：{r.fix}</div>
              ) : null}
            </Inset>
          ))}
        </div>
      </Card>

      {/* 阶段清单 */}
      <Card className="px-[18px] py-[15px]">
        <div className="flex items-baseline gap-2">
          <h3 className="flex items-center gap-1.5 text-[13px] font-[620]">
            <Sparkles className="size-3.5 text-muted-foreground" />
            阶段清单
          </h3>
          <span className="text-[11px] text-muted-foreground">点任意一行打开阶段抽屉</span>
          <button
            type="button"
            onClick={() => setOpenPhaseId(current?.id ?? phases[0]?.id ?? null)}
            className="ml-auto text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            打开当前阶段
          </button>
        </div>
        <div className="mt-2 flex flex-col divide-y divide-border-light rounded-[9px] border border-border-light bg-background">
          {phases.map((p) => {
            const changed = DEMO_NL1_CHANGE_LOGS.filter((c) => c.phase === p.name).length
            const confirmed = DEMO_NL1_CLIENT_CONFIRMS.filter((c) => c.phase === p.name).length
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setOpenPhaseId(p.id)}
                className="flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
              >
                <span className="w-[26px] flex-none text-[11px] tabular-nums text-muted-foreground">{p.seq}</span>
                <span className={cn('min-w-0 flex-1 truncate text-[12.5px]', p.status === 'doing' ? 'font-[650]' : 'font-[550]')}>
                  {p.name}
                </span>
                <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
                  {p.planStart.slice(5)} → {p.planEnd.slice(5)}
                </span>
                <span className="w-[62px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  {p.deliverables.length} 份 · 改 {changed}
                </span>
                <span className="w-[52px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  确认 {confirmed}
                </span>
                <TonePill tone={STATUS_TONE[p.status]}>{STATUS_TEXT[p.status]}</TonePill>
                <ChevronRight className="size-3 flex-none text-muted-foreground/60" />
              </button>
            )
          })}
        </div>
      </Card>

      {/* 交付物清单 */}
      <Card className="px-[18px] py-[15px]">
        <BlockHead title="交付物清单" hint={`${docs.length} 份 · 点任意一行看版本与预览`} />
        <div className="flex flex-col divide-y divide-border-light rounded-[9px] border border-border-light bg-background">
          {docs.map((d) => (
            <button
              key={`${d.phaseId}:${d.name}`}
              type="button"
              onClick={() => setOpenDoc(d)}
              className="flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
            >
              <FileText className="size-3.5 flex-none text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-[12.5px] font-[550]" title={d.name}>
                {d.name}
              </span>
              <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{d.pages} 页</span>
              <span className="w-[86px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{d.updatedAt}</span>
              <span className="w-[42px] flex-none text-right text-[10.5px] text-muted-foreground">{d.owner}</span>
              <TonePill tone={d.status === 'done' ? 'green' : d.status === 'drafting' ? 'yellow' : 'neutral'}>
                {d.status === 'done' ? '已定稿' : d.status === 'drafting' ? '撰写中' : '待开始'}
              </TonePill>
              <ChevronRight className="size-3 flex-none text-muted-foreground/60" />
            </button>
          ))}
          {docs.length === 0 ? (
            <div className="px-3 py-3 text-[12px] text-muted-foreground">全部交付物已删除，可从阶段抽屉重新起草</div>
          ) : null}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
          <ShieldQuestion className="size-3" />
          推进动作会把未通过项写进推进记录；删除与改名只在本页生效（演示数据）
          <span className="ml-auto">已删除 {removedDocs.length} 份</span>
        </div>
      </Card>

      {/* 抽屉 */}
      <SpecialPhaseDrawer
        open={openPhaseId !== null}
        phase={phases.find((p) => p.id === openPhaseId) ?? null}
        onClose={() => setOpenPhaseId(null)}
        onComplete={markDone}
        onReopen={reopen}
        onShiftPlan={shiftPlan}
      />
      <SpecialDocDrawer
        open={openDoc !== null}
        doc={openDoc}
        onClose={() => setOpenDoc(null)}
        onDownload={(name) => toast.success(`开始下载《${name}》`)}
        onRename={(name, next) => {
          const target = docs.find((d) => d.name === name)
          if (target) renameDoc(target, next)
        }}
        onDelete={(name) => {
          const target = docs.find((d) => d.name === name)
          if (target) deleteDoc(target)
        }}
        onRedraft={(name) => {
          const target = docs.find((d) => d.name === name)
          if (target) redraftDoc(target)
        }}
      />
    </>
  )
}
