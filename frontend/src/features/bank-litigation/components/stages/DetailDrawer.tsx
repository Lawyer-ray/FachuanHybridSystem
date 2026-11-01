/**
 * 行内详情弹窗 —— 表格里每一行都能点开看细节
 *
 * ═══ 为什么要它 ═══
 * 之前表格是「死」的：一行材料、一条缺件、一份文书，只能看那一行文字。
 * 真实的系统里，**任何一行都点得开** —— 律师看见「差额补足承诺函 61%」，
 * 第一反应就是「点开看看它到底识别成什么样了」。
 *
 * 所以这里提供统一的 Drawer：右侧滑入、带遮罩、ESC 关闭、点遮罩关闭。
 * 内容由调用方给（ReactNode），不只是文本 —— 可以放 markdown 预览、
 * 图片、表单、操作按钮。
 */

import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

export function DetailDrawer({
  open,
  onClose,
  title,
  subtitle,
  badge,
  children,
  footer,
  width = 520,
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  /** 标题右侧的状态标签 */
  badge?: ReactNode
  children: ReactNode
  /** 底部动作区 */
  footer?: ReactNode
  width?: number
}) {
  // ESC 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[80]">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-foreground/20 backdrop-blur-[1px]" onClick={onClose} aria-hidden />

      {/* 抽屉 */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'absolute inset-y-0 right-0 flex flex-col border-l border-border bg-card shadow-[-8px_0_32px_-12px_rgba(0,0,0,.18)]',
          'animate-[drawer-in_.2s_cubic-bezier(.16,1,.3,1)]',
        )}
        style={{ width }}
      >
        {/* 头 */}
        <header className="flex flex-none items-start gap-2 border-b border-border px-5 py-3.5">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="min-w-0 truncate text-[14px] font-[620]" title={title}>
                {title}
              </h2>
              {badge}
            </div>
            {subtitle ? <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="grid size-6 flex-none place-items-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </header>

        {/* 内容 */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3.5">{children}</div>

        {/* 底部动作 */}
        {footer ? <footer className="flex flex-none items-center gap-2 border-t border-border px-5 py-3">{footer}</footer> : null}
      </aside>
    </div>
  )
}
