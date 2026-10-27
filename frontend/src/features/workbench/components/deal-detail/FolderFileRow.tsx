import { FileSearch, Pencil } from 'lucide-react'

import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl } from '../../api'
import { stripEntryParens } from './detail-domain'
import { DeleteConfirm } from './folder-tree-menu'
import { EntryInput } from './folder-tree-ui'
import { fmtSize, type NodeActions, type TreeCtx } from './folder-tree-types'
import { FileKindBadge } from './FileKindBadge'

/**
 * 文件夹树里的单个文件行（从 FolderTree 拆出）。
 *
 * 一行承载四种交互：点行 = 预览（无预览通道则下载）、拖出去 = AI 文件引用、
 * 右键 = 复制/重命名/删除、hover 浮层 = AI 审查 / 重命名。重命名与删除确认
 * 在同一位置就地替换整行（不叠弹窗）。
 */
export function FolderFileRow({
  ctx,
  file,
  actions,
}: {
  ctx: TreeCtx
  file: { name: string; subpath: string; size: number; modified_at: string }
  actions: NodeActions
}) {
  const renamingThis = ctx.renaming?.subpath === file.subpath
  const deletingThis = ctx.deleting?.subpath === file.subpath

  const preview = async () => {
    // 有预览通道就交给调用方（OnlyOffice 渲染）；否则退回下载。
    // 浏览器没 docx 渲染器，`window.open` 对 .docx 必然变成下载。
    if (ctx.onOpenFile) {
      ctx.onOpenFile({ subpath: file.subpath, name: file.name })
      return
    }
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
  if (deletingThis) {
    return (
      <div className="py-1 pl-2">
        <DeleteConfirm
          name={stripEntryParens(file.name)}
          onConfirm={() => actions.deleteEntry(file.subpath)}
          onCancel={() => ctx.setDeleting(null)}
        />
      </div>
    )
  }
  return (
    <div
      role="button"
      tabIndex={0}
      className={
        'group relative flex cursor-pointer items-center gap-1.5 rounded-[7px] py-[5px] pr-1 transition-colors ' +
        // 选中态与 hover 分开：律师常要「看着预览、在列表里点下一份」，
        // 光靠 hover 无法表达「当前正在看的就是这份」
        (ctx.selectedSubpath === file.subpath
          ? 'bg-foreground/[0.07] shadow-[inset_2px_0_0_var(--color-foreground)]'
          : 'hover:bg-secondary')
      }
      style={{ paddingLeft: 20 }}
      aria-current={ctx.selectedSubpath === file.subpath ? 'true' : undefined}
      title={'预览 ' + file.name}
      onClick={() => void preview()}
      // 绑定文件拖为 AI 引用（自定义 MIME，与系统外文件的 Files 通道区分）；
      // 合同/案件绑定各走各的后端通道（kind 决定）
      {...ctx.fileDragProps({ subpath: file.subpath, name: file.name })}
      onKeyDown={(e) => {
        // role="button" 需同时响应 Enter 与 Space（Space 要 preventDefault 防滚动）
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          void preview()
        }
      }}
      onContextMenu={(e) => {
        e.preventDefault()
        e.stopPropagation()
        ctx.openMenu(e, { subpath: file.subpath, name: file.name, isFolder: false })
      }}
    >
      <FileKindBadge name={file.name} />
      <span className="min-w-0 flex-1 truncate text-[12.5px]" title={file.name}>
        {stripEntryParens(file.name)}
      </span>
      {/* 日期/大小 hover 时让位给浮层按钮（绝对定位，不参与布局） */}
      <span className="flex-none text-[11px] whitespace-nowrap text-muted-foreground/80 tabular-nums group-hover:opacity-0">
        {file.modified_at.slice(0, 10)}
        {file.size > 0 && ' · ' + fmtSize(file.size)}
      </span>
      <span className="absolute top-1/2 right-1 hidden -translate-y-1/2 items-center rounded-[6px] bg-secondary px-0.5 group-hover:flex">
        {ctx.onReviewFile && (
          <button
            type="button"
            title="AI 审查此文件"
            className="cursor-pointer rounded p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation()
              ctx.onReviewFile?.({ subpath: file.subpath, name: file.name })
            }}
          >
            <FileSearch className="size-3.5" />
          </button>
        )}
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
