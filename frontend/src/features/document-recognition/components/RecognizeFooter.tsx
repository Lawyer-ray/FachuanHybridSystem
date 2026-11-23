import { ExternalLink, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DialogFooter } from '@/components/ui/dialog'
import { safeHttpUrl } from '@/lib/url'
import { cn } from '@/lib/utils'

import type { TaskOut } from '../types'

interface Props {
  isFileMode: boolean
  task: TaskOut | null
  /** 有原文预览时左侧就是原文，脚注不再重复给「查看文书」入口 */
  hasPreview: boolean
  /** 已换好票据的预览/下载 URL（票据一次性，调用方换好一次就共用这一份） */
  previewUrl: string
  busy: boolean
  /** 可写入的提醒条数（已勾选且待确认的行数） */
  writableCount: number
  onClose: () => void
  onConfirm: () => void
}

/**
 * 识别弹窗底栏：未绑案件的提示 + 关闭 / 写入两条动作。
 *
 * 从 RecognizeDialog 抽出：底栏只消费结果（几行可写、是否绑了案件），
 * 不参与识别流程；留在主组件里会把「弹窗怎么开、何时提交」这类决策挤到
 * JSX 下面看不见。
 */
export function RecognizeFooter({
  isFileMode,
  task,
  hasPreview,
  previewUrl,
  busy,
  writableCount,
  onClose,
  onConfirm,
}: Props) {
  return (
    <DialogFooter className="mt-3 shrink-0 gap-2 border-t border-border pt-3">
      <span className="mr-auto text-[11px] text-muted-foreground">
        {isFileMode && task && !task.binding?.success ? '未关联案件，将创建独立提醒' : ''}
      </span>
      {!hasPreview && previewUrl && (
        <a
          href={safeHttpUrl(previewUrl)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ExternalLink className="h-3 w-3" />
          查看文书
        </a>
      )}
      <Button variant="outline" onClick={onClose} disabled={busy}>
        关闭
      </Button>
      <Button onClick={onConfirm} disabled={busy || writableCount === 0} className={cn(busy && 'opacity-80')}>
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        写入 {writableCount} 条提醒
      </Button>
    </DialogFooter>
  )
}
