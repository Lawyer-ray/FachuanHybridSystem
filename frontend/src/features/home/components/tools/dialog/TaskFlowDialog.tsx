import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Clock, Loader2, UserSearch, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Dialog, DialogContent } from '@/components/ui/dialog'

/**
 * 快捷工具任务弹窗的基调：running 处理中 / success 成功 / error 失败 /
 * manual 需人工介入（如短信匹配不到案件）/ timeout 等待超时（后台仍在跑）。
 */
export type FlowTone = 'running' | 'success' | 'error' | 'manual' | 'timeout'

const TONE_ICON: Record<FlowTone, ReactNode> = {
  running: null,
  success: <CheckCircle2 className="h-6 w-6" />,
  error: <XCircle className="h-6 w-6" />,
  manual: <UserSearch className="h-6 w-6" />,
  timeout: <Clock className="h-6 w-6" />,
}

const TONE_TILE: Record<FlowTone, string> = {
  running: 'border-status-blue/30 bg-status-blue-bg text-status-blue',
  success: 'border-status-green/30 bg-status-green-bg text-status-green',
  error: 'border-status-red/30 bg-status-red-bg text-status-red',
  manual: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
  timeout: 'border-border bg-secondary text-muted-foreground',
}

/** 处理中的图标瓦片：工具图标 + 双层 ping 光环 + 角标转圈 */
function RunningTile({ icon }: { icon: ReactNode }) {
  return (
    <div className="relative flex h-12 w-12 flex-none items-center justify-center">
      <span className="absolute inset-0 animate-ping rounded-[14px] border border-status-blue/25 [animation-delay:0ms]" />
      <span className="absolute inset-0 animate-ping rounded-[14px] border border-status-blue/15 [animation-delay:700ms]" />
      <div
        className={cn(
          'relative flex h-12 w-12 items-center justify-center rounded-[14px] border',
          TONE_TILE.running,
        )}
      >
        {icon}
        <span className="absolute -right-1.5 -bottom-1.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border border-border bg-card text-status-blue">
          <Loader2 className="h-3 w-3 animate-spin" />
        </span>
      </div>
    </div>
  )
}

/** 终态图标瓦片：带缩放入场动画 */
function DoneTile({ tone }: { tone: FlowTone }) {
  return (
    <div
      className={cn(
        'animate-in zoom-in-50 fade-in duration-300 flex h-12 w-12 flex-none items-center justify-center rounded-[14px] border',
        TONE_TILE[tone],
      )}
    >
      {TONE_ICON[tone]}
    </div>
  )
}

/**
 * 快捷工具统一任务弹窗外壳：四张工具卡（法院短信 / 要素式转换 / DOC转DOCX / 文档解析）
 * 共用的「提交后进度弹窗」。壳只负责 头部基调 + 内容区 + 底部操作，
 * 各工具的阶段动画 / 结果内容 / 操作按钮由 children 与 footer 传入。
 */
export function TaskFlowDialog({
  open,
  onOpenChange,
  icon,
  title,
  tone,
  headline,
  subline,
  children,
  footer,
  wide,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 工具图标（running 态展示在光环瓦片里；终态换状态图标） */
  icon: ReactNode
  title: string
  tone: FlowTone
  /** 基调主文案，如「正在处理…」「处理完成」 */
  headline: string
  /** 次要说明（进度数字 / 错误摘要），可省 */
  subline?: string
  children?: ReactNode
  /** 底部操作区（按钮等） */
  footer?: ReactNode
  /** 内容较宽（文书列表 / 解析预览）时用 560px */
  wide?: boolean
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={tone === 'running' ? false : undefined}
        className={cn('top-[46%] gap-0 p-5', wide ? 'sm:max-w-[560px]' : 'sm:max-w-[440px]')}
      >
        <div className="flex items-center gap-3.5 pr-6">
          {tone === 'running' ? <RunningTile icon={icon} /> : <DoneTile tone={tone} />}
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-muted-foreground">{title}</div>
            <div className="mt-0.5 truncate text-[15.5px] leading-tight font-bold" title={headline}>
              {headline}
            </div>
            {subline && (
              <div className="mt-1 line-clamp-2 text-[11.5px] leading-snug text-muted-foreground">{subline}</div>
            )}
          </div>
        </div>

        {children && <div className="mt-4 min-h-0">{children}</div>}

        {footer && (
          <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3.5">
            {footer}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** 弹窗内容里的小警示块（错误原因 / 注意事项） */
export function FlowNotice({ kind, children }: { kind: 'error' | 'warn' | 'info'; children: ReactNode }) {
  const styles = {
    error: 'border-status-red/30 bg-status-red-bg text-status-red',
    warn: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
    info: 'border-status-blue/30 bg-status-blue-bg text-status-blue',
  } as const
  const Icon = kind === 'error' ? AlertTriangle : kind === 'warn' ? Clock : CheckCircle2
  return (
    <div className={cn('flex items-start gap-2 rounded-[10px] border px-3 py-2.5 text-[12px] leading-relaxed', styles[kind])}>
      <Icon className="mt-0.5 h-3.5 w-3.5 flex-none" />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  )
}
