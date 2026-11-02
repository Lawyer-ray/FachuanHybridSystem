import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useMaterialStatus, useReadiness } from '../hooks/use-cases'
import type { SlotStatus } from '../types'
import {
  DEMO_READINESS_CHECK_BASIS,
  DEMO_READINESS_HISTORY,
  DEMO_READINESS_PEERS,
  DEMO_READINESS_SLOT_META,
} from './demo-data'
import { MaterialFileList } from './readiness/MaterialFileList'
import {
  Chip,
  KeyValueRow,
  Pill,
  RailSection,
  SectionTitle,
  StatCell,
  StatStrip,
  WorkCard,
} from './ui'

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
  // 齐备用「更白的白」（bg-background）+ 淡边框，与 deal-detail 的内嵌块同口径；
  // 缺件才染色。一屏只有一种告警色，齐备项不该抢注意力。
  ok: 'border-border-light bg-background',
  miss: 'border-status-red/40 bg-status-red-bg',
  stale: 'border-status-yellow/40 bg-status-yellow-bg',
  na: 'border-border-light bg-secondary/40',
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
    <div className="flex min-h-[1780px] flex-col gap-3.5">
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
            {!r
              ? '校验服务暂无响应'
              : noRule
                ? '本阶段暂无专门校验'
                : r.ready
                  ? '起诉条件已满足，可以立案'
                  : `还有 ${failed} 项没过，先补齐`}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            {!r
              ? '起诉条件引擎这次没返回结果（连线不稳）。下面三块是本案已有的卷宗事实，条件结论请点「重新校验」。'
              : noRule
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
      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell
          label="法律要件"
          value={`${r?.passed ?? 0}/${r?.total ?? 0}`}
          tone={r?.ready ? 'green' : 'red'}
        />
        <StatCell
          label="材料缺件"
          value={m ? `${m.missing_count} 项` : '—'}
          tone={m && m.missing_count > 0 ? 'red' : 'green'}
        />
        <StatCell label="案件阶段" value={r?.stage === 'first_trial' ? '一审' : r?.stage || '—'} />
        <StatCell
          label="校验模式"
          value={noRule ? '不判断' : r?.mode === 'appeal' ? '答辩条件' : '起诉条件'}
          tone={noRule ? 'yellow' : 'neutral'}
        />
      </StatStrip>

      {/* ══ ③④ 双栏：左法律要件，右材料齐备。
          原来是上下两块单列，1080p 屏上只占上半屏；并排后填满宽度、信息密度翻倍，
          并且「法律要件 vs 卷宗要件」这个对比关系在版面上也就成立了。 ══ */}
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_300px]">
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
          <div className="mt-2.5 flex flex-col gap-1.5">
            {r.checks.map((c) => {
              const basis = DEMO_READINESS_CHECK_BASIS[c.key]
              return (
              <div
                key={c.key}
                className={cn(
                  'flex items-start gap-2.5 rounded-[9px] border px-3 py-2.5',
                  c.ok
                    ? 'border-border-light bg-background'
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
                  {basis ? (
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10.5px] text-muted-foreground">
                      <span>判定依据：{basis.basis}</span>
                      <span className="tabular-nums">数据来源：{basis.source}</span>
                      {c.field ? <span className="tabular-nums">字段：{c.field}</span> : null}
                    </div>
                  ) : null}
                </div>
              </div>
              )
            })}
          </div>
        ) : (
          <p className="mt-2.5 text-[11.5px] text-muted-foreground">
            {noRule
              ? '执行、仲裁等阶段还没有对应的校验规则 —— 不是「已通过」，只是这里不判断。'
              : '暂无校验项。'}
          </p>
        )}
      </WorkCard>

      {/* 右栏：一卡多段（照 deal-detail 的 DetailRail） */}
      <WorkCard padded={false}>
        <RailSection title="本次校验">
          <StatStrip className="grid-cols-2">
            <StatCell label="法律要件" value={`${r?.passed ?? 0}/${r?.total ?? 0}`} tone={r?.ready ? 'green' : 'red'} />
            <StatCell label="材料缺件" value={m ? `${m.missing_count}` : '—'} tone={m && m.missing_count > 0 ? 'red' : 'green'} />
          </StatStrip>
          <dl className="mt-2.5">
            <KeyValueRow label="案件阶段">
              <span className="text-[12px]">{r?.stage === 'first_trial' ? '一审' : r?.stage || '—'}</span>
            </KeyValueRow>
            <KeyValueRow label="校验模式">
              <span className="text-[12px]">{noRule ? '不判断' : r?.mode === 'appeal' ? '答辩条件' : '起诉条件'}</span>
            </KeyValueRow>
            <KeyValueRow label="结论">
              <Pill tone={r?.ready ? 'green' : 'red'}>{r?.ready ? '可以立案' : `差 ${failed} 项`}</Pill>
            </KeyValueRow>
          </dl>
        </RailSection>

        <RailSection
          title="材料齐备"
          action={
            material.loading ? (
              <Loader2 className="size-3 animate-spin text-muted-foreground" />
            ) : (
              <span className="text-[10.5px] tabular-nums text-muted-foreground">
                {m ? `${m.ok_count}/${m.need_count}` : '—'}
              </span>
            )
          }
        >
        {material.error ? (
          <p className="mt-2.5 text-[11.5px] text-status-red">{material.error}</p>
        ) : m?.slots?.length ? (
          <>
            <div className="flex flex-col gap-1.5">
              {m.slots.map((s) => {
                const meta = SLOT_META[s.status ?? 'miss'] ?? SLOT_META.miss
                const status = s.status ?? 'miss'
                const extra = DEMO_READINESS_SLOT_META[s.key]
                return (
                  <div
                    key={s.key}
                    className={cn(
                      'flex flex-col gap-0.5 rounded-[8px] border px-2.5 py-2',
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
                    {extra ? (
                      <span className="flex items-center gap-2 text-[10px] tabular-nums text-muted-foreground/85">
                        <span>{extra.fileCount} 个文件</span>
                        <span className="text-border">·</span>
                        <span>{extra.lastAt}</span>
                        <span className="min-w-0 truncate" title={extra.source}>
                          {extra.source}
                        </span>
                      </span>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </>
        ) : (
          <EmptyBlock>还没有材料，先上传卷宗。</EmptyBlock>
        )}
        </RailSection>

        <RailSection title="判定口径">
          <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
            「待更新」不阻塞立案 —— 可以先递后补；「缺件」才是硬阻塞。
            法律要件与卷宗要件都过，才允许推进到一张网递交。
          </p>
        </RailSection>
      </WorkCard>
      </div>

      {/* ══ ⑤ 下方三块：历史校验 / 同类案件对比 / 材料清单明细。
          真实数据只到「本次校验」为止，这三块是演示态的来龙去脉 ——
          律师最常追问的是「上次为什么没过」「同批其他案件过了吗」「到底传了哪些文件」。 ══ */}
      <div className="grid grid-cols-1 items-stretch gap-3 xl:grid-cols-[minmax(0,1fr)_372px]">
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle
              title="历史校验记录"
              hint={`最近 ${DEMO_READINESS_HISTORY.length} 次 · 归案后与每日定时各校一次`}
              className="w-full"
              action={<Pill tone={r?.ready ? 'green' : 'red'}>{r?.ready ? '当前通过' : '当前未通过'}</Pill>}
            />
          </div>
          <div className="grid grid-cols-[74px_52px_74px_62px_64px_minmax(0,1fr)] gap-2 border-b border-border-light bg-secondary/40 px-5 py-1.5 text-[10.5px] font-medium text-muted-foreground">
            <span>时间</span>
            <span>结果</span>
            <span className="text-right">通过</span>
            <span className="text-right">缺件</span>
            <span>操作人</span>
            <span>说明</span>
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_READINESS_HISTORY.map((h) => (
              <li
                key={h.at}
                className="grid grid-cols-[74px_52px_74px_62px_64px_minmax(0,1fr)] items-center gap-2 px-5 py-2"
              >
                <span className="text-[10.5px] tabular-nums text-muted-foreground">{h.at}</span>
                <span>
                  <Pill tone={h.result === 'pass' ? 'green' : 'red'}>
                    {h.result === 'pass' ? '通过' : '未通过'}
                  </Pill>
                </span>
                <span className="text-right text-[11px] tabular-nums">
                  {h.passed}/{h.total}
                </span>
                <span
                  className={cn(
                    'text-right text-[11px] tabular-nums',
                    h.missing > 0 ? 'text-status-red' : 'text-muted-foreground',
                  )}
                >
                  {h.missing}
                </span>
                <span className="truncate text-[11px] text-muted-foreground" title={h.by}>
                  {h.by}
                </span>
                <span className="truncate text-[11px] text-muted-foreground" title={h.note}>
                  {h.note}
                </span>
              </li>
            ))}
          </ul>
        </WorkCard>

        <WorkCard padded={false}>
          <RailSection title="同类案件对比" action={<Chip>同一委托 · {DEMO_READINESS_PEERS.length} 件</Chip>}>
            <StatStrip className="grid-cols-3">
              <StatCell
                label="已有结论"
                value={DEMO_READINESS_PEERS.filter((p) => p.missing === 0).length}
                tone="green"
              />
              <StatCell
                label="缺件待补"
                value={DEMO_READINESS_PEERS.filter((p) => p.missing > 0).length}
                tone="red"
              />
              <StatCell
                label="同批通过率"
                value={`${Math.round(
                  (DEMO_READINESS_PEERS.filter((p) => p.missing === 0).length / DEMO_READINESS_PEERS.length) * 100,
                )}%`}
              />
            </StatStrip>
            <ul className="mt-2 flex flex-col gap-[5px]">
              {DEMO_READINESS_PEERS.map((p) => (
                <li key={p.caseName} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-[11px]" title={p.caseName}>
                    {p.caseName.replace('某某银行广州分行诉', '').replace('金融借款合同纠纷', '')}
                  </span>
                  <span className="flex-none text-[10px] text-muted-foreground">{p.stage}</span>
                  <span className="w-[46px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                    {p.passed}/{p.total}
                  </span>
                  <Pill tone={p.missing === 0 ? 'green' : 'red'}>
                    {p.missing === 0 ? '齐备' : `缺 ${p.missing}`}
                  </Pill>
                </li>
              ))}
            </ul>
          </RailSection>

          <RailSection title="判定口径">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              「待更新」不阻塞立案 —— 可以先递后补；「缺件」才是硬阻塞。
              法律要件与卷宗要件都过，才允许推进到一张网递交。
            </p>
          </RailSection>

          <RailSection title="数据来源">
            <dl>
              <KeyValueRow label="法律要件">
                <span className="text-[11.5px] tabular-nums">CaseReadiness</span>
              </KeyValueRow>
              <KeyValueRow label="材料槽位">
                <span className="text-[11.5px] tabular-nums">CaseMaterial</span>
              </KeyValueRow>
              <KeyValueRow label="对比范围">
                <span className="text-[11.5px]">同一委托合同下的全部案件</span>
              </KeyValueRow>
            </dl>
          </RailSection>
        </WorkCard>
      </div>

      <MaterialFileList />
    </div>
  )
}
