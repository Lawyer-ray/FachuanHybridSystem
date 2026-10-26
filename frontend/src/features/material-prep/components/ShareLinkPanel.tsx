/**
 * 客户上传链接管理面板：列表（状态/已收统计/有效期）+ 新建 + 作废 + 换发。
 * 换发与创建一样只显示一次新明文（旧链接立即失效）。
 */

import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Link2, Loader2, Plus, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { listUploadLinks, revokeUploadLink, rotateUploadLink, type UploadLinkRow } from '../api'
import { ShareLinkDialog, ShareUrlBox } from './ShareLinkDialog'

const STATE_LABEL: Record<string, string> = {
  open: '可收',
  expired: '已过期',
  revoked: '已作废',
  full: '已收满',
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  return `${Math.max(1, Math.round(bytes / 1024))}KB`
}

function formatExpiry(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

export function ShareLinkPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [rows, setRows] = useState<UploadLinkRow[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  /** 换发后的新链接 URL（只显示一次） */
  const [rotatedUrl, setRotatedUrl] = useState<string | null>(null)
  /** 待作废确认的链接（简单二次确认，不另开弹窗） */
  const [confirmingId, setConfirmingId] = useState<number | null>(null)

  const reload = useCallback(() => {
    setLoading(true)
    listUploadLinks()
      .then(setRows)
      .catch(() => toast.error('链接列表加载失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (open) {
      setRotatedUrl(null)
      setConfirmingId(null)
      reload()
    }
  }, [open, reload])

  const revoke = (id: number) => {
    revokeUploadLink(id)
      .then(() => {
        toast('已作废，客户手里的旧链接立即失效')
        reload()
      })
      .catch(() => toast.error('作废失败，请重试'))
  }

  const rotate = (id: number) => {
    rotateUploadLink(id)
      .then((created) => {
        setRotatedUrl(`${window.location.origin}/u/${created.token}`)
        reload()
      })
      .catch((e: unknown) => toast.error(e instanceof Error ? e.message : '换发失败'))
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link2 className="h-4 w-4" /> 客户上传链接
            </DialogTitle>
            <DialogDescription>一次性链接一对一发给客户；客户上传的材料包会出现在本桌面（来源：客户链接上传）。</DialogDescription>
          </DialogHeader>

          <div className="max-h-[60vh] space-y-2 overflow-auto py-1">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-sm text-secondary-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
              </div>
            ) : rows.length === 0 ? (
              <p className="py-10 text-center text-sm text-secondary-foreground">还没有生成过链接</p>
            ) : (
              rows.map((row) => {
                const isOpen = row.state === 'open'
                return (
                  <div key={row.id} className="rounded-lg border px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{row.title}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          isOpen ? 'bg-emerald-500/10 text-emerald-700' : 'bg-secondary text-secondary-foreground'
                        }`}
                      >
                        {STATE_LABEL[row.state] ?? row.state}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {[row.client_name, row.contract_name, `已收 ${row.pack_count} 包 / ${formatBytes(row.used_bytes)}`, `${formatExpiry(row.expires_at)} 到期`]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      {isOpen && (
                        <Button variant="outline" size="sm" onClick={() => rotate(row.id)}>
                          <RefreshCw className="h-3.5 w-3.5" /> 换发新链接
                        </Button>
                      )}
                      {isOpen &&
                        (confirmingId === row.id ? (
                          <>
                            <Button variant="destructive" size="sm" onClick={() => { setConfirmingId(null); revoke(row.id) }}>
                              确认作废
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setConfirmingId(null)}>
                              取消
                            </Button>
                          </>
                        ) : (
                          <Button variant="ghost" size="sm" onClick={() => setConfirmingId(row.id)}>
                            作废
                          </Button>
                        ))}
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {rotatedUrl && (
            <div className="space-y-1.5 rounded-lg border border-amber-300/60 bg-amber-500/5 px-3 py-2.5">
              <p className="text-xs text-amber-700">旧链接已失效，新链接只显示这一次：</p>
              <ShareUrlBox url={rotatedUrl} />
            </div>
          )}

          <div className="flex justify-end">
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> 新建链接
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ShareLinkDialog open={creating} onOpenChange={setCreating} onCreated={reload} />
    </>
  )
}
