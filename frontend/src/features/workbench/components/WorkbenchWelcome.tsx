/** 工作台空状态欢迎页面 */

import { Bot, Plus, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface WorkbenchWelcomeProps {
  onCreateSession: () => void
  isCreating: boolean
}

export function WorkbenchWelcome({ onCreateSession, isCreating }: WorkbenchWelcomeProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto">
      <div className="w-full max-w-2xl px-4 space-y-6">
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
      </div>
    </div>
  )
}
