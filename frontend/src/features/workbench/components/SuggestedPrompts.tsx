/** 空状态建议提示卡片 */

import { Briefcase, FileText, Search, Globe, Bell, Building2, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '../stores/workbench-store'
import { SUGGESTED_PROMPTS, type AgentType } from '../types'

const ICON_MAP: Record<string, LucideIcon> = {
  Briefcase,
  FileText,
  Search,
  Globe,
  Bell,
  Building2,
}

export function SuggestedPrompts() {
  const setSelectedAgent = useWorkbenchStore((s) => s.setSelectedAgent)
  const setPendingPrompt = useWorkbenchStore((s) => s.setPendingPrompt)

  const handleClick = (prompt: string, agent?: AgentType) => {
    if (agent) setSelectedAgent(agent)
    setPendingPrompt(prompt)
  }

  return (
    <div className="px-4 pb-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {SUGGESTED_PROMPTS.map((item) => {
          const Icon = ICON_MAP[item.icon] || Search
          return (
            <button
              key={item.label}
              onClick={() => handleClick(item.prompt, item.agent)}
              className={cn(
                'flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 px-3 py-2.5 text-left text-xs',
                'hover:bg-accent hover:border-border transition-colors',
              )}
            >
              <Icon className="size-4 shrink-0 text-muted-foreground" />
              <span className="font-medium">{item.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
