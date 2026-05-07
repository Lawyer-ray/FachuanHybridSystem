/** 工作台命令面板（Cmd+Shift+K） */

import {
  Plus,
  Download,
  Bot,
  Briefcase,
  FileText,
  Search,
  Square,
  Cpu,
} from 'lucide-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { useWorkbenchStore } from '../stores/workbench-store'
import { AGENT_OPTIONS, type AgentType } from '../types'
import { exportToMarkdown, downloadFile } from '../utils/export'
import { toast } from 'sonner'

const AGENT_ICONS: Record<AgentType, typeof Bot> = {
  triage: Bot,
  case: Briefcase,
  contract: FileText,
  research: Search,
}

interface WorkbenchCommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onNewSession: () => void
}

export function WorkbenchCommandPalette({
  open,
  onOpenChange,
  onNewSession,
}: WorkbenchCommandPaletteProps) {
  const {
    setSelectedAgent,
    setSelectedModel,
    abortStream,
    isStreaming,
    models,
    messages,
    currentSession,
  } = useWorkbenchStore()

  const handleExport = () => {
    if (!currentSession || messages.length === 0) return
    const md = exportToMarkdown(messages, currentSession.title || '对话')
    downloadFile(md, `${currentSession.title || '对话'}.md`, 'text/markdown;charset=utf-8')
    toast.success('已导出 Markdown')
    onOpenChange(false)
  }

  const handleSelectAgent = (type: AgentType) => {
    setSelectedAgent(type)
    const agent = AGENT_OPTIONS.find((a) => a.type === type)
    toast.success(`已切换到 ${agent?.name || type}`)
    onOpenChange(false)
  }

  const handleSelectModel = (modelId: string) => {
    setSelectedModel(modelId)
    const model = models.find((m) => m.id === modelId)
    toast.success(`已切换到 ${model?.name || modelId}`)
    onOpenChange(false)
  }

  const handleStop = () => {
    if (isStreaming) abortStream()
    onOpenChange(false)
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="输入命令..." />
      <CommandList>
        <CommandEmpty>未找到匹配命令</CommandEmpty>

        <CommandGroup heading="会话">
          <CommandItem
            value="新建会话 new session"
            onSelect={onNewSession}
            className="cursor-pointer"
          >
            <Plus className="size-4" />
            <span>新建会话</span>
            <kbd className="ml-auto text-[10px] text-muted-foreground">⌘N</kbd>
          </CommandItem>
          {currentSession && messages.length > 0 && (
            <CommandItem
              value="导出对话 export markdown"
              onSelect={handleExport}
              className="cursor-pointer"
            >
              <Download className="size-4" />
              <span>导出对话 Markdown</span>
              <kbd className="ml-auto text-[10px] text-muted-foreground">⌘E</kbd>
            </CommandItem>
          )}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="切换助手">
          {AGENT_OPTIONS.map((agent) => {
            const Icon = AGENT_ICONS[agent.type]
            return (
              <CommandItem
                key={agent.type}
                value={`${agent.name} ${agent.type} ${agent.description}`}
                onSelect={() => handleSelectAgent(agent.type)}
                className="cursor-pointer"
              >
                <Icon className="size-4" />
                <div className="flex flex-col">
                  <span>{agent.name}</span>
                  <span className="text-xs text-muted-foreground">{agent.description}</span>
                </div>
              </CommandItem>
            )
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="切换模型">
          {models.map((model) => (
            <CommandItem
              key={model.id}
              value={`${model.name} ${model.id}`}
              onSelect={() => handleSelectModel(model.id)}
              className="cursor-pointer"
            >
              <Cpu className="size-4" />
              <span>{model.name}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        {isStreaming && (
          <>
            <CommandSeparator />
            <CommandGroup heading="操作">
              <CommandItem
                value="停止生成 stop"
                onSelect={handleStop}
                className="cursor-pointer text-destructive"
              >
                <Square className="size-4" />
                <span>停止生成</span>
                <kbd className="ml-auto text-[10px] text-muted-foreground">⌘.</kbd>
              </CommandItem>
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  )
}
