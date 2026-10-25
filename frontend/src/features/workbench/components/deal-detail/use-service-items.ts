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
      .map<ServiceItem>(({ kid, date, title }) => ({
        date,
        kind: '办案',
        title,
        // 目录原名带编号与日期，排查时有用（律师改过名字也能对上）
        detail: kid.name,
        subpath: kid.subpath,
        // 完成状态暂以「有没有日期」判断：有计划日期的视为已发生。
        // 真正的交付状态需要事项层有文件才可靠，见下方 note。
        status: date ? 'done' : 'todo',
      }))
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
