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
 *
 * ═══ 层级：为什么是 z-[110] ═══
 * 本组件是模态的，必须盖住 copilot 常驻 dock（z-[100]，S7 审计 P20-102 记的
 * 就是「dock 一展开就把抽屉压在下面」）；但不能越到菜单类 portal（z-[120]）
 * 与弹窗基线（z-[130]）之上 —— 抽屉里点「确定」会弹 Dialog / AlertDialog，
 * 行内也可能开下拉，压过去就点不到。
 *
 * 当前 z 阶梯快照（`grep -rn 'z-\[[0-9]*\]' src` 全量整理，2026-11-23）：
 *    60  阅读器底部浮条（SelectionBar / AutoSplitProgress）、消息抽屉遮罩
 *    61  消息抽屉面板
 *    80  全屏阅读器 .mp-reader
 *    90  copilot 遮罩、签章抽屉、阅读器右键菜单
 *    96  发起审查抽屉遮罩 / 97 面板
 *   100  copilot 常驻 dock
 *   110  阅读器 OCR 浮层 ← 本组件取这一档
 *   119  右键菜单的透明遮罩 / 120 菜单类下拉与浮层（Radix portal）
 *   130  弹窗基线：Dialog / AlertDialog / Sheet / 首页日程详情
 * 999999999  toast（sonner 自带）
 *
 * 取 110 而不是新造一个数：它是阶梯里现成的、唯一落在「高于 dock、低于菜单/
 * 弹窗」这一段的值。同档的 OcrPanel 挂在 .mp-reader（z-[80]）自己的层叠上下文里，
 * 只跟阅读器内部比高低，与兜在页面层的抽屉不冲突。改前是 z-[80]，与全屏阅读器
 * 平档，dock 打开时被 z-[100] 盖住（P20-102）。
 */

import type { ReactNode } from 'react'
import { X } from 'lucide-react'

import { useFocusTrap } from '@/hooks/use-focus-trap'
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
  // 模态行为（ESC / Tab 圈定 / 关闭后焦点归还）全在这里，本文件不再自绘 ESC
  // 监听：两处都监听会让一次 ESC 触发两次 onClose。hook 必须在 `return null` 之前
  // 调用（hook 顺序），它会自己处理 open=false 的 inactive 状态。
  const { panelRef } = useFocusTrap(open, onClose)

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[110] h-screen w-screen overflow-hidden">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-foreground/20 backdrop-blur-[1px]" onClick={onClose} aria-hidden />

      {/* 抽屉 */}
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'absolute top-0 right-0 bottom-0 flex h-full max-h-screen flex-col border-l border-border bg-card shadow-[-8px_0_32px_-12px_rgba(0,0,0,.18)]',
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
