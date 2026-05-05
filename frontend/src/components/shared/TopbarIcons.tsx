import { useNavigate, useLocation } from 'react-router'
import { Inbox, MessageSquare, ScrollText, FileStack, ListTodo } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PATHS } from '@/routes/paths'

interface TopbarIcon {
  id: string
  icon: React.ReactNode
  title: string
  path: string
  badge?: number
}

const topbarIcons: TopbarIcon[] = [
  { id: 'inbox', icon: <Inbox className="w-[18px] h-[18px]" />, title: '收件箱', path: PATHS.ADMIN_INBOX },
  { id: 'message-source', icon: <MessageSquare className="w-[18px] h-[18px]" />, title: '消息来源', path: PATHS.ADMIN_MESSAGE_SOURCES },
  { id: 'logs', icon: <ScrollText className="w-[18px] h-[18px]" />, title: '日志', path: PATHS.ADMIN_LOGS },
  { id: 'templates', icon: <FileStack className="w-[18px] h-[18px]" />, title: '文件模板', path: PATHS.ADMIN_TEMPLATES },
  { id: 'task', icon: <ListTodo className="w-[18px] h-[18px]" />, title: 'Task 队列', path: PATHS.ADMIN_TASK_QUEUE },
]

export function TopbarIcons() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div className="flex items-center gap-0.5">
      {topbarIcons.map((item) => {
        const isActive = location.pathname.startsWith(item.path)
        return (
          <button
            key={item.id}
            title={item.title}
            onClick={() => navigate(item.path)}
            className={cn(
              'relative p-2 rounded-md transition-colors',
              isActive
                ? 'bg-accent text-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent'
            )}
          >
            {item.icon}
            {item.badge != null && item.badge > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-status-red text-white text-[10px] font-medium px-1">
                {item.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
