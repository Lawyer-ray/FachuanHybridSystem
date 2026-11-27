import type { DragEvent, MouseEvent } from 'react'

import type { FolderOwnerKind } from '../../api'

/** 绑定文件夹树的共享类型（与组件分开，满足 react-refresh 仅导出组件的约束）。
 *  本文件**只导出类型**：运行时函数一律落在 `lib/` 或有名字的 `*-domain.ts`/
 *  `use-*.ts` 里——类型文件混入运行时值会让 `import type` 与值导入混在一处，
 *  也让「删掉一个类型文件」不再是纯编译期操作。 */

/**
 * 拖放 / 拖拽接线（use-folder-drop 产出，经 TreeCtx 下发给行组件）。
 * 类型写在这里而不是从 hook 文件导出：types 文件只导出类型，不引 React。
 */
export type DropHandlers = {
  onDragOver: (e: DragEvent) => void
  onDragLeave: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
}

export type DragHandlers = {
  draggable: true
  onDragStart: (e: DragEvent) => void
}

/** 树的交互上下文（FolderTree 持有、递归层消费） */
export interface TreeCtx {
  kind: FolderOwnerKind
  ownerId: number
  /** 展开的文件夹 subpath 集合 */
  open: Set<string>
  toggle: (subpath: string) => void
  /** 正在新建子夹的父目录（null = 无；'' = 绑定根） */
  creatingIn: string | null
  setCreatingIn: (subpath: string | null) => void
  /** 正在重命名的条目（subpath 定位） */
  renaming: { subpath: string; name: string } | null
  setRenaming: (v: { subpath: string; name: string } | null) => void
  /** 正在确认删除的条目 */
  deleting: { subpath: string; name: string } | null
  setDeleting: (v: { subpath: string; name: string } | null) => void
  /** 拖拽悬停高亮的 subpath（'' = 绑定根，null = 无） */
  dropOn: string | null
  /** 文件夹行作为投放目标（上传到此目录；isOpen=false 时投放前先展开）；
   *  保留阶段 0 的 contains(relatedTarget) 拖拽高亮判定 */
  folderDropProps: (subpath: string, isOpen: boolean) => DropHandlers
  /** 文件夹行拖为 AI 的「目录引用」 */
  folderDragProps: (entry: { subpath: string; name: string }) => DragHandlers
  /** 文件行拖为 AI 的「文件引用」 */
  fileDragProps: (entry: { subpath: string; name: string }) => DragHandlers
  /** 右键打开上下文菜单 */
  openMenu: (e: MouseEvent, entry: { subpath: string; name: string; isFolder: boolean }) => void
  /** 传入时文件行 hover 显「AI 审查」按钮（非诉详情页的合同回审入口；不传则无此按钮） */
  onReviewFile?: (f: { subpath: string; name: string }) => void
  /** 点文件行时的回调；不传则由行自己下载（兼容未接预览的页面） */
  onOpenFile?: (f: { subpath: string; name: string; size?: number; modified_at?: string }) => void
  /** 当前正在预览的 subpath——列表行据此高亮（让你知道「看的就是这份」） */
  selectedSubpath?: string | null
}

/**
 * 树内条目被改名 / 删除（成功之后）。
 *
 * 为什么必须往上报：详情页可能正开着这个文件——画布还指着旧路径，
 * 标题还是旧名字，保存直接 404，而界面上一切照旧（看起来「还在」）。
 */
export type FolderEntryMutation =
  | { type: 'rename'; kind: FolderOwnerKind; ownerId: number; from: string; to: string }
  | { type: 'delete'; kind: FolderOwnerKind; ownerId: number; subpath: string }

/** 管理动作（FolderTree 的 mutations 下发） */
export interface NodeActions {
  mkdir: (p: { subpath: string; name: string }) => void
  rename: (p: { subpath: string; name: string }) => void
  upload: (subpath: string, files: File[]) => void
  deleteEntry: (subpath: string) => void
}
