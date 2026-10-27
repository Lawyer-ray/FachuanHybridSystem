import { useQuery } from '@tanstack/react-query'
import { ChevronRight, FolderClosed, Loader2, Pencil, Plus } from 'lucide-react'

import { errMessage } from '@/lib/errors'
import { listFolderEntries } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { stripEntryParens } from './detail-domain'
import { DeleteConfirm } from './folder-tree-menu'
import { FolderFileRow } from './FolderFileRow'
import { EntryInput } from './folder-tree-ui'
import type { NodeActions, TreeCtx } from './folder-tree-types'

/**
 * 文件夹树的递归层（从 FolderTree 拆出）：FolderNodeList → FolderRow → 子层。
 *
 * 逐层懒加载：每展开一层才请求该层 entries（单层 5-20 项，不虚拟化）。
 * 两个易踩的边界留在本文件：根目录「有文件但没有子夹」不能整个判空
 * （曾导致只有文件的根目录一份文件都不显示）；创建输入框只在展开态渲染。
 */

/** 展开时才挂载（懒加载）：父层 query 数据已到位才渲染本组件 */
function useLayer(ctx: TreeCtx, subpath: string) {
  return useQuery({
    queryKey: workbenchKeys.folderEntriesItem(ctx.kind, ctx.ownerId, subpath),
    queryFn: () => listFolderEntries(ctx.kind, ctx.ownerId, subpath),
    staleTime: 60_000,
    retry: false,
  })
}

export function FolderNodeList({
  ctx,
  subpath,
  actions,
}: {
  ctx: TreeCtx
  subpath: string
  actions: NodeActions
}) {
  const q = useLayer(ctx, subpath)
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
  if (!d) {
    return <div className="py-2 text-xs text-muted-foreground/70">文件夹是空的</div>
  }
  if (d.folders.length === 0) {
    if (subpath === '') {
      // 根目录没有子文件夹：只在真的什么都没有时提示「文件夹是空的」。
      // 有文件时必须继续往下渲染（此处曾直接 return，导致只有文件的根目录
      // 一个文件都不显示）
      if (d.files.length === 0 && ctx.creatingIn !== subpath) {
        return <div className="py-2 text-xs text-muted-foreground/70">文件夹是空的</div>
      }
    } else if (d.files.length === 0 && ctx.creatingIn !== subpath) {
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
        <FolderFileRow key={f.subpath} ctx={ctx} file={f} actions={actions} />
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
  const deletingThis = ctx.deleting?.subpath === folder.subpath
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
      ) : deletingThis ? (
        <div className="py-1 pl-2">
          <DeleteConfirm
            name={stripEntryParens(folder.name)}
            onConfirm={() => actions.deleteEntry(folder.subpath)}
            onCancel={() => ctx.setDeleting(null)}
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
          onContextMenu={(e) => {
            e.preventDefault()
            e.stopPropagation()
            ctx.openMenu(e, { subpath: folder.subpath, name: folder.name, isFolder: true })
          }}
          // 目录拖出去 = AI 的「目录引用」；拖入 = 上传到该目录
          {...ctx.folderDragProps({ subpath: folder.subpath, name: folder.name })}
          {...ctx.folderDropProps(folder.subpath, isOpen)}
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
                // 创建输入框只在 isOpen 时渲染：对已展开的文件夹 toggle 等于收起，
                // 输入框会落在收起子树里完全看不见。所以只在未展开时展开。
                if (!ctx.open.has(folder.subpath)) ctx.toggle(folder.subpath)
                ctx.setCreatingIn(folder.subpath)
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
          <FolderNodeList ctx={ctx} subpath={folder.subpath} actions={actions} />
        </div>
      )}
    </div>
  )
}
