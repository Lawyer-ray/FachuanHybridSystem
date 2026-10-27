import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * 阅读器的外壳与加载/错误态（从 Reader.tsx 拆出的纯展示分支）。
 * Reader 顶层编排保持单一职责后，这两个 early-return 分支随固定容器一起下沉。
 *
 * 右缘吃 `--copilot-docked-w`（AppShell 并排 AI 助手时写入）：阅读器是
 * fixed inset 全屏层，不跟页面 padding 走，只能自己把右缘收进来，阅读时
 * 才能和助手同屏。同时它是内部布局的 @container：窄屏形态、侧栏宽度等
 * 断点全按阅读器自身净宽算（视口量不到让位掉的宽度）。
 */
export function FixedReader({
  children,
  closing = false,
  rootRef,
}: {
  children: React.ReactNode
  closing?: boolean
  /** 挂到根容器的 ref（Reader 用它实测阅读器净宽驱动窄屏形态） */
  rootRef?: (node: HTMLDivElement | null) => void
}) {
  return (
    <div
      ref={rootRef}
      className={cn(
        'mp-reader @container fixed bottom-0 left-0 top-0 z-[80] flex flex-col bg-[#f1f1f3] transition-[right] duration-200 right-[var(--copilot-docked-w,0px)]',
        closing && 'closing',
      )}
      // 鼠标点按钮不夺焦：否则焦点停在按钮上，随后按空格/回车会重新触发该按钮，导致界面跳动（“闪烁”）
      onMouseDown={(e) => {
        const t = e.target as HTMLElement
        if (t && t.closest && t.closest('button')) e.preventDefault()
      }}
    >
      {children}
    </div>
  )
}

/** 打开中：解析页数（detail 已到、draft 未就绪） */
export function ReaderLoading() {
  return (
    <FixedReader>
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-secondary-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 正在打开材料包，解析页数…
      </div>
    </FixedReader>
  )
}

/** 打开失败：错误文案 + 返回（关闭阅读器） */
export function ReaderError({ error, onBack }: { error: string; onBack: () => void }) {
  return (
    <FixedReader>
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm">
        <p className="text-destructive">{error}</p>
        <Button onClick={onBack}>返回</Button>
      </div>
    </FixedReader>
  )
}
