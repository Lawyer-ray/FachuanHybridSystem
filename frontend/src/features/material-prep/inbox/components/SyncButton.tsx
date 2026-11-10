import { ChevronDown, Loader2, RefreshCw } from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { SYNC_WINDOW_OPTIONS } from '../api'
import type { SyncWindowDays } from '../api'
import { INBOX_SYNC_SPEC } from '../constants'
import type { SyncResult } from '../hooks/use-sync-sources'
import type { InboxSourceFilter } from '../types'

/**
 * 收件箱同步按钮 —— 贴在来源筛选条最右端，作用于**当前选中的档位**。
 *
 * ## 为什么带一个时间范围下拉
 *
 * 手动同步的预期是「点一下就看到最近的新消息」。此前无论点多少次，后端都按来源
 * 的 `sync_since` 走（实测某邮箱半年 290 封全拉，其中只有 2 封是关心的到账通知），
 * 又慢又污染收件箱。现在：
 *
 * - **主按钮**：按默认窗口（7 天）同步，一键完成，覆盖绝大多数场景；
 * - **下拉**：需要时放宽到 30/90 天。
 *
 * 后台定时任务不受此限制（首次建源仍会按 sync_since 完整回填）。
 *
 * ## 文案随档位变
 *
 * 「同步一张网」/「同步邮箱」而非固定「同步」：用户点它之前必须能一眼看出同步
 * 范围，否则「选着邮箱却点了同步全部」这类歧义会变成投诉。
 * 按钮固定 min-width 消化各档位文案的宽度差，避免筛选条抖动。
 */
export function SyncButton({ source, sync }: { source: InboxSourceFilter; sync: SyncResult }) {
  const spec = INBOX_SYNC_SPEC[source]
  const syncing = sync.state === 'syncing'

  if (!sync.enabled) {
    return (
      <button
        type="button"
        disabled
        title={sync.disabledReason}
        className="flex h-[28px] min-w-[104px] cursor-not-allowed items-center justify-center gap-1.5 rounded-[7px] border border-dashed border-border bg-secondary/40 px-2.5 text-[12px] font-medium text-muted-foreground"
      >
        <RefreshCw className="h-3.5 w-3.5 flex-none opacity-40" aria-hidden />
        {sync.disabledReason ?? '无需同步'}
      </button>
    )
  }

  return (
    <div className="flex flex-none items-stretch">
      <button
        type="button"
        onClick={() => sync.run()}
        disabled={syncing}
        title={`同步最近 ${sync.lastWindowDays} 天的消息`}
        className={cn(
          'flex h-[28px] min-w-[104px] items-center justify-center gap-1.5 rounded-l-[7px] border border-r-0 px-2.5 text-[12px] font-medium transition-colors',
          syncing
            ? 'cursor-wait border-border bg-secondary/40 text-muted-foreground'
            : 'border-input bg-background text-secondary-foreground hover:bg-secondary hover:text-foreground',
        )}
      >
        {syncing ? (
          <Loader2 className="h-3.5 w-3.5 flex-none animate-spin" aria-hidden />
        ) : (
          <RefreshCw className="h-3.5 w-3.5 flex-none" aria-hidden />
        )}
        {syncing ? '同步中…' : `同步${spec.label}`}
      </button>

      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={syncing}
          aria-label="选择同步时间范围"
          className={cn(
            'flex h-[28px] w-[26px] items-center justify-center rounded-r-[7px] border transition-colors',
            syncing
              ? 'cursor-not-allowed border-border bg-secondary/40 text-muted-foreground'
              : 'border-input bg-background text-secondary-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          <ChevronDown className="h-3.5 w-3.5" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[150px]">
          {SYNC_WINDOW_OPTIONS.map((days: SyncWindowDays) => (
            <DropdownMenuItem
              key={days}
              onClick={() => sync.run(days)}
              className="text-[12.5px]"
            >
              最近 {days} 天
              {days === sync.lastWindowDays && (
                <span className="ml-auto text-[10.5px] text-muted-foreground">上次</span>
              )}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
