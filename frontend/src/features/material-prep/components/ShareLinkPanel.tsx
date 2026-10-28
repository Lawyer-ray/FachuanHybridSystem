/**
 * 客户上传链接管理面板：列表（状态/已收统计/有效期）+ 新建 + 换发 + 作废。
 *
 * **关于「能不能复制旧链接」**：不能，而且是设计使然。库里只存 token 的
 * SHA-256（`ClientUploadLink.token_hash`），明文只在创建/换发那次响应里出现一次 ——
 * 这样即使库被拖走也无法反推出可用链接。所以面板里旧链接没有「复制」按钮，
 * 只有刚生成/刚换发的那一条能复制。想再拿到链接的唯一办法是「换发」
 * （旧链接立即失效）。
 *
 * 换发是**破坏性操作**（客户手里的旧链接当场失效），因此：
 *   1. 先在该行内二次确认，不直接执行；
 *   2. 结果就地显示在**那一行内部**并标明标题，多行时也不会搞混新链接属于谁。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Info, Link2, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { formatBytes } from '@/lib/format'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { buildShareUrl, deleteUploadLink, listUploadLinks, revokeUploadLink, rotateUploadLink, type UploadLinkRow } from '../api'
import { ShareLinkDialog, ShareUrlBox } from './ShareLinkDialog'

const STATE_LABEL: Record<string, string> = {
  open: '可收',
  expired: '已过期',
  revoked: '已作废',
  full: '已收满',
}

function formatExpiry(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

/** 一次性明文提示条：刚生成/刚换发的链接都走它，风格统一 */
function OneTimeUrlNotice({ url, hint }: { url: string; hint: string }) {
  return (
    <div className="mt-2 space-y-1.5 rounded-lg border border-amber-300/60 bg-amber-500/5 px-3 py-2.5">
      <p className="text-xs font-medium text-amber-700">{hint}</p>
      <ShareUrlBox url={url} />
      <p className="text-[11px] text-muted-foreground">关掉这个面板后就看不到了，如需再发请用「换发」。</p>
    </div>
  )
}

