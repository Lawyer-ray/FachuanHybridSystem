import type { MouseEvent } from 'react'

import type { FolderOwnerKind } from '../../api'

/** 绑定文件夹树的共享类型与小工具（与组件分开，满足 react-refresh 仅导出组件的约束）。 */

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
  /** 拖拽悬停高亮的文件夹 subpath */
  dropOn: string | null
  setDropOn: (subpath: string | null) => void
  /** 右键打开上下文菜单 */
  openMenu: (e: MouseEvent, entry: { subpath: string; name: string; isFolder: boolean }) => void
  /** 传入时文件行 hover 显「AI 审查」按钮（非诉详情页的合同回审入口；不传则无此按钮） */
  onReviewFile?: (f: { subpath: string; name: string }) => void
}

/** 管理动作（FolderTree 的 mutations 下发） */
export interface NodeActions {
  mkdir: (p: { subpath: string; name: string }) => void
  rename: (p: { subpath: string; name: string }) => void
  upload: (subpath: string, files: File[]) => void
  deleteEntry: (subpath: string) => void
}

/** 文件大小短格式（B / KB / MB） */
export function fmtSize(n: number): string {
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return Math.round(n / 1024) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}
