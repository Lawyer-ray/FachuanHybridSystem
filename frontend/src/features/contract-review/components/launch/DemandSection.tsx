import { cn } from '@/lib/utils'
import { DEMAND_CHIPS } from '../../constants'
import { SectionHead } from './SectionHead'

/**
 * ③ 特别交代——写进审查 prompt 的客户诉求。
 *
 * chips 只是把常见说法一键拼进 textarea（逗号分隔），拼完律师还能继续改；
 * 提交时同一份文本既作 `client_note` 全文，也按逗号拆成 `client_demands`。
 */
export function DemandSection({
  note,
  onChangeNote,
  onToggleChip,
}: {
  note: string
  onChangeNote: (v: string) => void
  onToggleChip: (text: string) => void
}) {
  return (
    <section className="py-4">
      <SectionHead index={3} title="特别交代" note="选填" />
      <textarea
        className="w-full resize-y rounded-[8px] border border-border bg-card px-2.5 py-2 text-[12.5px] leading-[1.6] outline-none focus:border-foreground"
        rows={3}
        placeholder="客户有没有特别在意的点？比如「这单一定要压工期，预算不能再加」"
        value={note}
        onChange={(e) => onChangeNote(e.target.value)}
      />
      <div className="mt-2 flex flex-wrap gap-1.5">
        {DEMAND_CHIPS.map((c) => {
          const on = note.includes(c.text)
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => onToggleChip(c.text)}
              className={cn(
                'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                on
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-card text-secondary-foreground hover:border-input',
              )}
            >
              {c.text}
            </button>
          )
        })}
      </div>
    </section>
  )
}
