/**
 * 审批与状态展示口径：倒计时窗口、离线待审卡映射、任务态徽标、工具参数预览。
 *
 * 倒计时窗口常量是**与后端同步的契约**（backend/apps/agent/…/approval.py 的
 * DEFAULT/CRITICAL/OFFLINE），改一处必须同时改后端——所以三者必须同文件，
 * 且不允许任何调用方自己写死秒数。
 */

import type { Tone } from '@/components/shared/status-badge'

import type { PendingApproval, PendingApprovalItem } from '../types'

/* ── 审批倒计时口径（与后端 approval.py 的 DEFAULT/CRITICAL/OFFLINE 常量同步）──
 * 在线：高。三百秒；紧急九百秒（值得多想一会儿）；离线挂起：两小时
 * （后台任务无人可问时 pending 挂起，用户回来处理）。
 */
export const APPROVAL_WINDOW_S = 300
export const APPROVAL_CRITICAL_WINDOW_S = 900
export const APPROVAL_OFFLINE_WINDOW_S = 7200

/** 审批等待上限（秒）：离线 7200；紧急 900；其余 300 */
export function approvalWindowSec(riskLevel?: string, offline?: boolean): number {
  if (offline) return APPROVAL_OFFLINE_WINDOW_S
  return riskLevel === 'critical' ? APPROVAL_CRITICAL_WINDOW_S : APPROVAL_WINDOW_S
}

/** 离线待审批列表项 → 审批卡模型（倒计时按服务端 created_at 起算，窗口 7200s） */
export function pendingItemToApproval(item: PendingApprovalItem): PendingApproval {
  return {
    approvalId: item.approval_id,
    toolName: item.tool_name,
    toolArgs: item.tool_args ?? {},
    message: '',
    receivedAt: new Date(item.created_at).getTime() || Date.now(),
    riskLevel: item.risk_level,
    offline: true,
  }
}

/**
 * 离线待审批列表项是否已超出等待窗口（服务端懒清理之外的客户端兜底）。
 * 坏日期（NaN/非法字符串）按未超期处理：宁多留一张卡也不误杀。
 */
export function isExpiredOfflineItem(item: PendingApprovalItem, now = Date.now()): boolean {
  const created = new Date(item.created_at).getTime()
  return Number.isFinite(created) && now - created > APPROVAL_OFFLINE_WINDOW_S * 1000
}

/** 审批卡上工具参数的短预览（卡上只放一行，详情看 args JSON） */
export function previewToolArgs(args: Record<string, unknown> | undefined, limit = 160): string {
  if (!args || Object.keys(args).length === 0) return ''
  try {
    const text = JSON.stringify(args)
    return text.length > limit ? `${text.slice(0, limit)}…` : text
  } catch {
    return ''
  }
}

/**
 * 任务式会话状态 → 侧边栏徽标（label + 语义色档）；非任务态返回 null。
 *
 * 返回 Tone 而非硬编码 class：之前写的是 tailwind 原始色（amber/blue/emerald），
 * 淡色主题下可读、暗色下与其它状态色不一致；统一走 StatusBadge 的 --status-* 令牌后，
 * 同一「排队/运行/完成」语义在历史列表、设置页也是同一档颜色。
 */
export function taskBadge(state: string | undefined): { label: string; tone: Tone } | null {
  switch (state) {
    case 'queued':
      return { label: '排队中', tone: 'yellow' }
    case 'running':
      return { label: '运行中', tone: 'blue' }
    case 'succeeded':
      return { label: '已完成', tone: 'green' }
    case 'failed':
      return { label: '失败', tone: 'red' }
    case 'cancelled':
      return { label: '已取消', tone: 'neutral' }
    default:
      return null
  }
}
