/**
 * store slice：审批卡（加载合并 / 决策 / 失效清理）。
 *
 * 离线待审（后台任务产生、无人在线）走同一份 approvals 数组，靠 `offline`
 * 区分倒计时口径；超窗项由服务端懒清理 + 这里按 APPROVAL_OFFLINE_WINDOW_S 双保险。
 */

import * as copilotApi from '../api'
import { APPROVAL_OFFLINE_WINDOW_S, isExpiredOfflineItem, pendingItemToApproval } from '../domain'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

export type ApprovalSlice = Pick<CopilotState, 'decide' | 'loadPendingApprovals' | 'dismissApproval'>

export const createApprovalSlice: Slice<ApprovalSlice> = (set) => ({
  decide: async (approvalId, approved, reason = '') => {
    set((s) => ({
      approvals: s.approvals.map((a) =>
        a.approvalId === approvalId ? { ...a, decided: approved ? 'approved' : 'rejected' } : a,
      ),
    }))
    try {
      await copilotApi.decideApproval(approvalId, approved, reason)
    } catch {
      // 本地已标记；提交失败不再回滚——服务端 300s 超时按拒绝处理（fail-closed）
    }
  },

  loadPendingApprovals: async () => {
    try {
      const items = await copilotApi.fetchPendingApprovals()
      set((s) => {
        // 只补前端不知道的：已渲染（含已决定）的不动，避免覆盖本地终态；
        // 已超窗的僵尸项不合并（服务端懒清理之外的双保险），并顺带清除旧卡
        const known = new Set(s.approvals.map((a) => a.approvalId))
        const fresh = items
          .filter((i) => !known.has(i.approval_id) && !isExpiredOfflineItem(i))
          .map(pendingItemToApproval)
        const pruned = s.approvals.filter(
          (a) => !(a.offline && !a.decided && Date.now() - a.receivedAt > APPROVAL_OFFLINE_WINDOW_S * 1000),
        )
        if (fresh.length === 0 && pruned.length === s.approvals.length) return s
        return { approvals: [...pruned, ...fresh] }
      })
    } catch {
      // 待审列表拉不到不阻塞主流程（下一流结束/面板重开会再试）
    }
  },

  dismissApproval: (approvalId) => {
    set((s) => ({ approvals: s.approvals.filter((a) => a.approvalId !== approvalId) }))
  },
})
