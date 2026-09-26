import { FolderOpen, Pencil, Plus, Trash2 } from 'lucide-react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { cn } from '@/lib/utils'
import { PackCard } from './PackCard'
import type { InboxMessage, PackStatus } from '../types'

type Tab = PackStatus

/**
 * 材料包网格：每张卡的右键菜单（打开 / 重命名 / 删除）+ 离场动画 +
 * 「todo」页签下的虚线新建槽 + 各页签空态提示。
 */
export function PackGrid({
  gridRef,
  wrapRef,
  ringRef,
  packs,
  tab,
  leaving,
  onOpen,
  onReject,
  onAccept,
  onRename,
  onDelete,
  onPickFiles,
}: {
  gridRef: React.RefObject<HTMLDivElement | null>
  wrapRef: React.RefObject<HTMLDivElement | null>
  ringRef: React.RefObject<HTMLDivElement | null>
  packs: InboxMessage[]
  tab: Tab
  leaving: Record<number, 'left' | 'right'>
  onOpen: (index: number) => void
  onReject: (pack: InboxMessage) => void
  onAccept: (pack: InboxMessage) => void
  onRename: (pack: InboxMessage) => void
  onDelete: (pack: InboxMessage) => void
  onPickFiles: () => void
}) {
  return (
    <div className="relative" ref={wrapRef}>
      <div
        ref={gridRef}
        className="grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-4"
      >
        {packs.map((p, i) => (
          <div
            key={p.id}
            data-pack-idx={i}
            className={cn(leaving[p.id] === 'right' && 'leave-right', leaving[p.id] === 'left' && 'leave-left')}
          >
            <ContextMenu>
              <ContextMenuTrigger className="block">
                <PackCard
                  pack={p}
                  finished={p.segs > 0 && p.named === p.segs}
                  leaving={leaving[p.id] ?? null}
                  onOpen={() => onOpen(i)}
                  onReject={() => onReject(p)}
                  onAccept={() => onAccept(p)}
                />
              </ContextMenuTrigger>
              <ContextMenuContent className="w-44">
                <ContextMenuItem onSelect={() => onOpen(i)}>
                  <FolderOpen /> 打开材料包
                </ContextMenuItem>
                <ContextMenuItem onSelect={() => onRename(p)}>
                  <Pencil /> 重命名材料包
                </ContextMenuItem>
                <ContextMenuSeparator />
                <ContextMenuItem variant="destructive" onSelect={() => onDelete(p)}>
                  <Trash2 /> 删除材料包
                </ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          </div>
        ))}

        {/* 虚线槽：第二个新建入口 */}
        {tab === 'todo' && (
          <button
            type="button"
            onClick={onPickFiles}
            className="flex min-h-[280px] cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[13px] border-[1.5px] border-dashed border-zinc-300 text-secondary-foreground transition-colors hover:border-zinc-400 hover:bg-card hover:text-foreground"
          >
            <span className="grid h-[34px] w-[34px] place-items-center rounded-[9px] bg-secondary text-secondary-foreground">
              <Plus className="h-4 w-4" />
            </span>
            <span className="text-sm">
              {packs.length === 0 ? '全部处理完了，拖入新材料，或点这里' : '拖入材料，或点这里选文件'}
            </span>
            <span className="text-[11.5px] text-muted-foreground">PDF · Word · 图片 · 视频，混着来都行</span>
          </button>
        )}

        {packs.length === 0 && tab !== 'todo' && (
          <div className="col-span-full flex flex-col items-center gap-2 rounded-[13px] border border-dashed border-zinc-300 py-16 text-sm text-secondary-foreground">
            这里还没有{tab === 'done' ? '已归案' : '归档'}的材料包
          </div>
        )}
      </div>
      <div ref={ringRef} className="mp-ring" />
    </div>
  )
}
