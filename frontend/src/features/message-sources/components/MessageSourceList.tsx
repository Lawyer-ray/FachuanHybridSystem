import { useState } from 'react'
import { Plus, RefreshCw, Trash2, Power, PowerOff } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { useMessageSources } from '../hooks/use-message-sources'
import { messageSourceApi } from '../api'
import {
  SOURCE_TYPE_LABELS, SYNC_STATUS_LABELS,
  type SourceType, type SyncStatus,
} from '../types'

export function MessageSourceList() {
  const { data: sources, isLoading } = useMessageSources()
  const queryClient = useQueryClient()
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set())

  const sourceList = sources ?? []

  const handleSync = async (id: number) => {
    setSyncingIds((prev) => new Set(prev).add(id))
    try {
      await messageSourceApi.sync(id)
    } catch (e) {
      console.error('Sync failed:', e)
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleSyncAll = async () => {
    try {
      await messageSourceApi.syncAll()
    } catch (e) {
      console.error('Sync all failed:', e)
    }
  }

  const handleToggleEnabled = async (id: number, currentEnabled: boolean) => {
    try {
      await messageSourceApi.update(id, { is_enabled: !currentEnabled })
      queryClient.invalidateQueries({ queryKey: ['message-sources'] })
    } catch (e) {
      console.error('Toggle failed:', e)
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除此消息来源？')) return
    try {
      await messageSourceApi.delete(id)
      queryClient.invalidateQueries({ queryKey: ['message-sources'] })
    } catch (e) {
      console.error('Delete failed:', e)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">消息来源</h1>
          <p className="text-muted-foreground text-sm mt-1">管理 IMAP 邮箱和一张网收件箱的消息同步配置</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleSyncAll}>
            <RefreshCw className="mr-1.5 size-4" />全部同步
          </Button>
          <Button size="sm">
            <Plus className="mr-1.5 size-4" />添加来源
          </Button>
        </div>
      </div>

      {/* Table */}
      {sourceList.length === 0 && !isLoading ? (
        <EmptyState
          icon="inbox"
          title="暂无消息来源"
          description="还没有配置消息来源，添加 IMAP 邮箱或一张网收件箱来开始同步消息"
          actionText="添加来源"
        />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]">ID</TableHead>
                <TableHead>显示名称</TableHead>
                <TableHead className="w-[120px]">来源类型</TableHead>
                <TableHead className="w-[150px]">账号</TableHead>
                <TableHead className="w-[60px]">启用</TableHead>
                <TableHead className="w-[90px]">轮询间隔</TableHead>
                <TableHead className="w-[130px]">最后同步</TableHead>
                <TableHead className="w-[100px]">同步状态</TableHead>
                <TableHead className="w-[150px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 9 }).map((_, j) => (
                      <TableCell key={j}><div className="bg-muted h-4 w-20 animate-pulse rounded" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : sourceList.map((s) => {
                const typeKey = s.source_type as SourceType
                const syncKey = s.last_sync_status as SyncStatus
                const isSyncing = syncingIds.has(s.id)

                return (
                  <TableRow key={s.id}>
                    <TableCell className="text-muted-foreground text-sm">{s.id}</TableCell>
                    <TableCell className="font-medium text-sm">{s.display_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{SOURCE_TYPE_LABELS[typeKey] ?? s.source_type}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm truncate max-w-[150px]" title={s.credential_account}>
                      {s.credential_account}
                    </TableCell>
                    <TableCell>
                      <button
                        className="p-0.5 rounded hover:bg-muted transition-colors"
                        onClick={() => handleToggleEnabled(s.id, s.is_enabled)}
                        title={s.is_enabled ? '点击禁用' : '点击启用'}
                      >
                        {s.is_enabled
                          ? <Power className="size-4 text-status-green" />
                          : <PowerOff className="size-4 text-muted-foreground" />}
                      </button>
                    </TableCell>
                    <TableCell className="text-sm">{s.poll_interval_minutes} 分钟</TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {s.last_sync_at ? new Date(s.last_sync_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={syncKey === 'success' ? 'default' : syncKey === 'failed' ? 'destructive' : 'secondary'}
                        className="text-xs"
                      >
                        {SYNC_STATUS_LABELS[syncKey] ?? s.last_sync_status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => handleSync(s.id)}
                          disabled={isSyncing}
                        >
                          <RefreshCw className={`size-3 mr-0.5 ${isSyncing ? 'animate-spin' : ''}`} />
                          {isSyncing ? '同步中' : '同步'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs text-status-red border-status-red hover:bg-status-red-bg"
                          onClick={() => handleDelete(s.id)}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

export default MessageSourceList
