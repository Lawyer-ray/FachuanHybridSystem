import { useCallback, useEffect, useMemo, useState } from 'react'
import { listRevisions, resolveRevision } from '../api'
import type { ResolveAction, ReviewRevision } from '../types'

/**
 * 修订清单状态。
 *
 * 决策走「乐观更新 + 失败回滚」：律师点采纳要即时生效（等他等网络会打断
 * 逐条过合同的节奏），失败再把那条退回原状态并保留错误供提示。
 */
export function useRevisions(taskId: string | null) {
  const [items, setItems] = useState<ReviewRevision[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 正在提交决策的修订 id，用于禁用该行按钮防连点 */
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!taskId) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await listRevisions(taskId)
      setItems(data.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载修订清单失败')
    } finally {
      setIsLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    void load()
  }, [load])

  const applyLocal = useCallback((id: string, status: ReviewRevision['status'], reason: string) => {
    setItems((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status, reject_reason: reason } : r)),
    )
  }, [])

  /** 决策：对外返回 void（UI 事件回调直接用），内部自管异步与回滚 */
  const decide = useCallback(
    (revision: ReviewRevision, action: ResolveAction, reason = ''): void => {
      if (!taskId || busyId) return
      void (async () => {
        const prevStatus = revision.status
        const prevReason = revision.reject_reason
      const nextStatus: ReviewRevision['status'] =
        action === 'accept' ? 'accepted' : action === 'reject' ? 'rejected' : 'pending'

        // 乐观更新
        applyLocal(revision.id, nextStatus, action === 'reject' ? reason : '')
        setBusyId(revision.id)
        setError(null)
        try {
          await resolveRevision(taskId, revision.id, action, reason)
        } catch (e) {
          // 回滚：律师看到的状态必须与服务端一致，否则定稿会漏改
          applyLocal(revision.id, prevStatus, prevReason)
          setError(e instanceof Error ? e.message : '保存决策失败')
        } finally {
          setBusyId(null)
        }
      })()
    },
    [taskId, busyId, applyLocal],
  )

  const pendingCount = useMemo(() => items.filter((r) => r.status === 'pending').length, [items])

  return { items, isLoading, error, busyId, pendingCount, reload: load, decide }
}
