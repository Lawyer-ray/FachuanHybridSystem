import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, FileText, FolderClosed, FolderPlus, Loader2, Pencil, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { withDownloadTicket } from '@/lib/download-ticket'
import { errMessage } from '@/lib/errors'
import {
  createFolderEntry,
  folderFileUrl,
  listFolderEntries,
  renameFolderEntry,
  uploadFolderFiles,
  type FolderOwnerKind,
} from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { stripEntryParens } from './detail-domain'
import { EntryInput } from './folder-tree-ui'
import { fmtSize, type NodeActions, type TreeCtx } from './folder-tree-types'

/**
 * 绑定文件夹树（案件卡「文件夹视图」与右栏「合同文件夹」共用）。
 * 树形就地展开（非面包屑）、逐层懒加载；管理动作长在对象上：
 * 文件夹行 hover 显「＋ 新建子夹 / ✎ 重命名」，文件拖到文件夹行即上传；
 * 成功静默只刷新，失败才弹窗（用户口味）。
 */

/** 展开时才挂载（懒加载）：父层 query 数据已到位才渲染本组件 */
function useLayer(kind: FolderOwnerKind, ownerId: number, subpath: string) {
  return useQuery({
    queryKey: workbenchKeys.folderEntriesItem(kind, ownerId, subpath),
    queryFn: () => listFolderEntries(kind, ownerId, subpath),
    staleTime: 60_000,
    retry: false,
  })
}

export function FolderTree({ kind, ownerId, maxH = '' }: { kind: FolderOwnerKind; ownerId: number; maxH?: string }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [creatingIn, setCreatingIn] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<{ subpath: string; name: string } | null>(null)
  const [dropOn, setDropOn] = useState<string | null>(null)

  const ctx: TreeCtx = useMemo(
    () => ({
      kind,
      ownerId,
      open,
      toggle: (subpath) =>
        setOpen((prev) => {
          const next = new Set(prev)
          if (next.has(subpath)) next.delete(subpath)
          else next.add(subpath)
          return next
        }),
      creatingIn,
      setCreatingIn,
      renaming,
      setRenaming,
      dropOn,
      setDropOn,
    }),
    [kind, ownerId, open, creatingIn, renaming, dropOn],
  )

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries(kind, ownerId) })
  }
  const fail = (e: unknown, what: string) => toast.error(what + '失败：' + errMessage(e, '请重试'))

  const mkdir = useMutation({
    mutationFn: (p: { subpath: string; name: string }) => createFolderEntry(kind, ownerId, p.subpath, p.name),
    onSuccess: (_d, p) => {
      invalidate()
      setOpen((prev) => new Set(prev).add(p.subpath))
      setCreatingIn(null)
    },
    onError: (e) => fail(e, '新建文件夹'),
  })
  const rename = useMutation({
    mutationFn: (p: { subpath: string; name: string }) => renameFolderEntry(kind, ownerId, p.subpath, p.name),
    onSuccess: () => {
      invalidate()
      setRenaming(null)
    },
    onError: (e) => fail(e, '重命名'),
  })
  const upload = useMutation({
    mutationFn: (p: { subpath: string; files: File[] }) => uploadFolderFiles(kind, ownerId, p.subpath, p.files),
    onSuccess: (d) => {
      invalidate()
      if (d.saved.length > 1) toast.success('已上传 ' + d.saved.length + ' 个文件')
    },
    onError: (e) => fail(e, '上传'),
  })

  const root = useLayer(kind, ownerId, '')

  const actions = useMemo(
    () => ({
      mkdir: (p: { subpath: string; name: string }) => mkdir.mutate(p),
      rename: (p: { subpath: string; name: string }) => rename.mutate(p),
      upload: (subpath: string, files: File[]) => upload.mutate({ subpath, files }),
    }),
    [mkdir, rename, upload],
  )

  if (root.isPending) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        正在读取文件夹…
      </div>
    )
  }
  if (root.isError) {
    return <div className="py-2 text-xs text-muted-foreground/70">{errMessage(root.error, '文件夹读取失败')}</div>
  }

  return (
    <div
      className={
        'text-secondary-foreground ' +
        (maxH ? maxH + ' overflow-y-auto ' : '') +
        (dropOn === '' ? 'rounded-[8px] ring-1 ring-foreground/25 ' : '')
      }
      // 拖到空白区 = 上传到绑定根（行级 drop 已 stopPropagation，不会重复触发）
      onDragOver={(e) => {
        e.preventDefault()
        setDropOn('')
      }}
      onDragLeave={() => setDropOn((cur) => (cur === '' ? null : cur))}
      onDrop={(e) => {
        e.preventDefault()
        setDropOn(null)
        const files = Array.from(e.dataTransfer.files)
        if (files.length > 0) actions.upload('', files)
      }}
    >
      {/* 根工具行：唯一常显管理按钮（新建根级文件夹）；拖整片区域 = 传到绑定根 */}
      <div className="mb-1 flex items-center justify-end">
        <button
          type="button"
          className="flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setCreatingIn('')}
        >
          <FolderPlus className="size-3.5" /> 新建文件夹
        </button>
      </div>
      <NodeList ctx={ctx} subpath="" actions={actions} />
    </div>
  )
}

