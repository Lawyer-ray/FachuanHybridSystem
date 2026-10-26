import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { listFolderEntries, type FolderOwnerKind } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { parseDatedFolder, pickServiceItems, stripOrderPrefix } from './service-items'
import type { ServiceItem } from './ServiceItemStream'

/**
 * 从合同文件夹里读服务事项（含交付物）。
 *
 * **为什么不另建一张「服务事项」表**：律师每天就在
 * `3-办案/2026.04.27-草拟付款确认书/` 里干活，事项名与日期都写在文件夹名上。
 * 再让他到系统里录一遍是同一件事做两次，且两边一旦不同步就不知道该信哪个。
 *
 * 成本：两次 folder-entries 请求（根 + 事项源目录），都是本地磁盘扫描，
 * 比查一张不存在的表更真实——律师看到的永远是磁盘上的实际状态。
 */
export function useServiceItems(
  kind: FolderOwnerKind,
  ownerId: number | null,
  opts?: {
    /** 用户手动指定的事项源目录（相对路径）；不给则自动识别 */
    sourceSubpath?: string | null
  },
) {
  const source = opts?.sourceSubpath ?? null

  // 根层：用来找「办案」目录
  const roots = useQuery({
    queryKey: [...workbenchKeys.folderEntriesItem(kind, ownerId ?? 0, ''), 'service-roots'],
    queryFn: () => listFolderEntries(kind, ownerId!, ''),
    enabled: ownerId !== null,
    staleTime: 30_000,
    retry: false,
  })

  const rootEntries = useMemo(() => roots.data?.folders ?? [], [roots.data])

  // 事项源目录：手动指定优先，否则按命名约定自动认
  const autoSource = useMemo(() => {
    if (source) return source
    if (rootEntries.length === 0) return null
    // 只认名字，不下探——自动识别只看根层命名（省一次请求）；
    // 认不出时由页面提示用户手动指定，而不是静默扫完全部子目录
    const hit = rootEntries.find((f) => /办案|法律服务|日常事务/.test(stripOrderPrefix(f.name)))
    return hit?.subpath ?? null
  }, [source, rootEntries])

  const itemsQuery = useQuery({
    queryKey: [...workbenchKeys.folderEntriesItem(kind, ownerId ?? 0, autoSource ?? ''), 'service-items'],
    queryFn: () => listFolderEntries(kind, ownerId!, autoSource!),
    enabled: ownerId !== null && autoSource !== null,
    staleTime: 30_000,
    retry: false,
  })

  const items: ServiceItem[] = useMemo(() => {
    if (!autoSource || !itemsQuery.data) return []
    const kids = itemsQuery.data.folders ?? []
    return kids
      .map((kid) => {
        const { date, title } = parseDatedFolder(kid.name)
        return { kid, date, title }
      })
      .sort((a, b) => {
        if (a.date && b.date) return b.date.localeCompare(a.date)
        if (a.date) return -1
        if (b.date) return 1
        return a.title.localeCompare(b.title, 'zh')
      })
      .map<ServiceItem>(({ kid, date, title }) => {
        // 交付状态看事项目录里**有没有文件**（后端在列目录时顺手算了 file_count）：
        // 空目录 = 事情还没产出东西 → 待办/进行中。比「有没有日期」可靠得多——
        // 日期只说明计划过，文件才说明做完了。
        const n = kid.file_count ?? 0
        const status: ServiceItem['status'] = n > 0 ? 'done' : date ? 'doing' : 'todo'
        return {
          date,
          kind: '办案',
          title,
          // 不再重复目录名：日期已在左列完整显示、事项名就在主行，把
          // `2026.06.09-租赁合同` 再贴一行只是把同一信息说两遍。
          // 唯一例外：目录只有日期没有事项名（`2026.06.09-`），此时事项名
          // 回退成原名＝重复了日期，也就不需要再显示。
          detail: undefined,
          subpath: kid.subpath,
          fileCount: n,
          status,
        }
      })
  }, [autoSource, itemsQuery.data])

  return {
    items,
    /** 实际使用的事项源目录（自动识别或手动指定） */
    sourceSubpath: autoSource,
    /** 根层里可选的候选源目录（供页面「换个目录」下拉） */
    candidates: rootEntries,
    isLoading: roots.isLoading || itemsQuery.isLoading,
    error: roots.error ?? itemsQuery.error ?? null,
  }
}

/**
 * `pickServiceItems` 保留给「需要一次请求拿完」的调用方（目前只有测试与
 * 纯函数复用）；页面走上面的 hook，避免一次扫全部子目录。
 */
export { pickServiceItems }
