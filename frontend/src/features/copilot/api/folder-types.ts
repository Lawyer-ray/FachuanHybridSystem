/**
 * 绑定文件夹浏览的返回契约（合同 / 案件两个端点同形）。
 *
 * 从 `api/folders.ts` 拆出：那个文件带候选缓存（有状态），返回契约不与取数
 * 逻辑混在一起；`api.ts` re-export 回既有 import 路径（`from '../api'`）。
 */

/** 合同绑定文件夹的某一层条目（目录树懒加载数据源，非递归） */
export interface FolderEntries {
  browsable: boolean
  // 后端 `CaseFolderEntriesResponseSchema` 里是可选且可空：失败态才带 message，成功态整个字段缺失。
  // 手抄成必填会让「后端改名/去字段」不再被 tsc 捕获（审计 P05-100）。
  message?: string | null
  path_display: string
  subpath: string
  parent_subpath: string
  folders: { name: string; subpath: string }[]
  files: { name: string; subpath: string; size: number; modified_at: string }[]
}
