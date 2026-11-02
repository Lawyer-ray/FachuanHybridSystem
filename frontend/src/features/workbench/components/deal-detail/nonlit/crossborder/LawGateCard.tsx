/**
 * 外国法核验：四道闸 + 核验依据
 *
 * 上面的动作卡只把「机器跑了」演出来；这张卡回答律师真正会追问的两件事：
 *   1. 这道闸到底查了什么、拿回来什么？（点开某道闸）
 *   2. 你凭哪一条法条说要这么改？法条原文在哪？（每条修订 → 英文原文 + 出处）
 *
 * 编造的法条在三道规则闸上就死（法是否存在 / 有没有正文 / 条款号在不在范围），
 * 只有过了这三道才交给判断层比对语义——这一点必须让律师看见，否则「AI 查了法条」
 * 和「AI 编了法条」在界面上长得一样。
 */

import { useState } from 'react'
import { BookOpen, ChevronDown, ExternalLink, Gavel, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  DEMO_LAW_GATES,
  DEMO_NL2_LAW_EXCERPTS,
  DEMO_REVISION_BY_ID,
  type DemoLawGate,
  type DemoNl2LawExcerpt,
} from '../../demo-nonlit'
import { Card } from '../../ui'
import { TonePill as Pill } from './crossborder-ui'

/** 每道闸的「查了什么 / 拿回来什么」——录屏时点开就能念的问答 */
const GATE_TRACE: Record<string, { query: string; got: string; sample: string }> = {
  '01': {
    query: 'Q: 是否存在名为「泰国民商法典」的法律？检索 BARLC 法律库 + 泰国皇家公报标题索引。',
    got: 'A: 命中 1 部。《Civil and Commercial Code of Thailand》，现行版本含 1,752 条。',
    sample: 'registry: TH-CCC-1952 (amended B.E. 2563) · match=exact',
  },
  '02': {
    query: 'Q: 该法能否取到逐条正文（而非只有目录/标题）？拉取全文并校验条目完整性。',
    got: 'A: 1,752 条正文全部可读，缺 0 条；单条平均 41 词，无空条文。',
    sample: 'fetched=1752 / gaps=0 / encoding=utf-8 / sha256=d41f…8c2a',
  },
  '03': {
    query: 'Q: 合同审查里引用的条款号是否落在该法的条目区间内？逐条比对。',
    got: 'A: 第 538 / 546 / 549 条均在 1–1752 内；未出现「第 1899 条」这类越界引用。',
    sample: 'refs=[538,546,549] · min=1 · max=1752 · out_of_range=0',
  },
  '04': {
    query: 'Q: 条文是否真的支持律所提出的修改主张？（判断层，不是规则）语义比对条文与改写方案。',
    got: 'A: 3 条支持、1 条部分支持（第 549 条「违约金与实际损失相当」需再解释），置信度 0.89–0.96。',
    sample: 'verdict=support×3 / partial×1 · confidence=0.89~0.96',
  },
}

