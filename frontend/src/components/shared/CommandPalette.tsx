import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  LayoutDashboard,
  Inbox,
  Users,
  FileText,
  Briefcase,
  Settings,
  Shield,
  FileSearch,
  MessageSquare,
  Truck,
  ArrowRightLeft,
  Calculator,
  ListTodo,
  ScrollText,
  FileStack,
} from 'lucide-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { PATHS } from '@/routes/paths'

interface CommandEntry {
  label: string
  icon: React.ReactNode
  path: string
  keywords?: string[]
}

const commands: CommandEntry[] = [
  { label: '仪表盘', icon: <LayoutDashboard className="w-4 h-4" />, path: PATHS.ADMIN_DASHBOARD },
  { label: '收件箱', icon: <Inbox className="w-4 h-4" />, path: PATHS.ADMIN_INBOX, keywords: ['inbox', '邮件'] },
  { label: '当事人管理', icon: <Users className="w-4 h-4" />, path: PATHS.ADMIN_CLIENTS, keywords: ['client', '客户'] },
  { label: '合同管理', icon: <FileText className="w-4 h-4" />, path: PATHS.ADMIN_CONTRACTS, keywords: ['contract'] },
  { label: '案件管理', icon: <Briefcase className="w-4 h-4" />, path: PATHS.ADMIN_CASES, keywords: ['case'] },
  { label: '财产保全询价', icon: <Shield className="w-4 h-4" />, path: PATHS.ADMIN_AUTOMATION_QUOTES },
  { label: '文书智能识别', icon: <FileSearch className="w-4 h-4" />, path: PATHS.ADMIN_AUTOMATION_RECOGNITION },
  { label: '法院短信', icon: <MessageSquare className="w-4 h-4" />, path: PATHS.ADMIN_TOOLS_COURT_SMS },
  { label: '快递查询', icon: <Truck className="w-4 h-4" />, path: PATHS.ADMIN_TOOLS_COURIER },
  { label: '要素式转换', icon: <ArrowRightLeft className="w-4 h-4" />, path: PATHS.ADMIN_TOOLS_ELEMENT },
  { label: 'LPR 计算器', icon: <Calculator className="w-4 h-4" />, path: PATHS.ADMIN_TOOLS_LPR },
  { label: '消息来源', icon: <MessageSquare className="w-4 h-4" />, path: PATHS.ADMIN_MESSAGE_SOURCES },
  { label: '日志', icon: <ScrollText className="w-4 h-4" />, path: PATHS.ADMIN_LOGS },
  { label: '文件模板', icon: <FileStack className="w-4 h-4" />, path: PATHS.ADMIN_TEMPLATES },
  { label: 'Task 队列', icon: <ListTodo className="w-4 h-4" />, path: PATHS.ADMIN_TASK_QUEUE },
  { label: '系统设置', icon: <Settings className="w-4 h-4" />, path: PATHS.ADMIN_SETTINGS },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  const handleSelect = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="搜索功能或输入命令..." />
      <CommandList>
        <CommandEmpty>未找到结果</CommandEmpty>
        <CommandGroup heading="导航">
          {commands.map((cmd) => (
            <CommandItem
              key={cmd.path}
              value={`${cmd.label} ${cmd.keywords?.join(' ') ?? ''}`}
              onSelect={() => handleSelect(cmd.path)}
              className="cursor-pointer"
            >
              {cmd.icon}
              <span>{cmd.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
