import { cn } from '@/lib/utils'

/** 状态徽章配色（历史列表通用：成功绿 / 失败红 / 处理中蓝 / 待处理黄） */
export const STATUS_BADGE: Record<string, string> = {
  completed: 'border-status-green/40 bg-status-green-bg text-status-green',
  success: 'border-status-green/40 bg-status-green-bg text-status-green',
  failed: 'border-status-red/40 bg-status-red-bg text-status-red',
  pending: 'border-status-yellow/50 bg-status-yellow-bg text-status-yellow',
  processing: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  converting: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  packing: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
}

export const badgeOf = (status: string) =>
  STATUS_BADGE[status] ?? cn('border-status-blue/40 bg-status-blue-bg text-status-blue')
