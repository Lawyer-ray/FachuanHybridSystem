/**
 * 合同文件夹 → 交付物行 / 阶段骨架的纯函数（与 special-term.ts 同域，放一处便于单测）。
 *
 * 专项阶段的结构化契约在 `special-phase-tree.ts`（树 + 层级 + 验收标准），这里只做
 * 「磁盘事实」这一半：
 * - `buildDeliverables`：某个阶段目录里的文件 → 交付物行（识别版本串、判定定稿/撰写中）；
 * - `buildPhases`：根层目录 → 阶段骨架，仅在合同还没有结构化阶段时给页面兜底内容。
 */

import type { PhaseNode } from './special-phase-tree'
import { splitVersion, type Deliverable, type PhaseState } from './special-term'

/** 认作专项的阶段目录：`<序号>-名称` 或 `日期-名称`，且**不是**发票/邮寄等档案目录 */
const ARCHIVE_DIR = /发票|邮寄|合同|收据|归档|往来|其他|附件/i

/** `2-方案设计` / `3-文件起草` 这类短序号前缀（与 service-items 的 stripOrderPrefix 同口径） */
function stripOrder(name: string): { no: number | null; rest: string } {
  const m = name.match(/^\s*(\d{1,2})\s*[-.、_]\s*(.+)$/)
  if (m) return { no: Number(m[1]), rest: (m[2] ?? '').trim() }
  return { no: null, rest: name.trim() }
}

/** 目录名里的可读日期（`2026.06.05-` / `2026-06-05` / `2026年6月5日`） */
function parseDate(name: string): { date: string; rest: string } {
  const m = name.match(/^\s*(\d{4})[.\-年]\s*(\d{1,2})[.\-月]\s*(\d{1,2})\s*日?\s*[-_.、\s]*\s*(.*)$/)
  if (!m) return { date: '', rest: name }
  const date = `${m[1]}-${String(Number(m[2])).padStart(2, '0')}-${String(Number(m[3])).padStart(2, '0')}`
  return { date, rest: (m[4] || '').trim() }
}

export interface FolderKid {
  name: string
  subpath: string
  file_count?: number
}

/** 根层目录认出的阶段骨架（合同还没有结构化阶段时的兜底内容） */
export interface FolderPhase {
  /** 阶段名（目录名去掉序号与日期） */
  name: string
  /** 阶段目录在合同文件夹中的相对路径 */
  subpath: string
  /** 阶段开始日 yyyy-mm-dd；解析不出为空串 */
  startDate: string
  /** 目录里已有文件数 */
  fileCount: number
  state: PhaseState
}

/**
 * 根层目录 → 阶段骨架。
 *
 * 排序按目录名开头的序号（律师自己的排序习惯），认不出序号时退回名称序；日期只用来
 * 标注「阶段开始日」，不参与排序——律师排阶段看的是序号。
 *
 * 状态判定：有文件=已完成；第一个空目录=进行中；其后=未开始。这套判定只用磁盘事实，
 * 不猜合同工期。
 */
export function buildPhases(folders: FolderKid[]): FolderPhase[] {
  const rows = folders
    .map((f) => {
      const { no, rest } = stripOrder(f.name)
      const { date, rest: title } = parseDate(rest)
      return { f, no, date, title }
    })
    // 只认有实际名字的目录；纯日期目录（`2026.06.05`）不是阶段，是事项
    .filter((r) => r.title.length > 0 && !ARCHIVE_DIR.test(r.title))

  if (rows.length === 0) return []

  // 序号优先：有号的全排前面按号升序，没号的按名称序接在后面
  rows.sort((a, b) => {
    if (a.no !== null && b.no !== null) return a.no - b.no
    if (a.no !== null) return -1
    if (b.no !== null) return 1
    return a.title.localeCompare(b.title, 'zh')
  })

  const counts = rows.map((r) => r.f.file_count ?? 0)
  const lastFilled = counts.reduce((acc, n, i) => (n > 0 ? i : acc), -1)

  return rows.map<FolderPhase>((r, i) => {
    const fileCount = counts[i] ?? 0
    const state: PhaseState = fileCount > 0 ? 'ok' : i === lastFilled + 1 ? 'doing' : 'todo'
    return { name: r.title, subpath: r.f.subpath, startDate: r.date, fileCount, state }
  })
}

/** 目录口径的阶段骨架 → 阶段树节点（结构化契约未上线时页面仍有内容） */
export function phaseFromFolder(p: FolderPhase): PhaseNode {
  return {
    key: `folder:${p.subpath}`,
    name: p.name,
    acceptance: '',
    open: p.state === 'doing',
    startDate: p.startDate,
    folders: [],
    deliverables: [],
  }
}

/** 阶段目录下的文件 → 交付物行（按版本自然序、再按日期倒序） */
export function buildDeliverables(
  files: Array<{ name: string; subpath: string; size?: number; modified_at?: string }>,
): Deliverable[] {
  return files
    .filter((f) => !/^\./.test(f.name))
    .map<Deliverable>((f) => {
      const { name, version } = splitVersion(f.name)
      const date = (f.modified_at ?? '').slice(0, 10)
      const editable = /\.docx$/i.test(f.name)
      return {
        date,
        name,
        version,
        fileName: f.name,
        subpath: f.subpath,
        // docx 是「还能改的活稿」→ 撰写中；pdf/图片一旦落盘就是发出去的定稿
        state: editable ? 'doing' : 'ok',
        size: f.size,
      }
    })
    .sort((a, b) => {
      // 同一份文书的多版本聚在一起：先按文书名，版本高的在前
      const byName = a.name.localeCompare(b.name, 'zh')
      if (byName !== 0) return byName
      return (b.version ?? '').localeCompare(a.version ?? '', 'en', { numeric: true })
    })
}
