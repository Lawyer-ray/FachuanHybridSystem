import { Loader2, RefreshCw } from 'lucide-react'

import { cn } from '@/lib/utils'
import { INBOX_SYNC_SPEC } from '../constants'
import type { SyncResult } from '../hooks/use-sync-sources'
import type { InboxSourceFilter } from '../types'

/**
 * 收件箱同步按钮 —— 贴在来源筛选条最右端，作用于**当前选中的档位**。
 *
 * 文案随档位变（「同步一张网」/「同步邮箱」）而不是固定写「同步」：用户点它之前
 * 必须能一眼看出同步范围，否则「选着邮箱却点了同步全部」这类歧义会变成投诉。
 * 给按钮固定 min-width 消化各档位文案的宽度差，避免筛选条抖动。
 *
 * 三态：idle（可点）/ syncing（转圈禁用）/ 置灰（材料包，无「拉新」概念）。
 * 同步完成后的「新增 N 条」提示由上层观察 `sync.newCount` 决定，本组件只管按钮本身。
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
    <button
      type="button"
      onClick={sync.run}
      disabled={syncing}
      className={cn(
        'flex h-[28px] min-w-[104px] items-center justify-center gap-1.5 rounded-[7px] border px-2.5 text-[12px] font-medium transition-colors',
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
  )
}