/* ============ 递归层 ============ */

function NodeList({ ctx, subpath, actions }: { ctx: TreeCtx; subpath: string; actions: NodeActions }) {
  const q = useLayer(ctx.kind, ctx.ownerId, subpath)
  if (q.isPending) {
    return (
      <div className="flex items-center gap-1.5 py-1.5 pl-2 text-[11.5px] text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> 读取中…
      </div>
    )
  }
  if (q.isError) {
    return <div className="py-1.5 pl-2 text-[11.5px] text-muted-foreground/70">{errMessage(q.error, '读取失败')}</div>
  }
  const d = q.data
  if (!d || d.folders.length === 0) {
    if (subpath === '') {
      return <div className="py-2 text-xs text-muted-foreground/70">{d?.files.length ? '' : '文件夹是空的'}</div>
    }
    if (d.files.length === 0 && ctx.creatingIn !== subpath) {
      return <div className="py-1.5 pl-2 text-[11.5px] text-muted-foreground/60">（空）</div>
    }
  }

  return (
    <div className="flex flex-col">
      {ctx.creatingIn === subpath && (
        <div className="py-1 pl-2">
          <EntryInput
            placeholder="新文件夹名"
            onConfirm={(name) => actions.mkdir({ subpath, name })}
            onCancel={() => ctx.setCreatingIn(null)}
          />
        </div>
      )}
      {d?.folders.map((f) => (
        <FolderRow key={f.subpath} ctx={ctx} folder={f} actions={actions} />
      ))}
      {d?.files.map((f) => (
        <FileRow key={f.subpath} ctx={ctx} file={f} actions={actions} />
      ))}
    </div>
  )
}

