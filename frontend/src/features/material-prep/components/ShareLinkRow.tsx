/**
 * 客户上传链接的**一行**：标题 / 状态徽标 / 已收统计 / 到期日 + 行内操作区
 * （换发 / 作废 / 删除，破坏性操作先在该行内二次确认）+ 换发结果就地展示。
 *
 * 为什么从 ShareLinkPanel 拆出去：面板管的是「一个资源」——拉列表、四个接口调用
 * （reload / revoke / remove / rotate）、新建子弹窗、以及「同一时刻只允许一行在确认」
 * 的互斥状态；而这里的组件管的是「一行怎么画、点哪个键进入哪个确认态」。后者有
 * 三四层早退分支（确认删除 / 已失效只剩删除 / 确认作废 / 确认换发 / 常规三键），
 * 和面板的请求编排揉在一起时，读的人很难分清哪段是数据、哪段是渲染。
 *
 * ⚠️ 「谁是确认态」的**判定结果**仍由面板持有并传进来（`pending` / `rotated`），
 * 本文件只是把它们渲染成对应的那一组按钮 —— 互斥语义（同一时刻只有一行在确认）
 * 依赖父层的单个 `pending` 状态，搬进行内就会退化成每行各自为政。
 */
import type { ReactNode } from 'react'
import { RefreshCw, Trash2 } from 'lucide-react'

import { formatBytes } from '@/lib/format'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'

import type { UploadLinkRow } from '../api'
import { ShareUrlBox } from './ShareLinkDialog'

/** 链接状态 → 中文标签（只在本行的徽标里用） */
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

/** 行内等确认的破坏性动作（换发 / 作废 / 删除） */
export type PendingAction = { kind: 'rotate' | 'revoke' | 'delete'; id: number }

/** 一次性明文提示条：刚生成/刚换发的链接都走它，风格统一 */
export function OneTimeUrlNotice({ url, hint }: { url: string; hint: string }) {
  return (
    <div className="mt-2 space-y-1.5 rounded-lg border border-amber-300/60 bg-amber-500/5 px-3 py-2.5">
      <p className="text-xs font-medium text-amber-700">{hint}</p>
      <ShareUrlBox url={url} />
      <p className="text-[11px] text-muted-foreground">关掉这个面板后就看不到了，如需再发请用「换发」。</p>
    </div>
  )
}

/**
 * 确认态：一句提示 + 确认键 + 取消。三个破坏性动作共用同一套确认 UI。
 */
function ConfirmBar({
  hint,
  confirmLabel,
  destructive = false,
  onConfirm,
  onCancel,
}: {
  hint: ReactNode
  confirmLabel: string
  /** 作废/删除用红色确认键：它们比换发更重 */
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <>
      <span className="text-xs text-muted-foreground">{hint}</span>
      <Button variant={destructive ? 'destructive' : 'default'} size="sm" onClick={onConfirm}>
        {confirmLabel}
      </Button>
      <Button variant="ghost" size="sm" onClick={onCancel}>
        取消
      </Button>
    </>
  )
}

/**
 * 行内操作区：常规三键 / 三个确认态 / 已失效行只留删除。
 *
 * 互斥由 `pending`（单个判别式）决定，而不是三个 `xxxId` 布尔汤：早退链从上往下
 * 只有一种情况成立，任何时候都只渲染出一组按钮。
 */
function RowActions({
  row,
  isOpen,
  pending,
  onAsk,
  onCancel,
  onConfirmRotate,
  onConfirmRevoke,
  onConfirmDelete,
}: {
  row: UploadLinkRow
  isOpen: boolean
  /** 该行正在等确认的动作；null = 常规操作组 */
  pending: PendingAction['kind'] | null
  onAsk: (kind: PendingAction['kind']) => void
  onCancel: () => void
  onConfirmRotate: () => void
  onConfirmRevoke: () => void
  onConfirmDelete: () => void
}) {
  if (pending === 'delete') {
    return (
      <ConfirmBar
        hint={
          <>
            删除后<b>「{row.title}」</b>将不再出现在列表里（已收材料包会保留），确定？
          </>
        }
        confirmLabel="确认删除"
        destructive
        onConfirm={onConfirmDelete}
        onCancel={onCancel}
      />
    )
  }

  // 已失效/已作废的行：只剩「删除」可做（作废过的不必再作废）
  if (!isOpen) {
    return (
      <Button variant="ghost" size="sm" onClick={() => onAsk('delete')}>
        <Trash2 className="h-3.5 w-3.5" /> 删除
      </Button>
    )
  }

  if (pending === 'revoke') {
    return (
      <ConfirmBar
        hint="作废后客户手里的链接立即失效，确定？"
        confirmLabel="确认作废"
        destructive
        onConfirm={onConfirmRevoke}
        onCancel={onCancel}
      />
    )
  }

  if (pending === 'rotate') {
    return (
      <ConfirmBar
        hint={
          <>
            换发会让<b>「{row.title}」</b>的旧链接立即失效，确定？
          </>
        }
        confirmLabel="确认换发"
        onConfirm={onConfirmRotate}
        onCancel={onCancel}
      />
    )
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => onAsk('rotate')}>
        <RefreshCw className="h-3.5 w-3.5" /> 换发新链接
      </Button>
      <Button variant="ghost" size="sm" onClick={() => onAsk('revoke')}>
        作废
      </Button>
      <Button variant="ghost" size="sm" onClick={() => onAsk('delete')}>
        <Trash2 className="h-3.5 w-3.5" /> 删除
      </Button>
    </>
  )
}

export function ShareLinkRow({
  row,
  pending,
  rotated,
  onAsk,
  onCancel,
  onConfirmRotate,
  onConfirmRevoke,
  onConfirmDelete,
}: {
  row: UploadLinkRow
  /** 该行正在等确认的动作；null = 常规操作组（判定在父层，保证全局互斥） */
  pending: PendingAction['kind'] | null
  /** 换发结果：仅本行刚换发成功时有值（判定同样在父层） */
  rotated: { title: string; url: string } | null
  onAsk: (kind: PendingAction['kind']) => void
  onCancel: () => void
  onConfirmRotate: () => void
  onConfirmRevoke: () => void
  onConfirmDelete: () => void
}) {
  const isOpen = row.state === 'open'
  const justRotated = rotated != null

  return (
    <div
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
        <RowActions
          row={row}
          isOpen={isOpen}
          pending={pending}
          onAsk={onAsk}
          onCancel={onCancel}
          onConfirmRotate={onConfirmRotate}
          onConfirmRevoke={onConfirmRevoke}
          onConfirmDelete={onConfirmDelete}
        />
      </div>

      {/* 换发结果就地显示在这一行里面，并点名标题——多行也不会搞混 */}
      {rotated && (
        <OneTimeUrlNotice url={rotated.url} hint={`「${rotated.title}」的新链接已生成，旧链接已失效`} />
      )}
    </div>
  )
}
