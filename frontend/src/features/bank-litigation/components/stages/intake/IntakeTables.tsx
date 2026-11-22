/**
 * ① 收案的左列展示块：来源卡 / 处理流水 / 自动拆分结果表。
 *
 * 三块都是只读呈现（数据来自 demo-data，点行开抽屉）。
 * 抽出来后 `IntakePanel` 只剩「动作卡 → 统计 → 左列组件 + 右栏 → 抽屉」的编排。
 */

import { AlertTriangle, CheckCircle2, FileStack, HelpCircle, Upload } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ClickableRow } from '../../ClickableRow'
import { DEMO_INTAKE_EVENTS, DEMO_INTAKE_SEGMENTS } from '../../demo-data'
import { ActionButton, InsetBlock, Pill, SectionTitle, WorkCard } from '../../ui'

/** 这一包从哪来：来源渠道与体积（客户链接上传 → 服务端合并成单一 PDF） */
export function IntakeSourceSummaryCard() {
  return (
            <WorkCard>
        <SectionTitle title="这一包从哪来" hint="客户上传 · 6 个源文件合并" />
        <InsetBlock className="mt-2.5">
          <div className="flex items-center gap-2.5">
            <FileStack className="size-4 flex-none text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium">银行个贷不良_首批材料.zip</div>
              <div className="mt-0.5 text-[10.5px] text-muted-foreground">
                客户经理 王某某 通过客户链接上传 · 10-28 09:41 · 12.4 MB
              </div>
            </div>
            <Pill tone="green">已下载</Pill>
          </div>
        </InsetBlock>
      </WorkCard>
  )
}

/** 处理流水：从收到到拆完的每一步与耗时 */
export function IntakeEventFlow() {
  return (
            <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SectionTitle title="处理流水" hint="从收到到拆完 · 用时 9.2 秒" className="w-full" />
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_INTAKE_EVENTS.map((e) => (
            <li key={e.at + e.event} className="flex items-center gap-3 px-5 py-2">
              <span className="w-[82px] flex-none text-[10.5px] tabular-nums text-muted-foreground">{e.at}</span>
              <Pill tone="blue">{e.event}</Pill>
              <span className="min-w-0 flex-1 truncate text-[11.5px]" title={e.detail}>{e.detail}</span>
              <span className="w-[56px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                {e.ms ? `${e.ms} ms` : '—'}
              </span>
            </li>
          ))}
        </ul>
      </WorkCard>
  )
}

/** 自动拆分结果：逐份状态与置信度，点行开抽屉复核 */
export function SegmentResultTable({
  segmentCount,
  excludedSeqs,
  onPick,
  onAppend,
}: {
  /** 拆出的份数（面板顶部统计用的是同一个数，从这里传进来避免两处各算一遍） */
  segmentCount: number
  /** 已排除的材料 seq */
  excludedSeqs: Set<number>
  onPick: (seq: number) => void
  onAppend: () => void
}) {
  return (
      <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SectionTitle
            title="自动拆分结果"
            hint={`按页内容识别 · ${segmentCount} 份`}
            className="w-full"
            action={
              <ActionButton sm onClick={onAppend}>
                <Upload className="size-3" /> 追加材料
              </ActionButton>
            }
          />
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_INTAKE_SEGMENTS.map((s) => (
            <ClickableRow
              key={s.seq}
              onClick={() => onPick(s.seq)}
              className="flex items-start gap-3 px-5 py-2.5"
            >
              <span
                className={cn(
                  'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                  s.status === 'ok'
                    ? 'bg-status-green'
                    : s.status === 'review'
                      ? 'bg-status-yellow'
                      : 'bg-status-red',
                )}
              >
                {s.status === 'ok' ? (
                  <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                ) : s.status === 'review' ? (
                  <HelpCircle className="size-2.5 text-white" strokeWidth={3} />
                ) : (
                  <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[12.5px] font-medium">{s.fileName}</span>
                  <Pill tone="blue">{s.type}</Pill>
                  <span className="text-[10.5px] tabular-nums text-muted-foreground">{s.pages}</span>
                  {excludedSeqs.has(s.seq) ? <Pill tone="neutral">已排除</Pill> : null}
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground">{s.note}</div>
              </div>
              <div className="flex flex-none items-center gap-2">
                <span
                  className={cn(
                    'text-[11px] tabular-nums',
                    s.confidence >= 0.9
                      ? 'text-muted-foreground'
                      : s.confidence >= 0.5
                        ? 'text-status-yellow'
                        : 'text-status-red',
                  )}
                >
                  {(s.confidence * 100).toFixed(0)}%
                </span>
                <span className="w-[52px] text-right">
                  <Pill
                    tone={
                      s.status === 'ok' ? 'green' : s.status === 'review' ? 'yellow' : 'red'
                    }
                  >
                    {s.status === 'ok' ? '已认准' : s.status === 'review' ? '待核对' : '未识别'}
                  </Pill>
                </span>
              </div>
            </ClickableRow>
          ))}
        </ul>
      </WorkCard>
  )
}
