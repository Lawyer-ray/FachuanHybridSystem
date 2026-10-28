import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { INBOX_LIST_KEY, convertToPack, listInbox, setReadState, type ListInboxParams } from '../api'
import type { InboxRow } from '../types'

/**
 * 收件箱列表。
 *
 * staleTime 取 15s 而非全站默认：收件箱是「一小时内有几条新消息」的慢数据，
 * 但比 material-prep 的 30s 更短——法院送达看一眼就想确认有没有新的。
 * 切回窗口不重拉（与首页收件箱卡同口径），避免打断正在读的列表滚动位置。
 */
export function useInboxList(params: ListInboxParams) {
  return useQuery({
    queryKey: [...INBOX_LIST_KEY, params],
    queryFn: () => listInbox(params),
    staleTime: 15_000,
    refetchOnWindowFocus: false,
  })
}

/**
 * 标记已读 / 未读（乐观更新列表缓存）。
 *
 * 为什么乐观：点开一条消息就标已读，若等请求回来再改，未读色条会「卡一下才消失」。
 * 失败则回滚——已读态看着小事，但标错了会让律师以为漏看了某条法院文书。
 */
export function useSetReadState() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, read }: { id: number; read: boolean }) => setReadState(id, read),
    onMutate: async ({ id, read }) => {
      // 取消在途的列表请求，否则乐观写入会被慢响应覆盖
      await qc.cancelQueries({ queryKey: INBOX_LIST_KEY })
      const snapshots = qc.getQueriesData<InboxRow[]>({ queryKey: INBOX_LIST_KEY })
      qc.setQueriesData<InboxRow[]>({ queryKey: INBOX_LIST_KEY }, (rows) =>
        rows?.map((r) => (r.id === id ? { ...r, is_read: read, read_at: read ? r.read_at ?? '' : null } : r)),
      )
      return { snapshots }
    },
    onError: (_e, _v, ctx) => {
      ctx?.snapshots?.forEach(([key, data]) => qc.setQueryData(key, data))
    },
  })
}

/**
 * 转材料包。
 *
 * 成功后让收件箱列表与材料预处理列表都失效：前者要把这一行标成「已转」，
 * 后者要能看到新生成的材料包。
 *
 * 这里按 queryKey 前缀 ['inbox'] 失效而非 import material-prep 的 PACKS_KEY：
 * 前端规范禁止 feature 互引内部文件，而 PACKS_KEY 恰是 ['inbox','material-packs']，
 * 与本页的 INBOX_LIST_KEY=['inbox-list'] 共享 'inbox' 前缀。
 */
export function useConvertToPack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => convertToPack(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['inbox'] })
      void qc.invalidateQueries({ queryKey: INBOX_LIST_KEY })
      void qc.invalidateQueries({ queryKey: ['home-inbox'] })
    },
  })
}
