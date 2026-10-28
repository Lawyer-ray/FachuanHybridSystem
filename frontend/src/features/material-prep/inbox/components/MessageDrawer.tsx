import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { materialPrepDetail } from '@/app/paths'
import { SOURCE_BADGE, SOURCE_LABEL } from '../constants'
import type { InboxRow } from '../types'
import { MessageContent } from './MessageContent'

/**
 * 消息详情抽屉（右侧滑出）。
 *
 * 内容与动作全部在 `MessageContent`（首页收件箱卡的就地展开共用同一份），
 * 本组件只负责抽屉外壳：遮罩、头部来源徽章、关闭按钮。这样两处不会出现
 * 「抽屉能下载附件、首页展开不能」这类漂移。
 *
 * 为什么不直接进材料预处理：收件箱里绝大多数是**纯通知**（一张网告知书正文、
 * 判决书送达通知），没有附件可拆。对这类消息给一个能读正文的抽屉，比硬塞进
 * 材料预处理阅读器（会得到一个空包 + 「附件解析失败」的误导性提示）诚实得多。
 */
export function MessageDrawer({
  row,
  onClose,
  onConverted,
}: {
  row: InboxRow
  onClose: () => void
  /** 转成材料包后跳转（由页面决定怎么走，抽屉不自己 navigate） */
  onConverted: (packId: number) => void
}) {
  const navigate = useNavigate()

  const openPack = useCallback(
    (packId: number) => {
      void navigate(materialPrepDetail(packId))
      onClose()
    },
    [navigate, onClose],
  )

  return (
    <>
      {/* 遮罩：点击关闭（抽屉内部点击不冒泡到遮罩，因为抽屉单独叠在上层） */}
      <div className="fixed inset-0 z-[60] bg-foreground/20 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <aside
        className="fixed inset-y-0 right-0 z-[61] flex w-full max-w-[560px] flex-col border-l border-border bg-card shadow-2xl"
        role="dialog"
        aria-label="消息详情"
      >
        {/* 头部：主题 + 来源 + 关闭 */}
        <header className="flex items-start gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex-none rounded-[4px] border px-1.5 py-px text-[10px] font-medium',
                  SOURCE_BADGE[row.source_type] ?? 'border-border bg-secondary text-secondary-foreground',
                )}
              >
                {SOURCE_LABEL[row.source_type] ?? row.source_name}
              </span>
              {row.has_attachments && (
                <span className="text-[11px] text-muted-foreground">{row.attachment_count} 个附件</span>
              )}
            </div>
            <h2 className="mt-1.5 text-[14px] font-semibold leading-snug break-words">{row.subject || '(无主题)'}</h2>
            <p className="mt-1 text-[11.5px] text-muted-foreground break-all">
              {row.sender || row.source_name}
              {row.recipient ? ` · ${row.recipient}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 flex-none items-center justify-center rounded-[7px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* 主体：正文 + 附件 + 动作（与首页就地展开共用 MessageContent） */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <MessageContent row={row} onConverted={onConverted} onOpenPack={openPack} />
        </div>
      </aside>
    </>
  )
}
