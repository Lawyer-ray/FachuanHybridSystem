import { cn } from '@/lib/utils'

interface RadioOption {
  value: string
  label: string
}

interface RadioPillGroupProps {
  options: RadioOption[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function RadioPillGroup({ options, value, onChange, className }: RadioPillGroupProps) {
  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {options.map((opt) => (
        <label
          key={opt.value}
          className={cn(
            'inline-flex items-center px-3 py-1.5 rounded-md text-sm cursor-pointer transition-all border',
            value === opt.value
              ? 'border-foreground bg-foreground text-primary-foreground font-medium'
              : 'border-border bg-background text-foreground hover:border-foreground/40'
          )}
        >
          <input
            type="radio"
            className="sr-only"
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
          />
          {opt.label}
        </label>
      ))}
    </div>
  )
}
