import { cn } from '@/lib/utils'

import { DEMO_BUNDLE_CAPABILITIES, DEMO_BUNDLE_SEGMENT_DETAIL } from '../demo-data'
import { Chip, Pill, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'

/**
 * 识别能力墙：本模板支持的每类材料 + 本月拆过几次 + 平均置信度。
 *
 * 「本月拆过 N 次」比单纯列类型名有用：律师能看出哪几类是常客
 * （借款合同、身份证明），哪几类是边缘（判决书、答辩状，二审模板才用）。
 */
export function TemplateWall() {
  const monthTotal = DEMO_BUNDLE_CAPABILITIES.reduce((s, c) => s + c.monthCount, 0)
  const lowConfidence = DEMO_BUNDLE_CAPABILITIES.filter((c) => c.avgConfidence < 0.8)

  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle
          title="识别能力"
          hint={`本模板支持 ${DEMO_BUNDLE_CAPABILITIES.length} 类材料 · 本月共拆 ${monthTotal} 份`}
        />
      </div>

      <div className="px-5 pt-3">
        <StatStrip className="grid-cols-4">
          <StatCell label="材料类型" value={DEMO_BUNDLE_CAPABILITIES.length} />
          <StatCell label="本月拆分" value={`${monthTotal} 份`} tone="blue" />
          <StatCell
            label="平均置信度"
            value={(DEMO_BUNDLE_CAPABILITIES.reduce((s, c) => s + c.avgConfidence, 0) / DEMO_BUNDLE_CAPABILITIES.length).toFixed(2)}
            tone="green"
          />
          <StatCell label="易错类型" value={`${lowConfidence.length} 类`} tone="yellow" />
        </StatStrip>
      </div>

      <ul className="mt-3 grid grid-cols-1 gap-x-5 pb-1 sm:grid-cols-2">
        {DEMO_BUNDLE_CAPABILITIES.map((c) => (
          <li
            key={c.label}
            className="flex items-center gap-2 border-t border-border-light px-5 py-[7px]"
          >
            <span className="min-w-0 flex-1 truncate text-[12px]" title={c.label}>
              {c.label}
            </span>
            <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
              本月 {c.monthCount} 次
            </span>
            <span
              className={cn(
                'w-[34px] flex-none text-right text-[10.5px] tabular-nums',
                c.avgConfidence >= 0.9
                  ? 'text-status-green'
                  : c.avgConfidence >= 0.8
                    ? 'text-muted-foreground'
                    : 'text-status-yellow',
              )}
            >
              {c.avgConfidence.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>

      <p className="border-t border-border-light px-5 py-2.5 text-[10.5px] leading-[1.6] text-muted-foreground">
        {lowConfidence.map((c) => c.label).join('、')} 平均置信度偏低，出片率高 —— 多因扫描倾斜或表格版式，
        复核时重点看这几类。
      </p>
    </WorkCard>
  )
}

const FLAG_META = {
  ok: { tone: 'neutral', text: '正常' },
  low_confidence: { tone: 'yellow', text: '需复核' },
  unrecognized: { tone: 'red', text: '未识别' },
} as const

/**
 * 上一包的拆分明细快照：页码区间 / 类型 / 置信度 / 判定依据。
 *
 * idle 态没有真任务可展示，但「上一次拆成什么样」是最有说服力的样例 ——
 * 律师点开就知道复核表长什么样、要核什么。
 */
export function SegmentSnapshot() {
  const pages = DEMO_BUNDLE_SEGMENT_DETAIL.reduce((s, d) => s + (d.pageEnd - d.pageStart + 1), 0)
  const flagged = DEMO_BUNDLE_SEGMENT_DETAIL.filter((d) => d.flag !== 'ok').length

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="上一次拆分明细"
          hint="某某银行对公不良_第二批扫描件.pdf · 312 页"
          className="w-full"
          action={
            <>
              <Chip>{DEMO_BUNDLE_SEGMENT_DETAIL.length} 段</Chip>
              {flagged > 0 ? <Pill tone="yellow">{flagged} 段需复核</Pill> : null}
            </>
          }
        />
      </div>

      <ul className="divide-y divide-border-light">
        {DEMO_BUNDLE_SEGMENT_DETAIL.map((d) => {
          const meta = FLAG_META[d.flag]
          return (
            <li
              key={d.order}
              className="grid grid-cols-[40px_74px_minmax(0,1fr)_120px_52px] items-center gap-2 px-5 py-2"
            >
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {String(d.order).padStart(2, '0')}
              </span>
              <span className="text-[11px] tabular-nums text-secondary-foreground">
                P{d.pageStart}–{d.pageEnd}
              </span>
              <div className="min-w-0">
                <div className="truncate text-[12px]" title={d.filename}>
                  {d.filename}
                </div>
                <div className="truncate text-[10.5px] text-muted-foreground" title={d.evidence}>
                  依据：{d.evidence}
                </div>
              </div>
              <span className="truncate text-[11px] text-muted-foreground">{d.label}</span>
              <div className="flex flex-col items-end gap-0.5">
                <span
                  className={cn(
                    'text-[11px] tabular-nums',
                    d.confidence >= 0.9
                      ? 'text-status-green'
                      : d.confidence >= 0.75
                        ? 'text-secondary-foreground'
                        : 'text-status-red',
                  )}
                >
                  {d.confidence.toFixed(2)}
                </span>
                <span className="text-[9.5px] text-muted-foreground">{meta.text}</span>
              </div>
            </li>
          )
        })}
      </ul>

      <p className="border-t border-border-light px-5 py-2.5 text-[10.5px] leading-[1.6] text-muted-foreground">
        共 {pages} 页覆盖（样例只列前 {DEMO_BUNDLE_SEGMENT_DETAIL.length} 段的代表页），
        空白页不单独成段，重复页指纹相同的只保留一处。
      </p>
    </WorkCard>
  )
}
