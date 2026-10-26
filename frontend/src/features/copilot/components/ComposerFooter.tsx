/**
 * 输入区底部的状态行：免责声明 / 后台任务提示 / 压缩进度 / 上下文水位 / 轮次统计。
 *
 * 从 Composer 拆出（后者超软红线）：本行自取 store（compacting/contextUsage），
 * 对外只需要 bgMode 一个 prop 决定提示文案，边界干净。
 */

import { useCopilot } from '../store'
import { TurnStatsView } from './TurnStatsView'

export function ComposerFooter({ bgMode }: { bgMode: boolean }) {
  const compacting = useCopilot((s) => s.compacting)
  const contextUsage = useCopilot((s) => s.contextUsage)
  return (
    <p className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
      <span className="min-w-0 flex-1 truncate">
        {compacting
          ? '正在压缩上下文…'
          : bgMode
            ? '后台任务跑完会写入会话通知；高危操作会等你回来审批。'
            : 'AI 回答仅供参考，法律判断需由律师复核。'}
      </span>
      {contextUsage.used !== null && contextUsage.total && contextUsage.total > 0 && !compacting && (
        <span
          className={`flex-none tabular-nums ${contextUsage.used / contextUsage.total >= 0.8 ? 'text-amber-600 dark:text-amber-400' : ''}`}
          title={`上下文窗口占用：${contextUsage.used} / ${contextUsage.total} tokens；用 / 压缩命令可手动释放`}
        >
          上下文 {Math.round((contextUsage.used / contextUsage.total) * 100)}%
        </span>
      )}
      <TurnStatsView />
    </p>
  )
}
