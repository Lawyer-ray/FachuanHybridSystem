import { useCallback, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'

import { getContractStages, listFolderEntries, putContractStages, type FolderOwnerKind } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { buildDeliverables, buildPhases, phaseFromFolder, type FolderKid } from './special-phases'
import { derivePhaseStates } from './special-phase-state'
import {
  flattenTree,
  folderNameOf,
  normalizeTree,
  type PhaseDeliverable,
  type PhaseNode,
} from './special-phase-tree'

/** 编号 + 名称 → 合同文件夹相对路径（与 `folderNameOf` 同一口径） */
/**
 * 把本地树的 `open` 状态搬到新树上（按 key 对齐）。
 *
 * 后端返回的树可能不带 `open`（UI 状态不入库），直接用它会丢掉律师的展开位置。
 * 以本地为准、按 key 逐节点覆盖，结构仍用服务端的最新版本。
 */
function keepOpenState(local: PhaseNode[], remote: PhaseNode[]): PhaseNode[] {
  const openOf = new Map<string, boolean>()
  const walk = (nodes: PhaseNode[]) => {
    nodes.forEach((n) => {
      openOf.set(n.key, n.open)
      walk(n.folders)
    })
  }
  walk(local)
  const apply = (nodes: PhaseNode[]): PhaseNode[] =>
    nodes.map((n) => ({
      ...n,
      open: openOf.get(n.key) ?? n.open,
      folders: apply(n.folders),
    }))
  return apply(remote)
}

/**
 * 专项阶段的数据装配：阶段树（结构化契约）+ 交付物（合同文件夹）。
 *
 * **阶段从哪来**：`GET /contracts/contracts/{id}/stages`（api/stages.ts）。端点
 * 未上线时读失败 → 空树，律师仍可设计阶段（本地 state 跑通 UI，写回失败只提示）。
 *
 * **交付物从哪来**：合同文件夹。阶段即文件夹（`<编号>-<阶段名>/`），阶段目录里的
 * 文件就是实际交付物。这不是过渡方案而是领域事实——律师在系统外改目录后刷新即
 * 同步，右栏「合同文件夹」与左侧阶段树共享同一来源（`folderNameOf`）。
 *
 * **目录读取并行、失败静默**：每级阶段一个 folder-entries 请求（5 个阶段就是 5 个），
 * 取不到（律师还没建该目录 / 端点不可用）就是空态，不报错也不阻塞阶段表。
 */
export function useSpecialPhases(kind: FolderOwnerKind, ownerId: number | null) {
  const stagesQuery = useQuery({
    queryKey: [kind, ownerId ?? 0, 'contract-stages'] as const,
    queryFn: () => getContractStages(ownerId!),
    enabled: ownerId !== null,
    staleTime: 30_000,
    retry: false,
  })

  /** 根层目录：结构化阶段为空时用它兜底（律师可能已经按「序号-阶段名」建好了目录） */
  const rootQuery = useQuery({
    queryKey: workbenchKeys.folderEntriesItem(kind, ownerId ?? 0, ''),
    queryFn: () => listFolderEntries(kind, ownerId!, ''),
    enabled: ownerId !== null,
    staleTime: 30_000,
    retry: false,
  })

  /** 本地阶段树：端点未上线 / 刚设计完还没落库时，页面靠它跑通 */
  const [localTree, setLocalTree] = useState<PhaseNode[] | null>(null)
  const [saving, setSaving] = useState(false)

  const folderPhases = useMemo(
    () => buildPhases((rootQuery.data?.folders ?? []) as FolderKid[]),
    [rootQuery.data],
  )

  const baseTree = useMemo(() => {
    if (localTree) return localTree
    const remote = normalizeTree(stagesQuery.data ?? [])
    // 结构化阶段为空、但文件夹里认得出阶段目录 → 用目录兜底，页面不至于空白
    return remote.length > 0 ? remote : folderPhases.map(phaseFromFolder)
  }, [localTree, stagesQuery.data, folderPhases])

  const dirs = useMemo(
    () => flattenTree(baseTree).map(folderNameOf),
    [baseTree],
  )

  const fileQueries = useQueries({
    queries: dirs.map((subpath) => ({
      queryKey: workbenchKeys.folderEntriesItem(kind, ownerId ?? 0, subpath),
      queryFn: () => listFolderEntries(kind, ownerId!, subpath),
      enabled: ownerId !== null,
      staleTime: 30_000,
      retry: false,
    })),
  })

  const filesByDir = useMemo(() => {
    const map = new Map<string, PhaseDeliverable[]>()
    dirs.forEach((subpath, i) => {
      const files = fileQueries[i]?.data?.files
      if (!files || files.length === 0) return
      map.set(subpath, buildDeliverables(files).map(toPhaseDeliverable))
    })
    return map
  }, [dirs, fileQueries])

  const tree = useMemo(() => derivePhaseStates(mergeFiles(baseTree, dirs, filesByDir)), [baseTree, dirs, filesByDir])

  const refetch = useCallback(() => {
    void stagesQuery.refetch()
    void rootQuery.refetch()
  }, [stagesQuery, rootQuery])

  /**
   * 保存阶段树：先落本地（UI 立即生效，不等网络），再试后端。
   *
   * 后端失败只提示「未保存到服务器」并保留本地改动——端点未上线时若回滚，律师刚
   * 设计好的阶段会凭空消失，比不同步更坏。
   */
  const saveStages = useCallback(
    async (next: PhaseNode[]) => {
      const derived = derivePhaseStates(normalizeTree(next))
      setLocalTree(derived)
      if (ownerId === null) return
      setSaving(true)
      try {
        const saved = await putContractStages(ownerId, derived)
        // 后端返回的树不一定带 `open`（它是 UI 状态）。合并时以本地为准，
        // 否则一次保存会把所有展开行缩回去——表现为「阶段点不开」。
        setLocalTree(saved.length > 0 ? keepOpenState(derived, saved) : derived)
        toast.success(`阶段已保存（${saved.length || derived.length} 个）`)
      } catch (e) {
        toast.error('阶段只保存在本页，未写入服务器', { description: errMessage(e, '合同阶段接口暂不可用') })
      } finally {
        setSaving(false)
      }
    },
    [ownerId],
  )

  /**
   * 纯 UI 改动（展开 / 折叠）：**只落本地，不发请求**。
   *
   * 之前折叠也走 saveStages——每点一下行就发一次 PUT，而且后端返回的树会把
   * `open` 洗掉（重绘后全收起，看上去就是「点不开」）。展开态是律师眼下的浏览
   * 位置，不是业务数据，没有落库的理由。
   */
  const setTreeLocal = useCallback((next: PhaseNode[]) => {
    setLocalTree(derivePhaseStates(normalizeTree(next)))
  }, [])

  return {
    tree,
    /** 阶段接口读失败的原因（页面据此提示「接口暂不可用，改动仅在本页」） */
    stagesError: stagesQuery.error ? errMessage(stagesQuery.error, '合同阶段接口暂不可用') : null,
    isLoading: stagesQuery.isLoading || rootQuery.isLoading,
    saving,
    saveStages,
    /** 只改本地（展开/折叠），不落库 */
    setTreeLocal,
    refetch,
  }
}

/**
 * 把读到的实际交付物合进对应阶段。
 *
 * 实际文件优先于计划项：同名计划项被真实文件顶替，避免「计划了 3 份、实际交了
 * 1 份」在表里出现两行同名。
 */
function mergeFiles(tree: PhaseNode[], dirs: string[], filesByDir: Map<string, PhaseDeliverable[]>): PhaseNode[] {
  const dirOf = new Map(flattenTree(tree).map((item, i) => [item.node.key, dirs[i]]))
  const patch = (n: PhaseNode): PhaseNode => {
    const dir = dirOf.get(n.key)
    const real = dir ? (filesByDir.get(dir) ?? []) : []
    const folders = n.folders.map(patch)
    if (real.length === 0) return { ...n, folders }
    const realNames = new Set(real.map((d) => d.name))
    return { ...n, folders, deliverables: [...real, ...n.deliverables.filter((d) => !realNames.has(d.name))] }
  }
  return tree.map(patch)
}

/** 文件夹文件 → 阶段交付物行（docx 视为可编辑=撰写中，其余落盘即定稿） */
function toPhaseDeliverable(f: {
  name: string
  subpath: string
  version?: string
  date: string
  state: 'ok' | 'doing' | 'todo'
}): PhaseDeliverable {
  return {
    id: `file:${f.subpath}`,
    date: f.date,
    name: f.name,
    version: f.version ?? '',
    state: f.state,
    subpath: f.subpath,
    planned: false,
  }
}
