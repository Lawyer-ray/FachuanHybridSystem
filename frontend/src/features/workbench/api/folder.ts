import { UPLOAD_TIMEOUT_MS } from '@/lib/api'

import type { CaseFolderBindingInfo, FolderEntries } from '../types'
import { casesApi, contractFolderApi } from './client'

/* ============ 绑定文件夹（案件卡「文件夹视图」+ 右栏「合同文件夹」树共用） ============ */

export type FolderOwnerKind = 'case' | 'contract'

/**
 * 文件夹端点所属的客户端（与 `./client` 里分开的两个实例一一对应）。
 *
 * 合同文件夹与合同 CRUD **前缀不同名**：folder 端点路径是 `/{contract_id}/…`，
 * 挂在 `/contracts` 下 → `/api/v1/contracts/{id}/folder-entries`（没有第二个
 * `contracts` 段）；合同 CRUD 的 `contracts/{id}` 才拼出 `/contracts/contracts/{id}`。
 * 两者曾共用同一个 `/contracts/contracts` 客户端，实测 folder-entries 404。
 */
function folderApi(kind: FolderOwnerKind) {
  return kind === 'case' ? casesApi : contractFolderApi
}

/** 案件文件夹绑定（未绑定时端点返回 null；404 = 案件不存在/无权） */
export async function getCaseFolderBinding(caseId: number): Promise<CaseFolderBindingInfo | null> {
  return casesApi.get(String(caseId) + '/folder-binding').json<CaseFolderBindingInfo | null>()
}

/** 绑定文件夹某一层子项（subpath 为空 = 根；非递归、不含隐藏项） */
export async function listFolderEntries(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
): Promise<FolderEntries> {
  return folderApi(kind)
    .get(String(ownerId) + '/folder-entries', { searchParams: subpath ? { subpath } : {} })
    .json<FolderEntries>()
}

/** 在 subpath（空 = 绑定根）下新建子文件夹；重名/非法名由后端 400 拒 */
export async function createFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string, name: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-mkdir', { json: { subpath, name } })
    .json<{ subpath: string; name: string }>()
}

/** 重命名 subpath 指向的文件/文件夹（name 为新名字） */
export async function renameFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string, name: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-rename', { json: { subpath, name } })
    .json<{ subpath: string; name: string }>()
}

/** 拖拽 / 多文件上传到 subpath 目录（后端同名自动加序号，不覆盖既有文件） */
export async function uploadFolderFiles(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  files: File[],
) {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return folderApi(kind)
    .post(String(ownerId) + '/folder-upload', {
      searchParams: subpath ? { subpath } : {},
      body: form,
      // 与其它模块上传端点同口径：ky 默认 10s，多文件扫描包必被误杀
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<{ saved: Array<{ name: string; subpath: string }> }>()
}

/**
 * 原地保存（覆盖写）。
 *
 * 与 `uploadFolderFiles` 语义**相反**：上传是「不覆盖、同名加序号」，
 * 这里是明确的「覆盖这一份」。加序号就变成另存为，律师看到的还是旧内容。
 *
 * `expectMtime` 做乐观锁：两人同开时后保存的一方会拿到 409，前端提示
 * 「文件已被他人修改」，不静默丢掉前一个人的修改。
 */
export async function saveFolderFile(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  data: Blob,
  expectMtime?: number,
): Promise<{ subpath: string; name: string; size: number; modified_at?: string }> {
  const form = new FormData()
  form.append('file', data, fileNameOf(subpath))
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save', {
      searchParams: {
        subpath,
        ...(expectMtime !== undefined ? { expect_mtime: String(expectMtime) } : {}),
      },
      body: form,
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json()
}

/** 另存为新文件（同目录、同名自动加序号、不动原文件） */
export async function saveFolderFileAs(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  name: string,
  data: Blob,
): Promise<{ subpath: string; name: string; size: number }> {
  const form = new FormData()
  form.append('file', data, name)
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save-as', {
      searchParams: { subpath, name },
      body: form,
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json()
}

function fileNameOf(subpath: string): string {
  return subpath.split('/').pop() || 'document.docx'
}

/** 单文件预览直链（预览前经 withDownloadTicket 换一次性票据再 window.open） */
export function folderFileUrl(kind: FolderOwnerKind, ownerId: number, subpath: string): string {
  // 合同文件夹预览与 folder-entries 同一前缀（`/contracts/{id}/…`，没有第二个 contracts 段）
  const base = kind === 'case' ? '/api/v1/cases' : '/api/v1/contracts'
  return base + '/' + ownerId + '/folder-file?subpath=' + encodeURIComponent(subpath)
}

/**
 * 登记「下一次保存另存为 name」的一次性意图（**不发文件字节**）。
 *
 * 为什么不是「取字节上传」：社区版 OnlyOffice 不暴露 `downloadAs`，编辑后的
 * 字节只存在于 DS 那边，浏览器拿不到。所以前端只能先把「另存为这个名字」的
 * 决定登记到编辑器会话上，再由 `requestSave()` 触发 DS forcesave，后端回调
 * 落盘时按意图写新文件、原文件不动。
 *
 * **只有合同文件夹有该端点**（cases 侧没有 folder-save-as-intent），调用方
 * 必须先按 `kind === 'contract'` 把关——这里不兜底成 no-op，否则「按钮点了没
 * 反应」这种假成功比 404 更难排查。
 *
 * `subpath` 传**已解码一次**的原文（与 `folderFileUrl` 同一口径）：后端回拼
 * source_path 时要按这个口径重新 quote，用来匹配两条编辑器会话。前端若多
 * encode 一次，后端就查不到会话，表现为「明明开着却报未打开」。
 *
 * 返回的 `name` 是后端清洗后的**实际**文件名（可能与入参不同），提示语用它。
 */
export async function registerFolderSaveAsIntent(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  name: string,
): Promise<{ registered: boolean; name: string; subpath: string }> {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save-as-intent', { json: { subpath, name } })
    .json()
}

/** 复制文件/文件夹到目标目录（同名自动加序号，不覆盖） */
export async function copyFolderEntry(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  destSubpath: string,
) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-copy', { json: { subpath, dest_subpath: destSubpath } })
    .json<{ subpath: string; name: string }>()
}

/** 删除 = 移入绑定根下 _已删除/（带时间戳可恢复，非物理删除） */
export async function deleteFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-delete', { json: { subpath } })
    .json<{ subpath: string; name: string }>()
}
