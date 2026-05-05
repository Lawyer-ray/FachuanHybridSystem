import { Inbox, Users, FileText, Briefcase, Search, FolderOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'

const icons = {
  inbox: Inbox,
  users: Users,
  file: FileText,
  case: Briefcase,
  search: Search,
  folder: FolderOpen,
}

interface EmptyStateProps {
  icon?: keyof typeof icons
  title?: string
  description?: string
  actionText?: string
  onAction?: () => void
}

export function EmptyState({
  icon = 'inbox',
  title = '暂无数据',
  description,
  actionText,
  onAction,
}: EmptyStateProps) {
  const Icon = icons[icon]

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-muted-foreground" />
      </div>
      <h3 className="text-base font-semibold text-foreground mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mb-4 text-center max-w-sm">
          {description}
        </p>
      )}
      {actionText && onAction && (
        <Button size="sm" onClick={onAction}>
          {actionText}
        </Button>
      )}
    </div>
  )
}