export function ShareLinkPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [rows, setRows] = useState<UploadLinkRow[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  /** 新建成功后得到的链接（只显示一次）。子弹窗关闭后仍要留在面板里，故由父层持有 */
  const [created, setCreated] = useState<{ title: string; url: string } | null>(null)
  /** 从「新建」弹窗返回，不能清 created，否则刚生成的链接会一闪而过 */
  const returningFromCreate = useRef(false)
  /** 换发结果带上行 id：多行时必须能看出新链接属于哪一条 */
  const [rotated, setRotated] = useState<{ id: number; title: string; url: string } | null>(null)
  /** 待确认换发的行（破坏性操作，先确认再执行） */
  const [rotatingId, setRotatingId] = useState<number | null>(null)
  /** 待确认作废的行 */
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  /** 待确认删除的行（彻底删除，比作废更重） */
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const reload = useCallback(() => {
    setLoading(true)
    listUploadLinks()
      .then(setRows)
      .catch(() => toast.error('链接列表加载失败'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!open) return
    if (returningFromCreate.current) {
      returningFromCreate.current = false
    } else {
      setCreated(null)
    }
    setRotated(null)
    setRotatingId(null)
    setConfirmingId(null)
    setDeletingId(null)
    reload()
  }, [open, reload])

  const revoke = (id: number) => {
    revokeUploadLink(id)
      .then(() => {
        toast('已作废，客户手里的旧链接立即失效')
        reload()
      })
      .catch(() => toast.error('作废失败，请重试'))
  }

  const remove = (row: UploadLinkRow) => {
    deleteUploadLink(row.id)
      .then(() => {
        toast(`已删除「${row.title}」`)
        setDeletingId(null)
        // 删掉的行如果刚好是换发结果那张，把结果也清掉，避免悬空的提示
        if (rotated?.id === row.id) setRotated(null)
        reload()
      })
      .catch((e: unknown) => {
        setDeletingId(null)
        // 后端对非本人/非管理员一律 404：这里给明确文案，不说「出错了」让人猜
        const status = (e as { response?: { status?: number } })?.response?.status
        toast.error(status === 404 ? '无权删除该链接（仅创建人或管理员可删）' : errMessage(e, '删除失败'))
      })
  }

  const rotate = (row: UploadLinkRow) => {
    rotateUploadLink(row.id)
      .then((created2) => {
        // 必须走 api.buildShareUrl：手抄 `/u/<token>` 一旦路由改名就会静默发出 404 链接
        setRotated({ id: row.id, title: row.title, url: buildShareUrl(created2.token) })
        setRotatingId(null)
        reload()
      })
      .catch((e: unknown) => {
        setRotatingId(null)
        toast.error(errMessage(e, '换发失败'))
      })
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link2 className="h-4 w-4" /> 客户上传链接
            </DialogTitle>
            <DialogDescription>
              一次性链接一对一发给客户；客户上传的材料包会出现在本桌面（来源：客户链接上传）。
            </DialogDescription>
          </DialogHeader>

          {/* 说明「为什么旧链接没有复制按钮」：不写清楚，用户会以为功能坏了 */}
          <p className="flex items-start gap-1.5 rounded-lg bg-secondary/70 px-3 py-2 text-[11.5px] leading-5 text-muted-foreground">
            <Info className="mt-[2px] h-3.5 w-3.5 flex-none" />
            <span>
              出于安全考虑，链接明文只在生成/换发时显示一次，服务器不保存明文，因此<b>旧链接无法再次复制</b>。
              需要重新发送时请用「换发新链接」——旧链接会立即失效。
            </span>
          </p>

          <div className="max-h-[52vh] space-y-2 overflow-auto py-1">
            {loading ? (
              <LoadingBlock className="py-10 text-sm text-secondary-foreground" />
            ) : rows.length === 0 ? (
              <EmptyBlock className="py-10 text-sm text-secondary-foreground">还没有生成过链接</EmptyBlock>
            ) : (
              rows.map((row) => {
                const isOpen = row.state === 'open'
                const isRotating = rotatingId === row.id
                const isVoiding = confirmingId === row.id
                const isDeleting = deletingId === row.id
                const justRotated = rotated?.id === row.id
                return (
                  <div
                    key={row.id}
                    className={
                      justRotated
                        ? 'rounded-lg border border-amber-300/70 bg-amber-500/[0.03] px-3 py-2.5'
                        : 'rounded-lg border px-3 py-2.5'
                    }
                  >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{row.title}</span>
                      <StatusBadge tone={isOpen ? 'green' : 'neutral'} className="rounded-full px-2">
                        {STATE_LABEL[row.state] ?? row.state}
                      </StatusBadge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {[
                        row.client_name,
                        row.contract_name,
                        `已收 ${row.pack_count} 包 / ${formatBytes(row.used_bytes)}`,
                        `${formatExpiry(row.expires_at)} 到期`,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>

                    {/* 操作区：确认态互斥，永远只出现一组按钮，避免多行时点错 */}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {isDeleting ? (
                        <>
                          <span className="text-xs text-muted-foreground">
                            删除后<b>「{row.title}」</b>将不再出现在列表里（已收材料包会保留），确定？
                          </span>
                          <Button variant="destructive" size="sm" onClick={() => remove(row)}>
                            确认删除
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeletingId(null)}>
                            取消
                          </Button>
                        </>
                      ) : !isOpen ? (
                        /* 已失效/已作废的行：只剩「删除」可做（作废过的不必再作废） */
                        <Button variant="ghost" size="sm" onClick={() => setDeletingId(row.id)}>
                          <Trash2 className="h-3.5 w-3.5" /> 删除
                        </Button>
                      ) : isVoiding ? (
                        <>
                          <span className="text-xs text-muted-foreground">作废后客户手里的链接立即失效，确定？</span>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => {
                              setConfirmingId(null)
                              revoke(row.id)
                            }}
                          >
                            确认作废
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setConfirmingId(null)}>
                            取消
                          </Button>
                        </>
                      ) : isRotating ? (
                        <>
                          <span className="text-xs text-muted-foreground">
                            换发会让<b>「{row.title}」</b>的旧链接立即失效，确定？
                          </span>
                          <Button size="sm" onClick={() => rotate(row)}>
                            确认换发
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setRotatingId(null)}>
                            取消
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button variant="outline" size="sm" onClick={() => setRotatingId(row.id)}>
                            <RefreshCw className="h-3.5 w-3.5" /> 换发新链接
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setConfirmingId(row.id)}>
                            作废
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeletingId(row.id)}>
                            <Trash2 className="h-3.5 w-3.5" /> 删除
                          </Button>
                        </>
                      )}
                    </div>

                    {/* 换发结果就地显示在这一行里面，并点名标题——多行也不会搞混 */}
                    {justRotated && (
                      <OneTimeUrlNotice
                        url={rotated.url}
                        hint={`「${rotated.title}」的新链接已生成，旧链接已失效`}
                      />
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* 新建结果：不属于任何已有行，单独放在列表下方 */}
          {created && <OneTimeUrlNotice url={created.url} hint={`「${created.title}」的链接已生成`} />}

          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => {
                // 关闭本面板、只留一个新建弹窗：两个 Dialog 叠在一起会让用户以为卡了
                onOpenChange(false)
                setCreating(true)
              }}
            >
              <Plus className="h-4 w-4" /> 新建链接
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ShareLinkDialog
        open={creating}
        onOpenChange={(v) => {
          setCreating(v)
          if (!v) {
            returningFromCreate.current = true
            onOpenChange(true)
          }
        }}
        onCreated={(url, title) => {
          setCreated({ title, url })
          reload()
        }}
      />
    </>
  )
}
