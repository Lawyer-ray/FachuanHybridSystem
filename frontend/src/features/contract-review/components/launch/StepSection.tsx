import { cn } from '@/lib/utils'
import { STEPS } from '../../constants'
import { SectionHead } from './SectionHead'

/** ② 审查哪些方面——对应后端 selected_steps；一项都不选会被拦住 */
export function StepSection({
  steps,
  onToggle,
}: {
  steps: Record<string, boolean>
  onToggle: (key: string) => void
}) {
  return (
    <section className="border-b border-border-light py-4">
      <SectionHead index={2} title="审查哪些方面？" />
      <div className="flex flex-col gap-1.5">
        {STEPS.map((s) => (
          <label
            key={s.key}
            className={cn(
              'flex cursor-pointer items-start gap-2.5 rounded-[8px] border px-2.5 py-2 transition-colors',
              steps[s.key] ? 'border-input bg-secondary/60' : 'border-border bg-card hover:border-input',
            )}
          >
            <input
              type="checkbox"
              className="mt-0.5 accent-foreground"
              checked={!!steps[s.key]}
              onChange={() => onToggle(s.key)}
            />
            <span className="min-w-0 flex-1">
              <b className="block text-[12.5px] font-[600]">{s.label}</b>
              <em className="mt-0.5 block text-[11px] not-italic text-muted-foreground">{s.desc}</em>
            </span>
          </label>
        ))}
      </div>
    </section>
  )
}
