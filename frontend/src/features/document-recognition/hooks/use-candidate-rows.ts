import { useMemo, useState, type Dispatch, type SetStateAction } from 'react'

import { rowsFromTask, type CandidateRow } from '../domain'
import type { TaskOut } from '../types'

/** 用户可在行内改动的字段：这些编辑必须压过服务端快照，否则会被刷新静默吞掉 */
const EDITABLE_FIELDS = [
  'checked',
  'dueLocal',
  'reminderType',
  'label',
  'content',
] as const satisfies readonly (keyof CandidateRow)[]

/**
 * 候选行状态：base 行由任务候选签名驱动（绑定刷新不冲掉本地编辑，
 * 仅候选状态变化时重建），overrides 叠加行内编辑；签名或文字输入变化时清空。
 *
 * 但「清空」不能连用户的行内编辑一起清：候选签名一变（比如在别处忽略了一条、
 * 或绑定案件后 refresh 拉到新任务）base 行就从最新的 task 整个 rebuild，
 * 若 overrides 同时被清空，用户刚改的 dueLocal / reminderType 会被服务端旧值
 * 顶掉且没有任何提示——用户确认的日期直接变成 AI 猜的那个。所以清空之前
 * 先把上一轮 override 里的**可编辑字段**转存，再与服务端新值 diff：
 * 一致（已经落库）就丢掉，不一致就留下继续盖住。不变量是「用户编辑永远赢」。
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
  // 显式依赖 task（不再 suppress exhaustive-deps）：forceRefresh 换回同签名 task 时基行也要更新
  const baseRows = useMemo(
    () => (isFileMode && task ? rowsFromTask(task) : (textRows ?? [])),
    [isFileMode, task, textRows],
  )
  const [overrides, setOverrides] = useState<Record<string, Partial<CandidateRow>>>({})
  /** 用户是否在当前这批行上动过（文字输入本身被调用方重写成新数组，不能当编辑看的信号） */
  const [edited, setEdited] = useState(false)

  const [prevSignature, setPrevSignature] = useState(candidateSignature)
  const [prevTextRows, setPrevTextRows] = useState(textRows)
  if (candidateSignature !== prevSignature || textRows !== prevTextRows) {
    // 渲染期对齐（不是 effect）：否则会先渲染一帧「服务端旧值 + 空 overrides」，
    // 用户在这一帧点确认写进去的就是被回滚的日期
    setPrevSignature(candidateSignature)
    setPrevTextRows(textRows)
    const carried = edited ? carryEdits(overrides, baseRows) : {}
    if (!sameOverrides(carried, overrides)) setOverrides(carried)
    if (edited) setEdited(false)
  }

  const rows = useMemo(
    () => baseRows.map((r) => (overrides[r.key] ? { ...r, ...overrides[r.key] } : r)),
    [baseRows, overrides],
  )
  return { rows, setOverrides: markEdited(setOverrides, setEdited) }
}

/** 把已生效的编辑从旧 overrides 里挑出来，只保留与服务端新值不一致的字段 */
function carryEdits(
  overrides: Record<string, Partial<CandidateRow>>,
  baseRows: CandidateRow[],
): Record<string, Partial<CandidateRow>> {
  const carried: Record<string, Partial<CandidateRow>> = {}
  for (const row of baseRows) {
    const edit = overrides[row.key]
    if (!edit) continue
    const kept: Partial<CandidateRow> = {}
    for (const field of EDITABLE_FIELDS) {
      const value = edit[field]
      if (value !== undefined && value !== row[field]) Object.assign(kept, { [field]: value })
    }
    if (Object.keys(kept).length > 0) carried[row.key] = kept
  }
  return carried
}

function sameOverrides(
  a: Record<string, Partial<CandidateRow>>,
  b: Record<string, Partial<CandidateRow>>,
): boolean {
  const aKeys = Object.keys(a)
  if (aKeys.length !== Object.keys(b).length) return false
  return aKeys.every((key) => {
    const left = a[key] as Record<string, unknown>
    const right = b[key] as Record<string, unknown> | undefined
    if (!right) return false
    const leftKeys = Object.keys(left)
    return (
      leftKeys.length === Object.keys(right).length &&
      leftKeys.every((field) => left[field] === right[field])
    )
  })
}

/** 包一层 setOverrides：任何写入同时置 edited，供上面的快照切换判断 */
function markEdited(
  setOverrides: Dispatch<SetStateAction<Record<string, Partial<CandidateRow>>>>,
  setEdited: Dispatch<SetStateAction<boolean>>,
): Dispatch<SetStateAction<Record<string, Partial<CandidateRow>>>> {
  return (action) => {
    setEdited(true)
    setOverrides(action)
  }
}
