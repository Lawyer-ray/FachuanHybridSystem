/**
 * ⑥ 校验 —— 三处金额对比
 *
 * 同一笔钱在三个地方各有一份数字：起诉状（律师定稿）、一张网立案表单（回读）、
 * 要素式起诉状（自动转换）。三处对不上，法院当场退回。
 *
 * 表格只给「差多少」，点开才给「为什么差」—— 差异来自计算口径
 * （360 天 vs 365 天），不是谁抄错了一个数。
 */

import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { DEMO_X3_AMOUNTS } from '../demo-data'
import { ActionButton, InsetBlock, Pill, SectionTitle, WorkCard } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'

export function FilingAmountCard() {
  const [open, setOpen] = useState<string | null>(null)
  const diffs = DEMO_X3_AMOUNTS.filter((a) => !a.consistent)

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="三处金额对比"
          hint="起诉状 / 立案表单 / 要素式"
          className="w-full"
          action={diffs.length ? <Pill tone="red">{diffs.length} 处不一致</Pill> : <Pill tone="green">三处一致</Pill>}
        />
      </div>

      <div className="grid grid-cols-[92px_repeat(3,minmax(0,1fr))_84px] items-center gap-x-2 border-b border-border-light bg-secondary/25 px-5 py-1.5 text-[10px] text-muted-foreground">
        <span>项目</span>
        <span className="text-right">起诉状</span>
        <span className="text-right">立案表单</span>
        <span className="text-right">要素式</span>
        <span className="text-right">差异</span>
      </div>

      <ul className="divide-y divide-border-light">
        {DEMO_X3_AMOUNTS.map((a) => (
          <li
            key={a.item}
            onClick={() => setOpen(a.item)}
            className={cn(
              'grid cursor-pointer grid-cols-[92px_repeat(3,minmax(0,1fr))_84px] items-center gap-x-2 px-5 py-2 transition-colors hover:bg-secondary/40',
              !a.consistent && 'bg-status-red-bg/40',
            )}
          >
            <span className="flex min-w-0 items-center gap-1 text-[11.5px]">
              {!a.consistent ? <AlertTriangle className="size-3 flex-none text-status-red" /> : null}
              <span className={cn('truncate', !a.consistent && 'font-medium text-status-red')}>{a.item}</span>
            </span>
            <span className="text-right text-[11.5px] tabular-nums">{a.complaint}</span>
            <span
              className={cn(
                'text-right text-[11.5px] tabular-nums',
                !a.consistent && 'font-semibold text-status-red',
              )}
            >
              {a.filingForm}
            </span>
            <span className="text-right text-[11.5px] tabular-nums">{a.elements}</span>
            <span
              className={cn(
                'text-right text-[11px] tabular-nums',
                a.consistent ? 'text-muted-foreground' : 'font-semibold text-status-red',
              )}
            >
              {a.consistent ? '—' : `+${a.delta}`}
            </span>
          </li>
        ))}
      </ul>

      <div className="border-t border-border-light px-5 py-2 text-[10px] text-muted-foreground">
        点任意一行看计算口径；差异行标红，修法见下方「不通过项怎么修」。
      </div>

      <AmountBasisDrawer item={open} onClose={() => setOpen(null)} />
    </WorkCard>
  )
}

/** 单笔的计算口径：三处分别怎么算出来的 */
function AmountBasisDrawer({ item, onClose }: { item: string | null; onClose: () => void }) {
  const a = item ? DEMO_X3_AMOUNTS.find((x) => x.item === item) : undefined

  return (
    <DetailDrawer
      open={a != null}
      onClose={onClose}
      width={520}
      title={a ? `${a.item} · 计算口径` : ''}
      subtitle={a ? (a.consistent ? '三处一致' : `立案表单与定稿差 ¥${a.delta}`) : undefined}
      badge={a ? <Pill tone={a.consistent ? 'green' : 'red'}>{a.consistent ? '一致' : '不一致'}</Pill> : null}
      footer={
        a ? (
          <ActionButton dark onClick={onClose}>
            以起诉状为准
          </ActionButton>
        ) : null
      }
    >
      {a ? (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: '起诉状', value: a.complaint, mark: false },
              { label: '立案表单', value: a.filingForm, mark: !a.consistent },
              { label: '要素式', value: a.elements, mark: false },
            ].map((c) => (
              <InsetBlock
                key={c.label}
                className={c.mark ? 'border-status-red/40 bg-status-red-bg/50' : undefined}
              >
                <div className="text-[10px] text-muted-foreground">{c.label}</div>
                <div
                  className={cn(
                    'mt-0.5 text-[12.5px] font-[620] tabular-nums',
                    c.mark && 'text-status-red',
                  )}
                >
                  {c.value}
                </div>
              </InsetBlock>
            ))}
          </div>

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">口径说明</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">{a.basis}</p>
          </InsetBlock>

          {!a.consistent ? (
            <InsetBlock className="border-status-red/40 bg-status-red-bg/40">
              <div className="text-[10.5px] font-medium text-status-red">差额来自口径不统一</div>
              <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
                立案表单由系统按 365 天重算，起诉状按 360 天。法院以起诉状为准，
                所以修的是立案表单那一侧 —— 见「一键修正可自动项」的 diff 预览。
              </p>
            </InsetBlock>
          ) : null}
        </div>
      ) : null}
    </DetailDrawer>
  )
}
