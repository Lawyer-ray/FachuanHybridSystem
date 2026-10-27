import { useMemo, useState, type DragEvent } from 'react'

import { FOLDER_REF_MIME } from '@/lib/folder-ref'
import type { FolderOwnerKind } from '../../api'
import type { DragHandlers, DropHandlers } from './folder-tree-types'

/** 拖拽携带的绑定引用（目录/文件都走这一个自定义 MIME） */
interface RefPayload {
  kind: FolderOwnerKind
  ownerId: number
  subpath: string
  name: string
  isFolder?: boolean
}

/** 把绑定引用写进拖拽载荷（目录带 isFolder，AI 据此决定先列目录） */
function dragProps(
  ref: { kind: FolderOwnerKind; ownerId: number },
  entry: { subpath: string; name: string; isFolder?: boolean },
): DragHandlers {
  return {
    draggable: true,
    onDragStart: (e) => {
      const payload: RefPayload = { ...ref, subpath: entry.subpath, name: entry.name, isFolder: entry.isFolder }
      e.dataTransfer.setData(FOLDER_REF_MIME, JSON.stringify(payload))
      e.dataTransfer.effectAllowed = 'copyLink'
    },
  }
}

/**
 * 绑定文件夹树的拖放接线（从 FolderTree 拆出）。
 *
 * 三条通道互不混淆：空白区投放 = 上传到绑定根；文件夹行投放 = 上传到该目录；
 * 行拖出去 = AI 的「目录/文件引用」，走自定义 MIME（系统外文件走原生 Files 通道）。
 *
 * `expand` 供「拖到文件夹行」时展开目标：上传目标必须保持可见，见 folderDropProps。
 */
export function useFolderDrop(
  kind: FolderOwnerKind,
  ownerId: number,
  upload: (subpath: string, files: File[]) => void,
  expand: (subpath: string) => void,
) {
  /** 拖拽悬停高亮的 subpath（'' = 绑定根空白区，null = 无） */
  const [dropOn, setDropOn] = useState<string | null>(null)

  // 返回值按依赖稳定化：消费方（FolderTree 的 TreeCtx memo）把它当依赖，
  // 每轮新建对象会让整棵树的 ctx 无谓失效
  return useMemo(
    () => ({
      /** 当前悬停高亮的 subpath（'' = 绑定根，null = 无） */
      dropOn,
      /** 拖到空白区 = 上传到绑定根（行级 drop 已 stopPropagation，不会重复触发） */
      rootDropProps: {
        onDragOver: (e: DragEvent) => {
          e.preventDefault()
          setDropOn('')
        },
        onDragLeave: () => setDropOn((cur) => (cur === '' ? null : cur)),
        onDrop: (e: DragEvent) => {
          e.preventDefault()
          setDropOn(null)
          const files = Array.from(e.dataTransfer.files)
          if (files.length > 0) upload('', files)
        },
      } satisfies DropHandlers,
      /** 文件夹行作为投放目标（isOpen 决定投放前是否需要展开） */
      folderDropProps: (subpath: string, isOpen: boolean): DropHandlers => ({
        onDragOver: (e) => {
          e.preventDefault()
          e.stopPropagation()
          setDropOn(subpath)
        },
        onDragLeave: (e) => {
          // 拖动在行内子元素（箭头/图标/名字/悬浮按钮间）之间移动时，浏览器会从子元素冒泡出
          // dragleave：直接清空会让高亮环每帧闪一次。relatedTarget 仍在行内 = 没真离开。
          // relatedTarget 为 null（拖出浏览器窗口）按真离开处理，否则高亮会卡住。
          const next = e.relatedTarget as Node | null
          if (next && e.currentTarget.contains(next)) return
          setDropOn(null)
        },
        onDrop: (e) => {
          e.preventDefault()
          e.stopPropagation()
          setDropOn(null)
          const files = Array.from(e.dataTransfer.files)
          if (files.length > 0) {
            // 上传目标保持展开（toggle 会把已展开的收起，传完反而看不见）
            if (!isOpen) expand(subpath)
            upload(subpath, files)
          }
        },
      }),
      /** 文件夹行作为拖拽源：AI 的「目录引用」，先列目录内容再按需读文件 */
      folderDragProps: (entry: { subpath: string; name: string }): DragHandlers =>
        dragProps({ kind, ownerId }, { subpath: entry.subpath, name: entry.name, isFolder: true }),
      /** 文件行作为拖拽源：AI 的「文件引用」 */
      fileDragProps: (entry: { subpath: string; name: string }): DragHandlers =>
        dragProps({ kind, ownerId }, entry),
    }),
    [dropOn, kind, ownerId, upload, expand],
  )
}
