import { useEffect, useMemo, useState } from 'react'

import { rowsFromTask, type CandidateRow } from '../domain'
import type { TaskOut } from '../types'

/**
 * 候选行状态：base 行由任务候选签名驱动（绑定刷新不冲掉本地编辑，
 * 仅候选状态变化时重建），overrides 叠加行内编辑；签名或文字输入变化时清空。
 */
export function useCandidateRows(
  isFileMode: boolean,
  task: TaskOut | null,
  textRows: CandidateRow[] | undefined,
) {
  const candidateSignature = useMemo(
    () => (task?.date_candidates ?? []).map((c) => `${c.id}:${c.status}`).join('|'),
    [task],
  )
  const baseRows = useMemo(
    () => (isFileMode && task ? rowsFromTask(task) : (textRows ?? [])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [candidateSignature, textRows, isFileMode],
  )
  const [overrides, setOverrides] = useState<Record<string, Partial<CandidateRow>>>({})
  useEffect(() => setOverrides({}), [candidateSignature, textRows])
  const rows = useMemo(
    () => baseRows.map((r) => (overrides[r.key] ? { ...r, ...overrides[r.key] } : r)),
    [baseRows, overrides],
  )
  return { rows, setOverrides }
}
