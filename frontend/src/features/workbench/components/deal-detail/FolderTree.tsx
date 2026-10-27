import { useMemo } from 'react'
import { FolderPlus, Loader2 } from 'lucide-react'

import { errMessage } from '@/lib/errors'
import type { FolderOwnerKind } from '../../api'
import type { TreeCtx } from './folder-tree-types'
import { FolderNodeList } from './FolderNodeList'
import { TreeContextMenu } from './folder-tree-menu'
import { buildFolderMenuItems } from './folder-tree-menu-items'
import { useFolderTreeState } from './use-folder-tree'
import { useFolderDrop } from './use-folder-drop'

/**
 * 绑定文件夹树（案件卡「文件夹视图」与右栏「合同文件夹」共用）。
 * 树形就地展开（非面包屑）、逐层懒加载；管理动作长在对象上：
 * 文件夹行 hover 显「＋ 新建子夹 / ✎ 重命名」，文件拖到文件夹行即上传；
 * 右键菜单：复制 / 粘贴到此 / 重命名 / 移入 _已删除。
 * 成功静默只刷新，失败才弹窗（用户口味）。
 *
 * 本组件只做组装：状态与 mutation 编排在 use-folder-tree，拖放接线在
 * use-folder-drop，递归渲染在 FolderNodeList（行组件 FolderRow / FolderFileRow）。
 */
export function FolderTree({
  kind,
  ownerId,
  maxH = '',
  title,
  onReviewFile,
  onOpenFile,
  selectedSubpath,
}: {
  kind: FolderOwnerKind
  ownerId: number
  maxH?: string
  /** 传入时渲染节标题行（右栏用，让「新建文件夹」与标题同行） */
  title?: string
  /** 传入时文件行 hover 显「AI 审查」按钮（非诉详情页的合同回审入口） */
  onReviewFile?: (f: { subpath: string; name: string }) => void
  /**
   * 传入时点文件行 = 打开预览（而不是下载）。
   *
   * 以前 onClick 直接 `window.open(下载地址)`——浏览器没有 docx 渲染器，
   * 点开必然变成下载，律师想「看一眼」得先存盘再开 Word。传了本回调就
   * 交给调用方渲染 OnlyOffice 预览；不传则保留旧行为（兼容案件页）。
   */
  onOpenFile?: (f: { subpath: string; name: string }) => void
  /** 当前预览中的 subpath（行高亮用） */
  selectedSubpath?: string | null
}) {
  const state = useFolderTreeState(kind, ownerId)
  const actions = state.mutation
  // 拖入文件夹行时展开目标（未展开才展开；toggle 会收起已展开的）
  const drop = useFolderDrop(kind, ownerId, actions.upload, (subpath) => {
    if (!state.open.has(subpath)) state.toggle(subpath)
  })
  const { setMenu, root } = state

  const ctx: TreeCtx = useMemo(
    () => ({
      kind,
      ownerId,
      open: state.open,
      toggle: state.toggle,
      creatingIn: state.creatingIn,
      setCreatingIn: state.setCreatingIn,
      renaming: state.renaming,
      setRenaming: state.setRenaming,
      deleting: state.deleting,
      setDeleting: state.setDeleting,
      dropOn: drop.dropOn,
      folderDropProps: drop.folderDropProps,
      folderDragProps: drop.folderDragProps,
      fileDragProps: drop.fileDragProps,
      openMenu: (e, entry) => setMenu({ x: e.clientX, y: e.clientY, ...entry }),
      onReviewFile,
      onOpenFile,
      selectedSubpath,
    }),
    // state 的字段是逐项列出的 setState/展开态，作为依赖列出即为 hook 的原有语义
    [kind, ownerId, state, drop, setMenu, onReviewFile, onOpenFile, selectedSubpath],
  )

  const menuItems = useMemo(() => buildFolderMenuItems(state), [state])

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
        (drop.dropOn === '' ? 'rounded-[8px] ring-1 ring-foreground/25 ' : '')
      }
      {...drop.rootDropProps}
    >
      {/* 标题行：传 title 时与「新建文件夹」同行（右栏），否则只有右对齐按钮（案件卡） */}
      <div className="mb-1 flex items-center gap-2">
        {title && (
          <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">{title}</h4>
        )}
        <button
          type="button"
          className="ml-auto flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => state.setCreatingIn('')}
        >
          <FolderPlus className="size-3.5" /> 新建文件夹
        </button>
      </div>
      <FolderNodeList ctx={ctx} subpath="" actions={actions} />

      {state.menu && (
        <TreeContextMenu
          x={state.menu.x}
          y={state.menu.y}
          items={menuItems}
          onClose={() => state.setMenu(null)}
        />
      )}
    </div>
  )
}
