import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'

import { DEFAULT_SYNC_WINDOW_DAYS, INBOX_LIST_KEY, listInbox, listSources, syncAllSources, syncSource } from '../api'
import type { SyncWindowDays } from '../api'
import { INBOX_SYNC_SPEC } from '../constants'
import type { InboxSourceFilter } from '../types'

/**
 * 收件箱同步按钮的状态机。
 *
 * 语义是「同步**当前筛选档位**对应的来源」——idle → syncing → 刷新列表 → idle。
 *
 * ## 为什么必须轮询到完成，而不是 toast 完事
 *
 * 这是**同步**按钮，不是**提交任务**按钮。用户点它的心理预期是「我马上要看到
 * 新邮件」。后端是纯异步的（submit_task 之后立刻返回），若只转 3 秒就提示已提交，
 * 列表不会有任何变化，用户会以为坏了、再点一次，制造重复任务。
 *
 * ## 为什么用 last_sync_at 而不是 last_sync_status 判断完成
 *
 * 后端的 SyncStatus 只有 pending/success/failed，**没有 running**：任务提交后
 * 状态仍是上一次的 success，跑完还是 success，前端无法区分「还没开始」和「已完成」。
 * 因此这里记录点击时刻的 last_sync_at 快照，轮询到它变化即判定完成。
 *
 * ## 为什么有 60 秒上限
 *
 * Playwright 类来源（一张网）后端超时给到 1800s。前端不能无限转圈——用户会以为
 * 卡死。到点停止转圈并提示仍在后台进行，让用户自己决定要不要稍后刷新。
 */

/** 轮询间隔：同步通常是秒级到分钟级，2 秒一次的密度对后端无压力 */
const POLL_INTERVAL_MS = 2_000
/** 轮询上限：超过就停止转圈，按「仍在后台进行」处理 */
const POLL_TIMEOUT_MS = 60_000

export type SyncState = 'idle' | 'syncing' | 'background'

export interface SyncResult {
  state: SyncState
  /** 该档位是否可同步（材料包为 false） */
  enabled: boolean
  /** 置灰原因 */
  disabledReason?: string
  /** 本次同步后新增的消息条数；未完成或为 0 时是 null */
  newCount: number | null
  /** 触发同步；档位不可同步时为空操作。days 省略时用默认窗口（3 天） */
  run: (days?: SyncWindowDays) => void
  /** 最近一次同步用的窗口天数，用于在按钮上回显「同步邮箱 · 3天」 */
  lastWindowDays: SyncWindowDays
}

/** 从来源列表里挑出本次要同步的目标 id */
function resolveTargetIds(
  sources: { id: number; source_type: string }[],
  target: readonly string[] | 'all',
): number[] {
  if (target === 'all') return sources.map((s) => s.id)
  const wanted = new Set(target)
  return sources.filter((s) => wanted.has(s.source_type)).map((s) => s.id)
}

export function useSyncSources(source: InboxSourceFilter): SyncResult {
  const qc = useQueryClient()
  const spec = INBOX_SYNC_SPEC[source]

  const [state, setState] = useState<SyncState>('idle')
  const [newCount, setNewCount] = useState<number | null>(null)
  const [lastWindowDays, setLastWindowDays] = useState<SyncWindowDays>(DEFAULT_SYNC_WINDOW_DAYS)

  // state 更新是异步的，重复点击要用同步的 ref 拦
  const runningRef = useRef(false)

  // 先收窄 target：后面闭包里 TS 才能确定它不是 null
  const target = spec.target

  const run = useCallback(
    (days: SyncWindowDays = DEFAULT_SYNC_WINDOW_DAYS) => {
    if (!target || runningRef.current) return
    runningRef.current = true
    setState('syncing')
    setNewCount(null)
    setLastWindowDays(days)

    void (async () => {
      try {
        // 1) 记快照 + 记录同步前的消息总数（用于算新增）
        const beforeSources = await listSources()
        const beforeRows = await listInbox({})
        const baseline = new Map(beforeSources.map((s) => [s.id, s.last_sync_at]))

        // 2) 提交同步任务
        if (target === 'all') {
          await syncAllSources(days)
        } else {
          const ids = resolveTargetIds(beforeSources, target)
          if (ids.length === 0) {
            // 该档位下没有任何来源：不进入后台态，直接回到 idle
            setState('idle')
            return
          }
          await Promise.all(ids.map((id) => syncSource(id, days)))
        }

        // 3) 轮询到 last_sync_at 变化（或超时）
        const startedAt = Date.now()
        for (;;) {
          await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
          const now = await listSources()
          const relevant = now.filter((s) => baseline.has(s.id))
          const allDone = relevant.length > 0 && relevant.every((s) => s.last_sync_at !== baseline.get(s.id))

          if (allDone) break
          if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
            setState('background')
            return
          }
        }

        // 4) 完成后刷新列表并算出新增条数
        const afterRows = await listInbox({})
        await qc.invalidateQueries({ queryKey: INBOX_LIST_KEY })
        const added = afterRows.length - beforeRows.length
        setNewCount(added > 0 ? added : null)
        setState('idle')
      } catch {
        // 请求失败：回到 idle，错误提示由全局错误处理负责
        setState('idle')
      } finally {
        runningRef.current = false
      }
    })()
  }, [qc, target])

  return {
    state,
    enabled: spec.target !== null,
    disabledReason: spec.disabledReason,
    newCount,
    run,
    lastWindowDays,
  }
}
