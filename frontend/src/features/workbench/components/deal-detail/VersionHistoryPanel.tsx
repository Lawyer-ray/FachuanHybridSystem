import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { errMessage } from '@/lib/errors'
import { formatBytes } from '@/lib/format'

import type { FolderOwnerKind } from '../../api'
import {
  SNAPSHOT_REASON_LABEL,
  listSnapshots,
  restoreSnapshot,
  type SnapshotItem,
} from './doc-review-api'

/**
 * 版本历史：每次覆盖之前系统都留了一版，这里只负责「看」和「回去」。
 *
 * ## 为什么回滚也要二次确认
 *
 * 回滚本身**也是可回滚的**（回滚前会先把当前内容再存一版，返回 `previous_seq`），
 * 但它仍然是「把文件换成另一份内容」——律师可能边看边改，误点一次就要再找回来。
 * 所以确认弹窗里明说「当前内容也会留一版，可以再滚回来」：既降低焦虑，也降低
 * 误点的代价。
 *
 * ## 为什么列表不显示内容预览
 *
 * 快照是整份 docx，拉下来预览要几十到几百 KB，而律师在这一屏要的只是
 * 「什么时候、因为什么、被谁」三件事。真要对比，走「打开该版本」下载后自己看。
 */

export function VersionHistoryPanel({
  kind,
  ownerId,
  subpath,
  onRestored,
}: {
  kind: FolderOwnerKind
  ownerId: number
  subpath: string
  onRestored?: () => void
}) {
  const qc = useQueryClient()
  const [target, setTarget] = useState<SnapshotItem | null>(null)
  const key = ['doc-snapshots', kind, ownerId, subpath] as const

  const snapshots = useQuery({ queryKey: key, queryFn: () => listSnapshots(kind, ownerId, subpath) })

  const restore = useMutation({
    mutationFn: (seq: number) => restoreSnapshot(kind, ownerId, subpath, seq),
    onSuccess: (result) => {
      setTarget(null)
      if (!result.restored) {
        toast.error(result.reason || '回滚失败')
        return
      }
      toast.success('已回滚到该版本', {
        description: `回滚前的内容存为第 ${result.previous_seq} 版，需要的话可以再滚回来`,
      })
      void qc.invalidateQueries({ queryKey: key })
      onRestored?.()
    },
    onError: (error) => {
      setTarget(null)
      toast.error(errMessage(error, '回滚失败，请稍后重试'))
    },
  })

  const items = snapshots.data?.items ?? []

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex flex-none items-center gap-2 border-b border-border px-3 py-2">
        <History className="size-3.5 text-muted-foreground" />
        <p className="text-[12.5px] font-[650]">版本历史</p>
        <span className="text-[10.5px] text-muted-foreground">{items.length} 版</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {snapshots.isLoading && (
          <p className="px-1 py-6 text-center text-[11.5px] text-muted-foreground">正在读取…</p>
        )}
        {!snapshots.isLoading && items.length === 0 && (
          <p className="px-2 py-8 text-center text-[11.5px] text-muted-foreground">
            还没有历史版本。每次保存或 AI 落笔之前，系统都会自动留一版。
          </p>
        )}

        {items.map((snap, index) => (
          <div
            key={snap.seq}
            className="mb-1.5 rounded-[8px] border border-border bg-background px-2 py-1.5"
          >
            <div className="flex items-center gap-1.5">
              <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                v{snap.seq}
              </span>
              <span className="text-[11.5px] font-[600]">
                {SNAPSHOT_REASON_LABEL[snap.reason] ?? snap.reason}
              </span>
              {index === 0 && (
                <span className="rounded-[5px] bg-status-green/10 px-1.5 py-0.5 text-[10px] text-status-green">
                  上一版
                </span>
              )}
              <div className="flex-1" />
              <button
                type="button"
                onClick={() => setTarget(snap)}
                className="inline-flex items-center gap-0.5 text-[10.5px] text-muted-foreground hover:text-foreground"
              >
                <RotateCcw className="size-2.5" /> 回到这一版
              </button>
            </div>
            <p className="mt-0.5 text-[10.5px] text-muted-foreground">
              {new Date(snap.created_at).toLocaleString('zh-CN')} · {formatBytes(snap.size)} ·
              {snap.actor_kind === 'ai' ? ' AI' : snap.actor_kind === 'human' ? ' 人工' : ' 未记录'}
            </p>
          </div>
        ))}
      </div>

      <AlertDialog open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>把文件回滚到 v{target?.seq}？</AlertDialogTitle>
            <AlertDialogDescription>
              当前内容会先自动存成新的一版，所以这次回滚**可以再滚回来**。
              但在你操作期间别人对这份文件的改动会被覆盖。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (target) restore.mutate(target.seq)
              }}
            >
              {restore.isPending ? <Loader2 className="size-3 animate-spin" /> : null}
              确认回滚
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
