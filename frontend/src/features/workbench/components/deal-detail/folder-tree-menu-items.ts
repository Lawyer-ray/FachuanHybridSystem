import type { TreeMenuItem } from './folder-tree-menu'
import type { FolderTreeState } from './use-folder-tree'

/**
 * 右键菜单项由树状态算出（从 use-folder-tree 分出的纯函数）。
 *
 * 「粘贴」是唯一有前置条件的项：目标必须是文件夹，且暂存的源不能就是目标
 * 或目标的祖先（否则会把自己/父目录粘进自己的子树）。复制/重命名/删除恒有。
 */
export function buildFolderMenuItems(state: FolderTreeState): TreeMenuItem[] {
  const { menu, clip, setMenu, setClip, setRenaming, setDeleting, copyTo } = state
  if (!menu) return []
  const close = () => setMenu(null)
  const items: TreeMenuItem[] = []
  const canPaste =
    menu.isFolder && clip && clip.subpath !== menu.subpath && !menu.subpath.startsWith(clip.subpath + '/')
  if (canPaste) {
    items.push({
      label: '粘贴到此文件夹',
      onClick: () => {
        close()
        copyTo(clip.subpath, menu.subpath)
      },
    })
  }
  items.push({
    label: '复制',
    onClick: () => {
      close()
      setClip({ subpath: menu.subpath, name: menu.name })
    },
  })
  items.push({
    label: '重命名',
    onClick: () => {
      close()
      setRenaming({ subpath: menu.subpath, name: menu.name })
    },
  })
  items.push({
    label: '删除',
    danger: true,
    onClick: () => {
      close()
      setDeleting({ subpath: menu.subpath, name: menu.name })
    },
  })
  return items
}
