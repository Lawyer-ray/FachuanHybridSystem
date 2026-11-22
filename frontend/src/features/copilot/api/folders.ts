/**
 * 绑定文件夹浏览（合同/案件目录树的懒加载数据源）。
 *
 * 从 `api.ts` 拆出：这一组端点横跨 contracts / cases 两个后端域，与 copilot 会话
 * 无关，混在会话 CRUD 里会让「改会话接口要翻过目录树代码」。`api.ts` 仍 re-export
 * 这些符号，既有 `from '../api'` 的 import 路径一个都不用改。
 */

import { api } from '@/lib/api'

import type { CopilotScope } from '../types'

/** 合同绑定文件夹的某一层条目（目录树懒加载数据源，非递归） */
export interface FolderEntries {
  browsable: boolean
  message: string | null
  path_display: string
  subpath: string
  parent_subpath: string
  folders: { name: string; subpath: string }[]
  files: { name: string; subpath: string; size: number; modified_at: string }[]
}

/**
 * 合同绑定文件夹某一层。`signal` 供 `@` 引用源的中断（查询词变了就 abort 上一轮）。
 *
 * 契约：`backend/apps/contracts/api/folder_binding_api.py`（路由前缀 `/contracts`
 * 由 `backend/apiSystem/apiSystem/api.py:217` 装配）。
 */
export function fetchContractFolderEntries(contractId: number, subpath = '', signal?: AbortSignal): Promise<FolderEntries> {
  return api
    .get(`contracts/${contractId}/folder-entries`, { searchParams: subpath ? { subpath } : {}, ...(signal ? { signal } : {}) })
    .json<FolderEntries>()
}

/**
 * 案件绑定文件夹某一层（与合同版同形：`CaseFolderEntriesResponseSchema` 与
 * `ContractFolderEntriesOut` 的 folders/files 字段一致）。
 *
 * 契约：`backend/apps/cases/api/case_folder_browse_api.py:54`
 * `GET /{case_id}/folder-entries?subpath=`，前缀 `/cases` 见 api.py:215。
 */
export function fetchCaseFolderEntries(caseId: number, subpath = '', signal?: AbortSignal): Promise<FolderEntries> {
  return api
    .get(`cases/${caseId}/folder-entries`, { searchParams: subpath ? { subpath } : {}, ...(signal ? { signal } : {}) })
    .json<FolderEntries>()
}

/** 业务范围 → 绑定文件夹某一层的条目（案件/合同两个端点同形，合并成一个入口） */
export function fetchScopeFolderEntries(
  scope: CopilotScope,
  subpath = '',
  signal?: AbortSignal,
): Promise<FolderEntries> {
  return scope.origin === 'case'
    ? fetchCaseFolderEntries(scope.refId, subpath, signal)
    : fetchContractFolderEntries(scope.refId, subpath, signal)
}

/** `@` 引用的文书/目录候选源要的行（本前端只用名字/路径/大小） */
export interface ScopeFolderRows {
  browsable: boolean
  message: string | null
  folders: { name: string; subpath: string }[]
  files: { name: string; subpath: string; size: number }[]
}

/** 候选源再下钻几层子目录（多几次请求换「@起诉状」在真实目录结构上真能命中） */
export const SCOPE_SUBDIR_SCAN = 6

/** 绑定文件夹候选的缓存（一个业务范围一份）：候选集不随查询词变化，重复拉没意义 */
const scopeRowsCache = new Map<string, Promise<ScopeFolderRows>>()

/** 测试 / 绑定文件夹变更后用：清掉候选缓存 */
export function clearScopeFolderRowsCache(): void {
  scopeRowsCache.clear()
}

/**
 * 业务范围 → 绑定文件夹里可 @ 的文件与子目录（根层 + 前 {@link SCOPE_SUBDIR_SCAN} 个子目录）。
 *
 * 为什么带下钻：文书几乎不在绑定根（典型是 `1-一审/2-立案材料/起诉状.pdf`），只列根
 * 会让 `@起诉状` 永远搜不到真正想引的东西。结果按 `origin:refId` 缓存——一次打开菜单
 * 只发一轮请求，之后每个查询词都命中缓存。
 *
 * **已知局限**（需后端端点才能根治，见产出）：深层（≥3 级）文书搜不到，且无服务端
 * 递归检索能力；单个子目录读失败只跳过它（换机器/权限变了的目录很常见）。
 *
 * 注：错误不进缓存（用户到详情页重新绑定后重试应该能看到变化）。
 */
export function loadScopeFolderRows(scope: CopilotScope): Promise<ScopeFolderRows> {
  const key = `${scope.origin}:${scope.refId}`
  const cached = scopeRowsCache.get(key)
  if (cached) return cached
  const pending = (async (): Promise<ScopeFolderRows> => {
    const root = await fetchScopeFolderEntries(scope)
    if (!root.browsable) return { browsable: false, message: root.message, folders: [], files: [] }
    const subdirs = root.folders.slice(0, SCOPE_SUBDIR_SCAN)
    const deeper = await Promise.allSettled(subdirs.map((folder) => fetchScopeFolderEntries(scope, folder.subpath)))
    const files = root.files.map(({ name, subpath, size }) => ({ name, subpath, size }))
    for (const result of deeper) {
      if (result.status !== 'fulfilled' || !result.value.browsable) continue
      for (const { name, subpath, size } of result.value.files) files.push({ name, subpath, size })
    }
    return { browsable: true, message: null, folders: root.folders, files }
  })().catch((error: unknown) => {
    scopeRowsCache.delete(key)
    throw error
  })
  scopeRowsCache.set(key, pending)
  return pending
}