function GateRow({ gate, open, onToggle }: { gate: DemoLawGate; open: boolean; onToggle: () => void }) {
  const t = GATE_TRACE[gate.n]
  return (
    <div
      className={cn(
        'rounded-[9px] border',
        gate.kind === 'rule' ? 'border-border-light bg-background' : 'border-status-blue/40 bg-status-blue-bg/40',
      )}
    >
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-2.5 px-3 py-2 text-left">
        <span className="w-6 flex-none font-mono text-[11px] text-muted-foreground">{gate.n}</span>
        <span className="text-[12px] font-medium">{gate.name}</span>
        <Pill tone={gate.kind === 'rule' ? 'neutral' : 'blue'}>{gate.kind === 'rule' ? '规则闸' : '判断层'}</Pill>
        <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground">{gate.detail}</span>
        <span className="flex-none text-[10px] tabular-nums text-muted-foreground">{gate.ms} ms</span>
        <ShieldCheck className="size-3.5 flex-none text-status-green" />
        <ChevronDown className={cn('size-3 flex-none text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && t ? (
        <div className="border-t border-border-light/70 px-3 py-2">
          <div className="text-[10.5px] leading-[1.7]">{t.query}</div>
          <div className="mt-1 text-[10.5px] leading-[1.7] text-status-green">{t.got}</div>
          <div className="mt-1.5 rounded-[6px] bg-secondary/40 px-2 py-1 font-mono text-[10px] break-all text-muted-foreground">
            {t.sample}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function Excerpt({ row, onPickRev }: { row: DemoNl2LawExcerpt; onPickRev: (rev: string) => void }) {
  const rev = DEMO_REVISION_BY_ID[row.rev]
  return (
    <div className="rounded-[9px] border border-border-light bg-background px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Gavel className="size-3.5 flex-none text-status-blue" />
        <span className="text-[12px] font-medium">
          {row.law} {row.article}
        </span>
        <Pill tone="green">已核验</Pill>
        <span className="text-[10px] tabular-nums text-muted-foreground">置信度 {row.confidence}</span>
        <button
          type="button"
          onClick={() => onPickRev(row.rev)}
          className="ml-auto text-[10.5px] text-muted-foreground underline underline-offset-2 transition-colors hover:text-foreground"
        >
          看对应修订：{rev?.title ?? row.rev}
        </button>
      </div>
      <blockquote className="mt-1.5 border-l-2 border-status-blue/40 pl-2.5 text-[11px] leading-[1.75] text-secondary-foreground italic">
        “{row.textEn}”
      </blockquote>
      <div className="mt-1 text-[10px] break-all text-muted-foreground">
        出处：{row.source} · {row.retrievedAt}
      </div>
      <div className="mt-1 text-[10.5px] leading-[1.6] text-status-green">判断层：{row.supports}</div>
    </div>
  )
}

export function LawGateCard({
  active,
  onPickRev,
}: {
  /** 核验动作是否已启动（未启动时闸不展示结论，避免「没跑就出结果」） */
  active: boolean
  onPickRev: (rev: string) => void
}) {
  const [openGate, setOpenGate] = useState<string | null>(null)
  const [tab, setTab] = useState<'gates' | 'basis'>('gates')

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[13px] font-[620]">外国法核验依据</h3>
        <span className="text-[11px] text-muted-foreground">点开某道闸看它查了什么 · 每条修订可回查法条原文</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setTab('gates')}
            className={cn(
              'inline-flex h-[27px] items-center rounded-[7px] border px-2.5 text-[11.5px] transition-colors',
              tab === 'gates'
                ? 'border-foreground bg-foreground font-semibold text-background'
                : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
            )}
          >
            四道闸 {DEMO_LAW_GATES.length}
          </button>
          <button
            type="button"
            onClick={() => setTab('basis')}
            className={cn(
              'inline-flex h-[27px] items-center rounded-[7px] border px-2.5 text-[11.5px] transition-colors',
              tab === 'basis'
                ? 'border-foreground bg-foreground font-semibold text-background'
                : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
            )}
          >
            <BookOpen className="size-3" /> 法条原文 {DEMO_NL2_LAW_EXCERPTS.length}
          </button>
        </div>
      </div>

      {tab === 'gates' ? (
        <div className="mt-3 flex flex-col gap-1.5">
          {!active ? (
            <div className="rounded-[9px] border border-dashed border-border px-3 py-2 text-[10.5px] text-muted-foreground">
              还没跑核验。点上面的「核验法条」后，四道闸会逐道落结论；任何一道不过，后面的判断层就不再执行。
            </div>
          ) : null}
          {DEMO_LAW_GATES.map((g) => (
            <GateRow
              key={g.n}
              gate={g}
              open={openGate === g.n}
              onToggle={() => setOpenGate(openGate === g.n ? null : g.n)}
            />
          ))}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-1.5">
          {DEMO_NL2_LAW_EXCERPTS.map((row) => (
            <Excerpt key={row.rev} row={row} onPickRev={onPickRev} />
          ))}
          <div className="rounded-[9px] border border-status-yellow/40 bg-status-yellow-bg/40 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-status-yellow">
              <ExternalLink className="size-3" /> 第 5 处无外国法依据
            </div>
            <div className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
              「语言版本以泰文为准」不违反任何泰国强制性规定，三道规则闸无条可核，判断层标为需律师判断——不硬编法条。
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
