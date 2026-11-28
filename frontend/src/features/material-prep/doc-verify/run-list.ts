/**
 * 核对记录列表的**纯函数**：排序、翻页去重、时间文案。
 *
 * 从 `CaseVerifyCard.tsx` 拆出：这三件都是 `VerifyRunOut[] → 视图` 的换算，
 * 与「历史卡怎么取数、怎么分档筛选」无关；放在组件文件里时，读筛选逻辑必须
 * 先穿过去重与时间格式化的实现。
 *
 * 与 `run-display.tsx` 的分工：那边是「一条记录长什么样」，这边是「一页记录怎么排队」。
 */

import { pad2 } from '@/lib/date'

import type { VerifyRunOut } from './api'

/** 时间倒序，与后端 `-created_at,-id` 同口径；`created_at` 解析不出来时退回 id 倒序。 */
export function newestFirst(a: VerifyRunOut, b: VerifyRunOut): number {
  const ta = Date.parse(a.created_at)
  const tb = Date.parse(b.created_at)
  if (Number.isFinite(ta) && Number.isFinite(tb) && ta !== tb) return tb - ta
  return b.id - a.id
}

/**
 * 按 id 去重。翻页期间新核了一条，offset 会整体后移，同一条记录可能在两页都出现；
 * 不去重的话 React key 重复，列表会少渲染或错位。
 */
export function dedupeRuns(runs: VerifyRunOut[]): VerifyRunOut[] {
  const seen = new Set<number>()
  const out: VerifyRunOut[] = []
  for (const run of runs) {
    if (seen.has(run.id)) continue
    seen.add(run.id)
    out.push(run)
  }
  return out
}

/** 核对时间：ISO（可能带时区偏移）→ 本地 "YYYY-MM-DD HH:mm"；解析失败原样返回，不编一个时间出来。 */
export function runTimeText(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return iso
  return `${at.getFullYear()}-${pad2(at.getMonth() + 1)}-${pad2(at.getDate())} ${pad2(at.getHours())}:${pad2(at.getMinutes())}`
}
