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
import { Info, Link2, Plus } from 'lucide-react'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { buildShareUrl, deleteUploadLink, listUploadLinks, revokeUploadLink, rotateUploadLink, type UploadLinkRow } from '../api'
import { ShareLinkDialog } from './ShareLinkDialog'
import { OneTimeUrlNotice, ShareLinkRow, type PendingAction } from './ShareLinkRow'

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
  /**
   * 行内待确认的动作：换发 / 作废 / 删除共用一个状态（破坏性操作先确认再执行）。
   *
   * 三者共用同一行操作区、同一时刻只可能出现一组确认按钮，所以用一个带 kind 的
   * 单状态：三个各自独立的 `xxxId` 能同时为真，那种「不可能组合」只能靠渲染顺序
   * 去维持，改一处判断就会在同一行冒出两组确认按钮。
   * （换发**成功后的结果**不在这里——它要留在那一行里继续显示且与确认态无关，见 rotated。）
   */
  const [pending, setPending] = useState<PendingAction | null>(null)

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
    setPending(null)
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
        setPending(null)
        // 删掉的行如果刚好是换发结果那张，把结果也清掉，避免悬空的提示
        if (rotated?.id === row.id) setRotated(null)
        reload()
      })
      .catch((e: unknown) => {
        setPending(null)
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
        setPending(null)
        reload()
      })
      .catch((e: unknown) => {
        setPending(null)
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
              rows.map((row) => (
                <ShareLinkRow
                  key={row.id}
                  row={row}
                  pending={pending?.id === row.id ? pending.kind : null}
                  rotated={rotated?.id === row.id ? rotated : null}
                  onAsk={(kind) => setPending({ kind, id: row.id })}
                  onCancel={() => setPending(null)}
                  onConfirmRotate={() => rotate(row)}
                  onConfirmRevoke={() => {
                    setPending(null)
                    revoke(row.id)
                  }}
                  onConfirmDelete={() => remove(row)}
                />
              ))
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
