/**
 * 裁决卡的数据源：按 (session, turn) 取一轮评审快照。
 *
 * 为什么不进 store：评审是**只读展示 + 单卡本地采纳状态**，与转录的流式生命周期
 * 无关；放进 store 会多出一份「哪一轮的评审还在内存里」的缓存键，切会话/刷新还得
 * 手动清（B5b 的另一条硬约束就是不改 store 形状）。
 *
 * 404 的处理是这个 hook 的重点：**该轮没有评审是正常态**，整块不渲染，不弹错、
 * 不阻塞对话——评审是影子模式下的附加信息，缺它不能影响律师读答案。
 */

import { useEffect, useState } from 'react'

import { fetchReview } from '../../api'
import { toReviewView, type ReviewView } from '../../domain/fusion'

export function useReview(sessionId: string | null, turn: number | null): ReviewView | null {
  const [review, setReview] = useState<ReviewView | null>(null)

  useEffect(() => {
    if (!sessionId || turn === null) {
      setReview(null)
      return
    }
    let cancelled = false
    fetchReview(sessionId, turn)
      .then((wire) => {
        if (!cancelled) setReview(toReviewView(wire))
      })
      // 404 = 该轮没评审过（正常态）；网络失败同样降级为「没有卡」，不打扰对话
      .catch(() => {
        if (!cancelled) setReview(null)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, turn])

  return review
}
