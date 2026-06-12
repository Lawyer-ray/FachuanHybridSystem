/**
 * 步骤节点卡片 — 画布中的单个步骤
 *
 * gate/wait 类型使用更突出的视觉样式：
 * - 更大的内边距和图标
 * - 左侧竖条强调色
 * - 显示暂停/等待提示文字
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { GripVertical, Trash2, Copy, Play, ShieldCheck, Clock, GitFork, Timer, Brain, Globe, Code } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { StepNode, StepType } from '@/features/workflow/types'

interface TypeConfig {
  color: string
  bg: string
  borderAccent: string
  icon: typeof Play
  label: string
  /** 悬浮提示文字（仅 gate/wait 有） */
  hint?: string
}

const TYPE_CONFIG: Record<StepType, TypeConfig> = {
  activity: { color: 'text-blue-600', bg: 'bg-blue-50/50 border-blue-200', borderAccent: 'border-l-blue-400', icon: Play, label: 'Activity' },
  gate: { color: 'text-amber-700', bg: 'bg-amber-50 border-amber-300', borderAccent: 'border-l-amber-500', icon: ShieldCheck, label: '审批门', hint: '⏸ 流程将暂停，等待人工审批后继续' },
  wait: { color: 'text-purple-700', bg: 'bg-purple-50 border-purple-300', borderAccent: 'border-l-purple-500', icon: Clock, label: '等待事件', hint: '⏳ 等待外部事件触发后继续' },
  condition: { color: 'text-green-600', bg: 'bg-green-50/50 border-green-200', borderAccent: 'border-l-green-400', icon: GitFork, label: '条件分支' },
  delay: { color: 'text-gray-600', bg: 'bg-gray-50/50 border-gray-200', borderAccent: 'border-l-gray-400', icon: Timer, label: '延时' },
  llm: { color: 'text-pink-600', bg: 'bg-pink-50/50 border-pink-200', borderAccent: 'border-l-pink-400', icon: Brain, label: 'LLM' },
  http: { color: 'text-cyan-600', bg: 'bg-cyan-50/50 border-cyan-200', borderAccent: 'border-l-cyan-400', icon: Globe, label: 'HTTP' },
  code: { color: 'text-orange-600', bg: 'bg-orange-50/50 border-orange-200', borderAccent: 'border-l-orange-400', icon: Code, label: '代码' },
}

interface StepNodeCardProps {
  step: StepNode
  isSelected: boolean
  onSelect: () => void
  onRemove: () => void
  onDuplicate: () => void
  stepIndex: number
  isDragging?: boolean
  dragHandleProps?: Record<string, unknown>
}

export function StepNodeCard({
  step,
  isSelected,
  onSelect,
  onRemove,
  onDuplicate,
  stepIndex,
  isDragging,
  dragHandleProps,
}: StepNodeCardProps) {
  const config = TYPE_CONFIG[step.type] || TYPE_CONFIG.activity
  const Icon = config.icon
  const isHighlight = step.type === 'gate' || step.type === 'wait'

  return (
    <div
      className={cn(
        'group relative flex items-center gap-3 rounded-lg border-2 border-l-4 transition-all cursor-pointer',
        config.bg,
        config.borderAccent,
        isHighlight ? 'p-4 shadow-sm' : 'p-3',
        isSelected ? 'ring-2 ring-primary shadow-md' : 'hover:shadow-sm',
        isDragging ? 'opacity-50 shadow-lg' : '',
      )}
      onClick={(e) => {
        e.stopPropagation()
        onSelect()
      }}
    >
      {/* 拖拽手柄 */}
      <div {...dragHandleProps} className="cursor-grab active:cursor-grabbing">
        <GripVertical className="h-4 w-4 text-muted-foreground/50" />
      </div>

      {/* 步骤序号 */}
      <div className={cn('flex items-center justify-center rounded-full text-xs font-bold shrink-0', config.color, 'bg-white border', isHighlight ? 'w-8 h-8' : 'w-7 h-7')}>
        {stepIndex + 1}
      </div>

      {/* 图标 */}
      <Icon className={cn('shrink-0', config.color, isHighlight ? 'h-6 w-6' : 'h-5 w-5')} />

      {/* 内容 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn('font-medium truncate', isHighlight ? 'text-base' : 'text-sm')}>{step.name}</span>
          <Badge variant="outline" className={cn('text-xs h-5 px-1.5 shrink-0', isHighlight && 'font-semibold')}>
            {config.label}
          </Badge>
        </div>
        {/* gate/wait 显示提示文字 */}
        {isHighlight && config.hint && (
          <p className={cn('text-xs mt-1', config.color, 'opacity-80')}>{config.hint}</p>
        )}
        {step.description && !isHighlight && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">{step.description}</p>
        )}
        {step.description && isHighlight && (
          <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>
        )}
        {step.mcp_tool && (
          <span className="text-xs font-mono text-muted-foreground/70 bg-white/50 px-1 rounded mt-0.5 inline-block">
            {step.mcp_tool}
          </span>
        )}
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={(e) => {
            e.stopPropagation()
            onDuplicate()
          }}
        >
          <Copy className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
