/** 工作台空状态欢迎页面 */

import { Bot, Plus, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SuggestedPrompts } from './SuggestedPrompts'

interface WorkbenchWelcomeProps {
  onCreateSession: () => void
  isCreating: boolean
  onSelectPrompt: (prompt: string) => void
}

export function WorkbenchWelcome({ onCreateSession, isCreating, onSelectPrompt }: WorkbenchWelcomeProps) {
  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-2xl px-4 py-8 space-y-6">
        {/* 欢迎标题 */}
        <div className="text-center space-y-2">
          <Bot className="mx-auto size-10 text-primary/60" />
          <h2 className="text-lg font-semibold">欢迎使用法穿工作台</h2>
          <p className="text-sm text-muted-foreground">AI 驱动的法律事务助手，帮你高效处理案件、合同和法律检索</p>
          <Button onClick={onCreateSession} disabled={isCreating} className="mt-2">
            {isCreating ? (
              <Loader2 className="size-4 animate-spin mr-2" />
            ) : (
              <Plus className="size-4 mr-2" />
            )}
            新建会话
          </Button>
        </div>

        {/* 快速开始 */}
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-muted-foreground">快速开始</h3>
          <SuggestedPrompts onSelect={onSelectPrompt} />
        </div>
      </div>
    </div>
  )
}
