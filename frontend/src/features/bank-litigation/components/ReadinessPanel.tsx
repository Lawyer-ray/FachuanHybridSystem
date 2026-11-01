import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useMaterialStatus, useReadiness } from '../hooks/use-cases'
import type { SlotStatus } from '../types'
import { SectionTitle, StatTile, WorkCard } from './ui'

/**
 * 就绪度面板 —— 「这件能不能递」的唯一答案。
 *
 * ═══ 为什么材料齐备与起诉条件要并排 ═══
 * 它们回答的是同一件事的两半：
 *   · 起诉条件（主体/管辖/时效/金额）是**法律要件**，问「该不该立案」；
 *   · 材料齐备是**卷宗要件**，问「递得上去吗」。
 * 律师看完法律要件就该知道去哪补材料，所以两者必须同屏，
 * 分两个 tab 会让人来回切。
 *
 * ═══ 布局为什么这么排（2026-10-31 重做）═══
 * 旧版是「一个绿/红结论条 + 两列竖排文字」，在 1100px 内容区里只占左半边，
 * 右边大片空白；4 个法律要件用同样的小圆点，看不出哪个是硬阻塞。
 * 现在：
 *   ① 顶部 4 个数字块（通过项 / 缺件 / 标的 / 阶段）横向铺开，先用数字定调
 *   ② 法律要件用**卡片网格**，未通过的整卡染红（一屏只有一种告警色）
 *   ③ 材料槽位用**格子墙**，齐备=淡绿底、缺件=红底、不适用=灰底，
 *      6 个槽位一眼扫完，不用读字就知道缺几个
 */

/** 槽位状态 → 语气 + 文案 */
const SLOT_META: Record<SlotStatus, { tone: Tone; text: string }> = {
  ok: { tone: 'neutral', text: '齐备' },
  miss: { tone: 'red', text: '缺件' },
  stale: { tone: 'yellow', text: '待更新' },
  na: { tone: 'neutral', text: '不适用' },
}

/** 槽位状态的格子配色（比 StatusBadge 更重，用于格子墙铺底） */
const SLOT_CELL: Record<SlotStatus, string> = {
  ok: 'border-status-green/30 bg-status-green-bg/60',
  miss: 'border-status-red/40 bg-status-red-bg',
  stale: 'border-status-yellow/40 bg-status-yellow-bg',
  na: 'border-border bg-secondary/30',
}