function FolderRow({
  ctx,
  folder,
  actions,
}: {
  ctx: TreeCtx
  folder: { name: string; subpath: string }
  actions: NodeActions
}) {
  const isOpen = ctx.open.has(folder.subpath)
  const renamingThis = ctx.renaming?.subpath === folder.subpath
  const dropping = ctx.dropOn === folder.subpath

  return (
    <div>
      {renamingThis ? (
        <div className="py-1 pl-2">
          <EntryInput
            initial={folder.name}
            placeholder="新名称"
            onConfirm={(name) => actions.rename({ subpath: folder.subpath, name })}
            onCancel={() => ctx.setRenaming(null)}
          />
        </div>
      ) : (
        <div
          role="button"
          tabIndex={0}
          className={
            'group relative flex cursor-pointer items-center gap-1.5 rounded-[7px] py-[5px] pr-1 transition-colors hover:bg-secondary ' +
            (dropping ? 'bg-secondary ring-1 ring-foreground/30 ' : '')
          }
          style={{ paddingLeft: 4 }}
          onClick={() => ctx.toggle(folder.subpath)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') ctx.toggle(folder.subpath)
          }}
          onDragOver={(e) => {
            e.preventDefault()
            e.stopPropagation()
            ctx.setDropOn(folder.subpath)
          }}
          onDragLeave={() => ctx.setDropOn(null)}
          onDrop={(e) => {
            e.preventDefault()
            e.stopPropagation()
            ctx.setDropOn(null)
            const files = Array.from(e.dataTransfer.files)
            if (files.length > 0) {
              // 上传目标保持展开（toggle 会把已展开的收起，传完反而看不见）
              if (!ctx.open.has(folder.subpath)) ctx.toggle(folder.subpath)
              actions.upload(folder.subpath, files)
            }
          }}
        >
          <ChevronRight
            className={
              'size-3.5 flex-none text-muted-foreground/60 transition-transform ' + (isOpen ? 'rotate-90' : '')
            }
          />
          <FolderClosed className="size-[15px] flex-none text-muted-foreground/70" />
          <span className="min-w-0 flex-1 truncate text-[13px]" title={folder.name}>
            {stripEntryParens(folder.name)}
          </span>
          {/* 上下文动作 hover 显形：浮层绝对定位，不挤占行布局（否则名字会被压短/跳动） */}
          <span className="absolute top-1/2 right-1 hidden -translate-y-1/2 items-center gap-0.5 rounded-[6px] bg-secondary px-0.5 group-hover:flex">
            <button
              type="button"
              title="新建子文件夹"
              className="cursor-pointer rounded p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation()
                ctx.setCreatingIn(folder.subpath)
                ctx.toggle(folder.subpath)
              }}
            >
              <Plus className="size-3.5" />
            </button>
            <button
              type="button"
              title="重命名"
              className="cursor-pointer rounded p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation()
                ctx.setRenaming({ subpath: folder.subpath, name: folder.name })
              }}
            >
              <Pencil className="size-3.5" />
            </button>
          </span>
        </div>
      )}
      {isOpen && (
        <div className="ml-4 border-l border-border-light pl-1.5">
          <NodeList ctx={ctx} subpath={folder.subpath} actions={actions} />
        </div>
      )}
    </div>
  )
}

function FileRow({
  ctx,
  file,
  actions,
}: {
  ctx: TreeCtx
  file: { name: string; subpath: string; size: number; modified_at: string }
  actions: NodeActions
}) {
  const renamingThis = ctx.renaming?.subpath === file.subpath

  const preview = async () => {
    window.open(await withDownloadTicket(folderFileUrl(ctx.kind, ctx.ownerId, file.subpath)), '_blank', 'noopener')
  }

  if (renamingThis) {
    return (
      <div className="py-1 pl-2">
        <EntryInput
          initial={file.name}
          placeholder="新名称"
          onConfirm={(name) => actions.rename({ subpath: file.subpath, name })}
          onCancel={() => ctx.setRenaming(null)}
        />
      </div>
    )
  }
  return (
    <div
      role="button"
      tabIndex={0}
      className="group relative flex cursor-pointer items-center gap-1.5 rounded-[7px] py-[5px] pr-1 transition-colors hover:bg-secondary"
      style={{ paddingLeft: 20 }}
      title={'预览 ' + file.name}
      onClick={() => void preview()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') void preview()
      }}
    >
      <FileText className="size-[15px] flex-none text-muted-foreground/70" />
      <span className="min-w-0 flex-1 truncate text-[13px]" title={file.name}>
        {stripEntryParens(file.name)}
      </span>
      {/* 日期/大小 hover 时让位给浮层按钮（绝对定位，不参与布局） */}
      <span className="flex-none text-[11px] whitespace-nowrap text-muted-foreground/80 tabular-nums group-hover:opacity-0">
        {file.modified_at.slice(0, 10)}
        {file.size > 0 && ' · ' + fmtSize(file.size)}
      </span>
      <span className="absolute top-1/2 right-1 hidden -translate-y-1/2 items-center rounded-[6px] bg-secondary px-0.5 group-hover:flex">
        <button
          type="button"
          title="重命名"
          className="cursor-pointer rounded p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
          onClick={(e) => {
            e.stopPropagation()
            ctx.setRenaming({ subpath: file.subpath, name: file.name })
          }}
        >
          <Pencil className="size-3.5" />
        </button>
      </span>
    </div>
  )
}
