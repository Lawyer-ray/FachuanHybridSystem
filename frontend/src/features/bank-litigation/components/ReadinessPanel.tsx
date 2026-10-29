import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useMaterialStatus, useReadiness } from '../hooks/use-cases'
import type { SlotStatus } from '../types'

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
 * ═══ 三态色彩纪律 ═══
 * 不通过的一律上色（红），通过的用中性灰勾 —— 一屏只有一种告警色，
 * 这样「哪几项没过」才跳得出来。全部通过时才给绿色。
 */

/** 槽位状态 → 语气 + 文案 */
const SLOT_META: Record<SlotStatus, { tone: Tone; text: string }> = {
  ok: { tone: 'neutral', text: '齐备' },
  miss: { tone: 'red', text: '缺件' },
  stale: { tone: 'yellow', text: '待更新' },
  na: { tone: 'neutral', text: '不适用' },
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

  return (
    <div className="flex flex-col gap-3">
      {/* ── 一句话结论 ── */}
      <div
        className={cn(
          'flex items-center gap-2 rounded-[8px] border px-3 py-2 text-[12.5px]',
          r?.ready
            ? 'border-status-green/40 bg-status-green-bg text-status-green'
            : 'border-status-red/40 bg-status-red-bg text-status-red',
        )}
      >
        {r?.ready ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
        <span className="font-medium">
          {r?.ready ? '起诉条件已满足，可以立案' : `还有 ${(r?.total ?? 0) - (r?.passed ?? 0)} 项没过`}
        </span>
        {r ? (
          <span className="ml-auto tabular-nums opacity-80">
            {r.passed}/{r.total}
          </span>
        ) : null}
      </div>

      {/* ── 起诉条件逐条 ── */}
      <section>
        <h3 className="mb-1.5 text-[11px] font-semibold text-muted-foreground">
          {r?.mode === 'appeal' ? '答辩条件' : r?.mode === 'other' ? '本阶段暂无专门校验' : '起诉条件'}
        </h3>
        {r?.checks?.length ? (
          <ul className="flex flex-col gap-1">
            {r.checks.map((c) => (
              <li key={c.key} className="flex items-start gap-2 text-[12px] leading-[1.6]">
                {c.ok ? (
                  <Circle className="mt-[3px] size-3 flex-none fill-current text-muted-foreground/30 text-transparent" />
                ) : (
                  <AlertTriangle className="mt-[3px] size-3 flex-none text-status-red" />
                )}
                <span className={cn('flex-none', c.ok ? 'text-secondary-foreground' : 'font-medium')}>
                  {c.label}
                </span>
                <span
                  className={cn(
                    'min-w-0 flex-1 truncate text-[11.5px]',
                    c.ok ? 'text-muted-foreground' : 'text-status-red',
                  )}
                  title={c.detail}
                >
                  {c.detail}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11.5px] text-muted-foreground">
            {r?.mode === 'other'
              ? '执行、仲裁等阶段还没有对应的校验规则 —— 不是「已通过」，只是这里不判断。'
              : '暂无校验项。'}
          </p>
        )}
      </section>

      {/* ── 材料齐备度 ── */}
      <section>
        <h3 className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold text-muted-foreground">
          材料齐备
          {m ? (
            <span className="font-normal tabular-nums">
              {m.ok_count}/{m.need_count}
              {m.missing_count > 0 ? ` · 缺 ${m.missing_count}` : ''}
            </span>
          ) : null}
          {material.loading ? <Loader2 className="size-3 animate-spin" /> : null}
        </h3>
        {material.error ? (
          <p className="text-[11.5px] text-status-red">{material.error}</p>
        ) : m?.slots?.length ? (
          <ul className="flex flex-col gap-1">
            {m.slots.map((s) => {
              const meta = SLOT_META[s.status ?? 'miss'] ?? SLOT_META.miss
              return (
                <li key={s.key} className="flex items-center gap-2 text-[12px]">
                  <span className="w-[110px] flex-none text-secondary-foreground">{s.label}</span>
                  <StatusBadge tone={meta.tone} size="xs">
                    {meta.text}
                  </StatusBadge>
                  <span
                    className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground"
                    title={s.reason || (s.file_names ?? []).join('、')}
                  >
                    {s.reason || (s.file_names ?? []).join('、') || '—'}
                  </span>
                </li>
              )
            })}
          </ul>
        ) : (
          <EmptyBlock>还没有材料，先上传卷宗。</EmptyBlock>
        )}
        <p className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          「待更新」不阻塞立案 —— 可以先递后补；「缺件」才是硬阻塞。
        </p>
      </section>

      <Button variant="ghost" size="xs" className="self-start" onClick={() => {
        ready.reload()
        material.reload()
      }}>
        重新校验
      </Button>
    </div>
  )
}
