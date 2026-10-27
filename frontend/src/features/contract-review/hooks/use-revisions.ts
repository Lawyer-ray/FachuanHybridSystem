import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { errMessage } from '@/lib/errors'

import { listRevisions, resolveRevision } from '../api'
import type { ResolveAction, ReviewRevision, RevisionList } from '../types'

/** 本域 query key 工厂：修订清单按任务缓存（决策后 invalidate 前缀即整域失效） */
export const reviewKeys = {
  revisions: (taskId: string | null) => ['contract-review', 'revisions', taskId] as const,
}

/** 决策提交的入参（variables 同时用于乐观更新与 busyId 推导，见 useRevisions） */
interface DecideVars {
  revisionId: string
  /** 乐观更新与回滚要用到的前后状态：从列表项上抄下来，回滚不依赖当时的 items 闭包 */
  nextStatus: ReviewRevision['status']
  nextReason: string
  prevStatus: ReviewRevision['status']
  prevReason: string
  action: ResolveAction
  reason: string
}

/**
 * 修订清单状态（react-query 版）。
 *
 * 清单读取走 useQuery：拿到 signal 取消（切任务/卸载时旧请求自动作废）、
 * 缓存共享、staleTime 内重返不重复打接口；决策走 useMutation 的
 * 「乐观更新 + 失败回滚 + onSettled 失效」。
 *
 * 为什么不再手写 useState/useEffect：旧实现的 finally 里无条件 setIsLoading(false)，
 * 卸载后仍会 setState；也没有 request 取消——切任务时旧响应能把新任务的清单盖掉。
 *
 * 决策的乐观态直接写进 query 缓存（不走本地 items copy），所以「律师看到的状态」
 * 永远只有一份来源；busyId 由 mutation 的在飞 variables 推导，不额外存一份。
 */
export function useRevisions(taskId: string | null) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: reviewKeys.revisions(taskId),
    queryFn: ({ signal }) => listRevisions(taskId as string, signal),
    enabled: taskId != null,
  })

  const mutation = useMutation({
    mutationFn: ({ revisionId, action, reason }: DecideVars) =>
      resolveRevision(taskId as string, revisionId, action, reason),
    onMutate: async (vars) => {
      // 停掉在途重拉：否则旧响应晚到会把乐观态覆盖回去
      await queryClient.cancelQueries({ queryKey: reviewKeys.revisions(taskId) })
      const snapshot = queryClient.getQueryData<RevisionList>(reviewKeys.revisions(taskId))
      if (snapshot) {
        queryClient.setQueryData<RevisionList>(reviewKeys.revisions(taskId), {
          ...snapshot,
          items: snapshot.items.map((r) =>
            r.id === vars.revisionId
              ? { ...r, status: vars.nextStatus, reject_reason: vars.nextReason }
              : r,
          ),
        })
      }
      return { snapshot }
    },
    onError: (_error, _vars, ctx) => {
      // 回滚：律师看到的状态必须与服务端一致，否则定稿会漏改
      if (ctx?.snapshot) queryClient.setQueryData(reviewKeys.revisions(taskId), ctx.snapshot)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: reviewKeys.revisions(taskId) })
    },
  })

  /** 决策：对外返回 void（UI 事件回调直接用），失败由 onError 回滚、错误经 error 暴露 */
  const decide = (revision: ReviewRevision, action: ResolveAction, reason = ''): void => {
    // 同一时刻只允许一条在提交：防连点导致状态错乱
    if (!taskId || mutation.isPending) return
    const nextStatus: ReviewRevision['status'] =
      action === 'accept' ? 'accepted' : action === 'reject' ? 'rejected' : 'pending'
    mutation.mutate({
      revisionId: revision.id,
      action,
      reason,
      nextStatus,
      nextReason: action === 'reject' ? reason : '',
      prevStatus: revision.status,
      prevReason: revision.reject_reason,
    })
  }

  const items = query.data?.items ?? []
  return {
    items,
    isLoading: taskId != null && query.isPending,
    /** 加载或决策失败的可读文案（null = 无错） */
    error: query.error
      ? errMessage(query.error, '加载修订清单失败')
      : mutation.error
        ? errMessage(mutation.error, '保存决策失败')
        : null,
    /** 正在提交决策的修订 id，用于禁用该行按钮防连点 */
    busyId: mutation.isPending ? (mutation.variables?.revisionId ?? null) : null,
    pendingCount: items.filter((r) => r.status === 'pending').length,
    reload: () => {
      void query.refetch()
    },
    decide,
  }
}
