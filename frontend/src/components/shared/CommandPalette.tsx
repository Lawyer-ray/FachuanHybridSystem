import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router'
import {
  LayoutDashboard,
  Inbox,
  Users,
  FileText,
  Briefcase,
  Settings,
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
import { createFeatureApiClient } from '@/lib/api'

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

interface SearchResultItem {
  id: number
  title: string
  subtitle: string
}

interface GlobalSearchResult {
  clients: SearchResultItem[]
  cases: SearchResultItem[]
  contracts: SearchResultItem[]
  inbox: SearchResultItem[]
  court_sms: SearchResultItem[]
  contacts: SearchResultItem[]
}

const searchApi = createFeatureApiClient('search')

const RESULT_GROUPS: { key: keyof GlobalSearchResult; label: string; icon: React.ReactNode; getPath: (item: SearchResultItem) => string }[] = [
  { key: 'clients', label: '当事人', icon: <Users className="w-4 h-4" />, getPath: (item) => `/admin/clients/${item.id}` },
  { key: 'cases', label: '案件', icon: <Briefcase className="w-4 h-4" />, getPath: (item) => `/admin/cases/${item.id}` },
  { key: 'contracts', label: '合同', icon: <FileText className="w-4 h-4" />, getPath: (item) => `/admin/contracts/${item.id}` },
  { key: 'contacts', label: '工作人员', icon: <Users className="w-4 h-4" />, getPath: (_item) => `/admin/cases` },
  { key: 'inbox', label: '收件箱', icon: <Inbox className="w-4 h-4" />, getPath: () => PATHS.ADMIN_INBOX },
  { key: 'court_sms', label: '法院短信', icon: <MessageSquare className="w-4 h-4" />, getPath: () => PATHS.ADMIN_TOOLS_COURT_SMS },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GlobalSearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const navigate = useNavigate()
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', down)
    return () => {
      document.removeEventListener('keydown', down)
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  useEffect(() => {
    if (!open) {
      setQuery('')
      setResults(null)
    }
  }, [open])

  const doSearch = useCallback(async (q: string) => {
    if (!q || q.trim().length < 1) {
      setResults(null)
      setSearching(false)
      return
    }
    setSearching(true)
    try {
      const data = await searchApi.get('', { searchParams: { q: q.trim(), limit: '5' } }).json<GlobalSearchResult>()
      setResults(data)
    } catch {
      setResults(null)
    } finally {
      setSearching(false)
    }
  }, [])

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!value.trim()) {
      setResults(null)
      setSearching(false)
      return
    }
    setSearching(true)
    debounceRef.current = setTimeout(() => doSearch(value), 300)
  }, [doSearch])

  const handleSelect = useCallback((path: string) => {
    setOpen(false)
    navigate(path)
  }, [navigate])

  const hasResults = results && RESULT_GROUPS.some((g) => results[g.key].length > 0)

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="搜索功能、当事人、案件、合同..."
        value={query}
        onValueChange={handleQueryChange}
      />
      <CommandList>
        <CommandEmpty>
          {searching ? '搜索中...' : query ? '未找到相关数据' : '输入关键词搜索...'}
        </CommandEmpty>

        {/* Navigation commands */}
        {!query && (
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
        )}

        {/* Search results */}
        {query && hasResults && RESULT_GROUPS.map((group) => {
          const items = results[group.key]
          if (items.length === 0) return null
          return (
            <CommandGroup key={group.key} heading={group.label}>
              {items.map((item) => (
                <CommandItem
                  key={`${group.key}-${item.id}`}
                  value={`${item.title} ${item.subtitle}`}
                  onSelect={() => handleSelect(group.getPath(item))}
                  className="cursor-pointer"
                >
                  {group.icon}
                  <div className="flex flex-col min-w-0">
                    <span className="truncate">{item.title}</span>
                    {item.subtitle && (
                      <span className="text-xs text-muted-foreground truncate">{item.subtitle}</span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          )
        })}

        {/* Navigation commands when searching (as fallback) */}
        {query && (
          <CommandGroup heading="导航">
            {commands
              .filter((cmd) => {
                const q = query.toLowerCase()
                return cmd.label.toLowerCase().includes(q) || cmd.keywords?.some((k) => k.includes(q))
              })
              .map((cmd) => (
                <CommandItem
                  key={cmd.path}
                  value={`nav ${cmd.label} ${cmd.keywords?.join(' ') ?? ''}`}
                  onSelect={() => handleSelect(cmd.path)}
                  className="cursor-pointer"
                >
                  {cmd.icon}
                  <span>{cmd.label}</span>
                </CommandItem>
              ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  )
}
