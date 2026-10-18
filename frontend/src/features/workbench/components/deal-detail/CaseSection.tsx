import type { DealCase } from '../../types'
import { caseMetaParts, legalStatusGroups, timelineEntries } from './detail-domain'
import { ActionButton, Card, Chip, MetaLine, Pill, StateDot } from './ui'

/**
 * 程序节（一桩案件）：状态点 + 阶段名 + 已结/在办 + 案号 chips ＋ meta 行（机构/收案/案由/标的/保全）
 * ＋ 诉讼地位行 ＋ 该案日志时间轴（升序叙事）。同阶段多案时补案名消歧。
 */
export function CaseSection({
  c,
  ambiguous,
  highlighted,
  onAddLog,
}: {
  c: DealCase
  /** 同阶段多案（如按被告分立）时节标题带案名才分得清 */
  ambiguous: boolean
  /** stepper 跳转后的短暂高亮环 */
  highlighted: boolean
  onAddLog: () => void
}) {
  const legGroups = legalStatusGroups(c)
  const entries = timelineEntries(c)
  return (
    <Card
      id={'case-' + c.id}
      className={
        'scroll-mt-[76px] transition-shadow duration-700 ' + (highlighted ? 'shadow-[0_0_0_3px_rgba(24,24,27,0.14)]' : '')
      }
    >
      <div className="flex flex-wrap items-baseline gap-2.5 px-5 pt-[15px] max-[680px]:px-3.5">
        <span className="relative top-[-1px]">
          <StateDot state={c.done ? 'done' : 'cur'} size={c.done ? 9 : 10} />
        </span>
        <b className="text-[15.5px] font-[720] tracking-[-0.015em]" title={c.name}>
          {c.proc}
        </b>
        <Pill>{c.done ? '已结' : '在办'}</Pill>
        {c.numbers.map((n) => (
          <Chip key={n}>{n}</Chip>
        ))}
        <span className="relative top-[-2px] ml-auto">
          <ActionButton sm onClick={onAddLog}>
            ＋ 记日志
          </ActionButton>
        </span>
      </div>
      {ambiguous && (
        <div className="truncate px-5 pt-1 text-xs text-muted-foreground max-[680px]:px-3.5" title={c.name}>
          {c.name}
        </div>
      )}

      <MetaLine
        parts={caseMetaParts(c)}
        className="px-5 pt-[7px] text-[12.5px] leading-[1.9] text-muted-foreground tabular-nums max-[680px]:px-3.5"
      />

      {legGroups.length > 0 && (
        <div className="mx-5 mt-[9px] rounded-[9px] border border-border-light bg-background px-3 py-2 text-[12.5px] leading-[1.9] text-muted-foreground max-[680px]:mx-3.5">
          {legGroups.map((g, i) => (
            <span key={g.status}>
              {i > 0 && <span className="mx-1.5 text-border">·</span>}
              <b className="font-[620] text-secondary-foreground">{g.status}</b> {g.names.join('、')}
            </span>
          ))}
        </div>
      )}

      <div className="px-5 pt-3.5 pb-1.5 max-[680px]:px-3.5">
        {entries.length === 0 ? (
          <div className="py-2 text-xs text-muted-foreground/70">还没有办案日志</div>
        ) : (
          entries.map((e, i) => (
            <div
              key={e.key}
              className={
                'relative grid grid-cols-[80px_16px_1fr] pb-[15px] max-[680px]:grid-cols-[66px_14px_1fr] ' +
                (i === entries.length - 1 ? 'pb-2' : '')
              }
            >
              {/* 竖线贯穿到下一条（最后一条不画），点用元素而非伪元素便于对齐 */}
              {i < entries.length - 1 && (
                <span className="absolute top-3.5 -bottom-1 left-[87px] w-px bg-border-light max-[680px]:left-[72px]" />
              )}
              <span className="pt-px text-right text-xs whitespace-nowrap text-muted-foreground tabular-nums">{e.date}</span>
              <span className="relative">
                <span className="absolute top-[6px] left-[5px] size-[7px] rounded-full bg-border" />
              </span>
              <span className="min-w-0 pl-1.5">
                {/* 日志正文可能含法院短信里的长 URL 等不可断行串，break-words 防止撑破窄屏 */}
                <span className="block text-[13.5px] leading-[1.55] break-words text-secondary-foreground">{e.text}</span>
                {(e.who || e.attN > 0) && (
                  <span className="mt-0.5 block text-[11.5px] text-muted-foreground/80 tabular-nums">
                    {e.who}
                    {e.attN > 0 && <span className="ml-2">📎 {e.attN}</span>}
                  </span>
                )}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  )
}

/** 执行虚节点：判决生效后可立执行案（可按被执行人分立多线） */
export function VirtualExecRow({ onCreate }: { onCreate: () => void }) {
  return (
    <Card className="flex flex-wrap items-center gap-3 px-5 py-3.5 max-[680px]:px-3.5">
      <span className="size-[11px] flex-none rounded-full border-[1.5px] border-dashed border-border" />
      <span className="text-sm font-[620] text-muted-foreground">执行</span>
      <span className="text-[12.5px] text-muted-foreground/70">判决生效后启动 · 可按被执行人分立多线</span>
      <span className="ml-auto max-[680px]:ml-0">
        <ActionButton onClick={onCreate} title="新建执行案">
          ＋ 立执行案
        </ActionButton>
      </span>
    </Card>
  )
}
