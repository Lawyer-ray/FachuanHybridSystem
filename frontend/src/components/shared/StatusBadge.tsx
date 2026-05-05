import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type StatusVariant = 'active' | 'pending' | 'closed' | 'draft' | 'success' | 'warning' | 'error' | 'info' | 'purple'

const variantStyles: Record<StatusVariant, string> = {
  active: 'bg-status-green-bg text-status-green border-status-green/20',
  success: 'bg-status-green-bg text-status-green border-status-green/20',
  pending: 'bg-status-yellow-bg text-status-yellow border-status-yellow/20',
  warning: 'bg-status-yellow-bg text-status-yellow border-status-yellow/20',
  closed: 'bg-muted text-muted-foreground border-border',
  draft: 'bg-muted text-muted-foreground border-border',
  error: 'bg-status-red-bg text-status-red border-status-red/20',
  info: 'bg-status-blue-bg text-status-blue border-status-blue/20',
  purple: 'bg-status-purple-bg text-status-purple border-status-purple/20',
}

interface StatusBadgeProps {
  variant: StatusVariant
  children: React.ReactNode
  className?: string
}

export function StatusBadge({ variant, children, className }: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'rounded-full text-xs font-medium px-2.5 py-0.5',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </Badge>
  )
}
