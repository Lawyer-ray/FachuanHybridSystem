import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'
import type { FolderEntryMutation } from './folder-tree-types'
import {
  copyFolderEntry,
  createFolderEntry,
  deleteFolderEntry,
  listFolderEntries,
  renameFolderEntry,
  uploadFolderFiles,
  type FolderOwnerKind,
} from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'

/**
 * 文件夹树的状态与 mutation 编排（从 FolderTree 拆出：树里「状态机」与
 * 「递归渲染」是两个关注点，混在一个文件里 600 行）。
 *
 * 全部成功静默只刷新、失败才弹 toast（用户口味）；展开集合 open 是唯一
 * 需要跟着 mutation 改写的状态：新建/复制要展开目标、重命名要改写旧
 * subpath（含子树）、删除要连子树一起收起。
 */

interface MenuState {
  x: number
  y: number
  subpath: string
  name: string
  isFolder: boolean
}

/** 展开时才挂载（懒加载）：父层 query 数据已到位才渲染本组件 */
function useLayer(kind: FolderOwnerKind, ownerId: number, subpath: string) {
  return useQuery({
    queryKey: workbenchKeys.folderEntriesItem(kind, ownerId, subpath),
    queryFn: () => listFolderEntries(kind, ownerId, subpath),
    staleTime: 60_000,
    retry: false,
  })
}

/**
 * 某个文件的祖先目录（`1-立案/1-起诉状/a.docx` → `1-立案`、`1-立案/1-起诉状`）。
 *
 * 只取「目录段」，不含文件本身：把文件 subpath 塞进展开集合没有意义（展开的是目录）。
 */
function ancestorsOf(subpath?: string | null): Set<string> {
  const out = new Set<string>()
  if (!subpath) return out
  const segs = subpath.split('/').slice(0, -1)
  let acc = ''
  for (const s of segs) {
    if (!s) continue
    acc = acc ? `${acc}/${s}` : s
    out.add(acc)
  }
  return out
}

/**
 * 树的展开集合。
 *
 * `selectedSubpath` 只在**初次挂载**时用来展开当前文件的祖先链，不能在后续
 * 变更时恢复它——展开态是用户的手势，不能被每次点击重置。
 *
 * **为什么需要它**：详情页打开文档时档案卡会从右栏搬到内容列底部（DealDocLayout
 * 的两种文档态是两个不同的 DOM 位置），树随之重挂一次、展开集合清空——律师刚点开的那份文件就沉进折叠的
 * 三层目录里，连「下一份」都点不到。按选中文件重算祖先链，重挂后看到的就是
 * 自己刚才所在的那一层；没选中文件时仍是一棵收起的树。
 */
export function useFolderTreeState(
  kind: FolderOwnerKind,
  ownerId: number,
  selectedSubpath?: string | null,
  /** 改名/删除成功后往上报：页面据此把「正在预览的那份」关掉，别对着旧路径保存 */
  onEntryMutated?: (e: FolderEntryMutation) => void,
) {
  const qc = useQueryClient()
  const [open, setOpen] = useState<Set<string>>(() => ancestorsOf(selectedSubpath))
  const [creatingIn, setCreatingIn] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<{ subpath: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState<{ subpath: string; name: string } | null>(null)
  const [dropOn, setDropOn] = useState<string | null>(null)
  const [menu, setMenu] = useState<MenuState | null>(null)
  /** 右键「复制」暂存的源（同一棵树内粘贴） */
  const [clip, setClip] = useState<{ subpath: string; name: string } | null>(null)

  const toggle = (subpath: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(subpath)) next.delete(subpath)
      else next.add(subpath)
      return next
    })

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
    onSuccess: (_d, p) => {
      invalidate()
      setRenaming(null)
      // 重命名后旧 subpath 失效：把展开集合里的旧名（含子树）改写到新名，
      // 否则已展开的多层目录会莫名其妙地全部收起
      const parent = p.subpath.includes('/') ? p.subpath.slice(0, p.subpath.lastIndexOf('/') + 1) : ''
      const nextPath = parent + p.name
      setOpen((prev) => {
        const next = new Set<string>()
        for (const k of prev) {
          if (k === p.subpath) next.add(nextPath)
          else if (k.startsWith(p.subpath + '/')) next.add(nextPath + k.slice(p.subpath.length))
          else next.add(k)
        }
        return next
      })
      onEntryMutated?.({ type: 'rename', kind, ownerId, from: p.subpath, to: nextPath })
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
  const copy = useMutation({
    mutationFn: (p: { subpath: string; dest: string }) =>
      copyFolderEntry(kind, ownerId, p.subpath, p.dest),
    onSuccess: (_d, p) => {
      invalidate()
      setOpen((prev) => new Set(prev).add(p.dest))
    },
    onError: (e) => fail(e, '复制'),
  })
  const remove = useMutation({
    mutationFn: (subpath: string) => deleteFolderEntry(kind, ownerId, subpath),
    onSuccess: (_d, subpath) => {
      invalidate()
      setDeleting(null)
      // 删掉的目录若在展开集合里，连同其子树一起收起
      setOpen((prev) => {
        const next = new Set(prev)
        for (const k of next) if (k === subpath || k.startsWith(subpath + '/')) next.delete(k)
        return next
      })
      onEntryMutated?.({ type: 'delete', kind, ownerId, subpath })
    },
    onError: (e) => {
      fail(e, '删除')
      setDeleting(null)
    },
  })

  /** 根层的懒加载 query（TreeContextMenu 之前的 loading / error 分支据此判定） */
  const root = useLayer(kind, ownerId, '')

  return {
    open,
    toggle,
    creatingIn,
    setCreatingIn,
    renaming,
    setRenaming,
    deleting,
    setDeleting,
    dropOn,
    setDropOn,
    menu,
    setMenu,
    clip,
    setClip,
    root,
    mutation: {
      mkdir: (p: { subpath: string; name: string }) => mkdir.mutate(p),
      rename: (p: { subpath: string; name: string }) => rename.mutate(p),
      upload: (subpath: string, files: File[]) => upload.mutate({ subpath, files }),
      deleteEntry: (subpath: string) => remove.mutate(subpath),
    },
    /** 粘贴到目标目录 */
    copyTo: (subpath: string, dest: string) => copy.mutate({ subpath, dest }),
  }
}

export type FolderTreeState = ReturnType<typeof useFolderTreeState>