export function ReadinessPanel({ caseId }: { caseId: number }) {
  const ready = useReadiness(caseId)
  const material = useMaterialStatus(caseId)

  if (ready.loading && material.loading) return <LoadingBlock text="正在校验起诉条件…" />
  if (ready.error) {
    return <ErrorBlock error={ready.error} fallback="起诉条件校验失败" onRetry={ready.reload} />
  }

  const r = ready.data
  const m = material.data
  const failed = (r?.total ?? 0) - (r?.passed ?? 0)
  const noRule = r?.mode === 'other'

  return (
    <div className="flex flex-col gap-3.5">
      {/* ══ ① 结论条：一句话 + 总数 ══ */}
      <div
        className={cn(
          'flex items-center gap-2.5 rounded-[10px] border px-4 py-3',
          r?.ready
            ? 'border-status-green/40 bg-status-green-bg'
            : 'border-status-red/40 bg-status-red-bg',
        )}
      >
        {r?.ready ? (
          <CheckCircle2 className="size-4 flex-none text-status-green" />
        ) : (
          <XCircle className="size-4 flex-none text-status-red" />
        )}
        <div className="min-w-0">
          <div
            className={cn(
              'text-[13.5px] font-semibold leading-tight',
              r?.ready ? 'text-status-green' : 'text-status-red',
            )}
          >
            {noRule
              ? '本阶段暂无专门校验'
              : r?.ready
                ? '起诉条件已满足，可以立案'
                : `还有 ${failed} 项没过，先补齐`}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            {noRule
              ? '执行、仲裁等阶段还没有对应的校验规则 —— 不是「已通过」，只是这里不判断。'
              : '法律要件与卷宗要件都过，才允许推进到一张网递交。'}
          </div>
        </div>
        {r ? (
          <div className="ml-auto flex items-baseline gap-0.5 tabular-nums">
            <span
              className={cn(
                'text-[22px] font-semibold leading-none',
                r.ready ? 'text-status-green' : 'text-status-red',
              )}
            >
              {r.passed}
            </span>
            <span className="text-[12px] text-muted-foreground">/{r.total}</span>
          </div>
        ) : null}
      </div>

      {/* ══ ② 四个数字块：先把事实摆出来 ══ */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile
          label="法律要件"
          value={`${r?.passed ?? 0}/${r?.total ?? 0}`}
          tone={r?.ready ? 'green' : 'red'}
        />
        <StatTile
          label="材料缺件"
          value={m ? m.missing_count : '—'}
          unit={m && m.missing_count > 0 ? '项' : undefined}
          tone={m && m.missing_count > 0 ? 'red' : 'green'}
        />
        <StatTile label="案件阶段" value={r?.stage === 'first_trial' ? '一审' : r?.stage || '—'} />
        <StatTile
          label="校验模式"
          value={noRule ? '不判断' : r?.mode === 'appeal' ? '答辩条件' : '起诉条件'}
          tone={noRule ? 'yellow' : 'neutral'}
        />
      </div>

      {/* ══ ③④ 双栏：左法律要件，右材料齐备。
          原来是上下两块单列，1080p 屏上只占上半屏；并排后填满宽度、信息密度翻倍，
          并且「法律要件 vs 卷宗要件」这个对比关系在版面上也就成立了。 ══ */}
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <WorkCard>
        <SectionTitle
          title={r?.mode === 'appeal' ? '答辩条件' : '起诉条件'}
          hint="逐项判定，未通过的一律染红"
          action={
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                ready.reload()
                material.reload()
              }}
            >
              重新校验
            </Button>
          }
        />
        {r?.checks?.length ? (
          <div className="mt-2.5 grid grid-cols-1 gap-2">
            {r.checks.map((c) => (
              <div
                key={c.key}
                className={cn(
                  'flex items-start gap-2.5 rounded-[8px] border px-3 py-2.5',
                  c.ok
                    ? 'border-border bg-secondary/20'
                    : 'border-status-red/40 bg-status-red-bg',
                )}
              >
                {c.ok ? (
                  <CheckCircle2 className="mt-[1px] size-3.5 flex-none text-status-green" />
                ) : (
                  <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-red" />
                )}
                <div className="min-w-0">
                  <div
                    className={cn(
                      'text-[12.5px] font-medium leading-tight',
                      c.ok ? 'text-foreground' : 'text-status-red',
                    )}
                  >
                    {c.label}
                  </div>
                  {/* detail 单独一行、允许换行：长句（如「未登记主管机关（管辖法院）」）
                      截断成省略号会让律师看不到真正缺什么，而那句话正是他要的 */}
                  <div
                    className={cn(
                      'mt-1 text-[11px] leading-[1.55] break-words',
                      c.ok ? 'text-muted-foreground' : 'text-status-red/90',
                    )}
                  >
                    {c.detail || '—'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2.5 text-[11.5px] text-muted-foreground">
            {noRule
              ? '执行、仲裁等阶段还没有对应的校验规则 —— 不是「已通过」，只是这里不判断。'
              : '暂无校验项。'}
          </p>
        )}
      </WorkCard>

      <WorkCard>
        <SectionTitle
          title="材料齐备"
          hint={
            m ? `${m.ok_count}/${m.need_count} 齐备${m.missing_count > 0 ? ` · 缺 ${m.missing_count}` : ''}` : undefined
          }
          action={material.loading ? <Loader2 className="size-3.5 animate-spin text-muted-foreground" /> : null}
        />
        {material.error ? (
          <p className="mt-2.5 text-[11.5px] text-status-red">{material.error}</p>
        ) : m?.slots?.length ? (
          <>
            <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {m.slots.map((s) => {
                const meta = SLOT_META[s.status ?? 'miss'] ?? SLOT_META.miss
                const status = s.status ?? 'miss'
                return (
                  <div
                    key={s.key}
                    className={cn(
                      'flex flex-col gap-1 rounded-[8px] border px-3 py-2.5',
                      SLOT_CELL[status],
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={s.label}>
                        {s.label}
                      </span>
                      <StatusBadge tone={meta.tone} size="xs">
                        {meta.text}
                      </StatusBadge>
                    </div>
                    <span
                      className="line-clamp-2 text-[10.5px] leading-[1.5] text-muted-foreground"
                      title={s.reason || (s.file_names ?? []).join('、')}
                    >
                      {s.reason || (s.file_names ?? []).join('、') || '—'}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="mt-2.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              「待更新」不阻塞立案 —— 可以先递后补；「缺件」才是硬阻塞。
            </p>
          </>
        ) : (
          <EmptyBlock>还没有材料，先上传卷宗。</EmptyBlock>
        )}
      </WorkCard>
      </div>
    </div>
  )
}
