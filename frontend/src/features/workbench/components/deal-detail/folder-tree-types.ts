import type { DragEvent, MouseEvent } from 'react'

import { formatBytes } from '@/lib/format'
import type { FolderOwnerKind } from '../../api'

/** 绑定文件夹树的共享类型与小工具（与组件分开，满足 react-refresh 仅导出组件的约束）。 */

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
  onOpenFile?: (f: { subpath: string; name: string }) => void
  /** 当前正在预览的 subpath——列表行据此高亮（让你知道「看的就是这份」） */
  selectedSubpath?: string | null
}

/** 管理动作（FolderTree 的 mutations 下发） */
export interface NodeActions {
  mkdir: (p: { subpath: string; name: string }) => void
  rename: (p: { subpath: string; name: string }) => void
  upload: (subpath: string, files: File[]) => void
  deleteEntry: (subpath: string) => void
}

/**
 * 文件大小短格式。
 *
 * 口径统一到 lib/format 的 formatBytes（此前本地那份漏了 GB 档，大文件会显示成
 * 「512000.0 MB」）。这里只保留 fmtSize 这个名字给同目录的 FolderTree /
 * FilePreviewCard，避免改调用点、也避免重命名文件——注意运行时函数放在
 * `*-types.ts` 里本身就是归属问题（该文件只应导出类型，函数应迁出到独立模块）。
 */
export const fmtSize = formatBytes
