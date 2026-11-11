import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { errMessage } from '@/lib/errors'
import { useDeletePack, useJudgePack } from '../hooks/use-inbox'
import { PACK_LEAVE_REMOVAL_MS } from '../constants'
import type { InboxMessage } from '../types'

type JudgeTarget = 'done' | 'filed'
type LeaveDir = 'left' | 'right'

/**
 * DeskPage 的「判决 / 删除」动作状态簇：卡片离场动画的 leaving 标记、归案与
 * 归档动作（含防重入与定时清理），以及待确认删除目标的确认动作。
 *
 * 为什么成簇住在这里：leaving 不只是动画标记，它同时是 judge 的重入守卫，
 * 又决定删除/归案后多久把卡片从列表刷走（列表过滤在页面侧读它）。这几个
 * 定时器必须和发起它们的动作住在一起，否则清理逻辑会散到两处。
 */
export function useDeskJudge({
  deleteTarget,
  onDeleted,
}: {
  /** 待确认删除的材料包；为 null 时确认动作是 no-op */
  deleteTarget: InboxMessage | null
  /** 删除成功后关掉确认框 */
  onDeleted: () => void
}) {
  const judgePack = useJudgePack()
  const deletePack = useDeletePack()

  const [leaving, setLeaving] = useState<Record<number, LeaveDir>>({})
  const leaveTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set())

  // 卸载时清掉所有离场清理定时器，避免卸载后仍 setState
  useEffect(() => {
    const timers = leaveTimersRef.current
    return () => {
      timers.forEach((t) => window.clearTimeout(t))
      timers.clear()
    }
  }, [])

  // 离场动画后移除 leaving 标记（并把卡片从当前列表刷走）
  const judge = useCallback(
    async (pack: { id: number }, target: JudgeTarget) => {
      if (leaving[pack.id]) return
      setLeaving((prev) => ({
        ...prev,
        [pack.id]: target === 'done' ? 'right' : 'left',
      }))
      try {
        await judgePack.mutateAsync({ id: pack.id, status: target })
        toast(target === 'done' ? '已归案' : '已归档留痕，未建案')
      } catch (e) {
        toast.error(errMessage(e, '状态更新失败，请重试'))
      }
      const t = setTimeout(() => {
        leaveTimersRef.current.delete(t)
        setLeaving((prev) => {
          const n = { ...prev }
          delete n[pack.id]
          return n
        })
      }, PACK_LEAVE_REMOVAL_MS)
      leaveTimersRef.current.add(t)
    },
    [judgePack, leaving],
  )

  // judge 是 async（返回 Promise）；键盘导航 / 弹窗回调期望 void 返回，
  // 统一包一层 fire-and-forget（内部 busy/leaving 守卫防重入，无需等待结果）
  const judgeVoid = useCallback(
    (pack: { id: number }, target: JudgeTarget) => {
      void judge(pack, target)
    },
    [judge],
  )

  // 「不接」回调稳定化：内联箭头会透传到 PackCard 打穿 memo
  const rejectPack = useCallback(
    (p: InboxMessage) => {
      void judge(p, 'filed')
    },
    [judge],
  )

  const confirmDelete = useCallback(() => {
    const p = deleteTarget
    if (!p) return
    deletePack
      .mutateAsync(p.id)
      .then(() => {
        toast(`${p.subject} 已删除`)
        onDeleted()
      })
      .catch((e) => toast.error(errMessage(e, '删除失败，请重试')))
  }, [deleteTarget, deletePack, onDeleted])

  return {
    leaving,
    judge,
    judgeVoid,
    rejectPack,
    confirmDelete,
    deleting: deletePack.isPending,
  }
}
