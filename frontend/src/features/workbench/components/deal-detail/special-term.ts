/**
 * 非诉的两种工作形态各自的时间骨架（54 号原型的结论：它们的推进方式不同）。
 *
 * **常法顾问**按「哪天做了什么」推进，事项天然散落成流水（ServiceItemStream）;
 * **专项服务**按合同约定的阶段交付——尽调 → 方案 → 起草 → 登记 → 交割，每个阶段
 * 验收几份定稿文书，再按节点收款。阶段本身的结构（树、层级、验收标准）在
 * `special-phase-tree.ts`；本文件只剩「交付物行」的类型与文件名解析。
 *
 * 状态取值两套，别再增加第三套：
 * - `DeliverableState`（本文件）：交付物行的**视图口径**「定稿 / 撰写中 / 待开始」；
 * - `PhaseState`（`special-phase-tree.ts`）：阶段行的「已完成 / 进行中 / 未开始」。
 * 曾经的 `phaseLabel` / `deliverableLabel` / `STATE_LABEL` 是这两套的第二份文案
 * 映射，全仓零引用（真正在用的是 `special-phase-state.ts`），已删。
 */

/** 交付物状态：定稿 / 撰写中 / 待开始 */
export type DeliverableState = 'ok' | 'doing' | 'todo'

export interface Deliverable {
  /** yyyy-mm-dd（解析不出为空串） */
  date: string
  /** 展示名（去扩展名，保留《》书名号） */
  name: string
  /** 版本号，如 v1 / v2；解析不出为 undefined */
  version?: string
  /** 原始文件名（点击预览用） */
  fileName: string
  /** 文件在合同文件夹里的相对路径 */
  subpath: string
  /** 状态：docx 视为可编辑=撰写中（有版本但仍可能改），其余按「已归档」算定稿 */
  state: DeliverableState
  size?: number
}

/** 文件名 → 展示名：去扩展名、去结尾的版本串（版本单独成 chip） */
export function splitVersion(fileName: string): { name: string; version?: string } {
  const stem = fileName.replace(/\.[^.]+$/, '')
  // v1 / V2 / 第3版 / (第3稿) 都收；只吃结尾，正文里的「v」不动
  const m = stem.match(/^(.*?)[\s_\-—]*([vV]\d+|第\s*\d+\s*版|第\s*\d+\s*稿)$/)
  if (!m) return { name: stem.trim() }
  return { name: (m[1] ?? '').trim() || stem.trim(), version: normaliseVersion(m[2] ?? '') }
}

function normaliseVersion(v: string): string {
  const lower = v.toLowerCase().replace(/\s+/g, '')
  if (/^v\d+$/.test(lower)) return lower
  const n = lower.match(/\d+/)
  return n ? 'v' + n[0] : lower
}
