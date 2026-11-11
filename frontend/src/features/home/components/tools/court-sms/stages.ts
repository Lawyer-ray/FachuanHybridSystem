/**
 * 法院短信状态 → 处理阶段的纯映射（后端 CourtSMSStatus 十态，apps/automation/models/court_sms.py）。
 * 拆成纯函数是为了可单测：状态机以后加状态时，改这里 + 测试即可。
 */

/** 弹窗步进器的五个阶段（对齐后端 pipeline：解析→下载→匹配→重命名→通知） */
export const SMS_STAGES = ['解析短信', '下载文书', '匹配案件', '重命名归档', '发送通知'] as const

/** 客户转交通道没有「下载」环节，也不解析短信正文，步进器只展示四步 */
export const MATERIAL_STAGES = ['解析材料', '匹配案件', '重命名归档', '发送通知'] as const

/** 阶段列名称（品牌） */
export type SmsStageSource = 'sms' | 'material'

/** 按来源取步进器标签 */
export function stagesFor(source: SmsStageSource): readonly string[] {
  return source === 'material' ? MATERIAL_STAGES : SMS_STAGES
}

/**
 * 后端状态 → 当前来源下的阶段下标。
 *
 * 两个来源共用同一条后端状态机，但客户转交通道永远不经过 downloading：
 * 若直接用 SMS 下标（downloading=1）会在四步的 MATERIAL_STAGES 里错位，
 * 所以这里做一次「跳不跳下载阶段」的映射。
 */
export function stageIndexFor(status: string, source: SmsStageSource): number {
  const info = smsStageInfo(status)
  if (source === 'sms' || info.stage === 0) return info.stage
  // material：解析(0) → 匹配(1) → 重命名(2) → 通知(3)，下载阶段整体移除
  return Math.max(0, info.stage - 1)
}

/** 把「后端原始阶段下标」换算成当前来源的阶段下标（稳定历史记录 / 兜底展示用） */
export function stageIndexFromRaw(rawStage: number, source: SmsStageSource): number {
  if (source === 'sms') return rawStage
  // material：0 解析保持 0；>=2 的（matching/renaming/notifying）整体左移一位
  return rawStage <= 1 ? 0 : rawStage - 1
}

/** 当前来源下「某状态属于第几步」（失败定位用；逻辑同上） */
export function failedStageFor(status: string, source: SmsStageSource): number | null {
  const info = smsStageInfo(status)
  if (info.failedAt === null) return null
  if (source === 'sms') return info.failedAt
  return stageIndexFromRaw(info.failedAt, source)
}

/** 终态语义：completed 成功收尾；failed/download_failed 失败；manual 即 pending_manual 待人工分配案件 */
export type SmsTerminal = 'completed' | 'failed' | 'manual'

export interface SmsStageInfo {
  /** 当前阶段下标（0-4）；completed 停在 5 表示全部走完 */
  stage: number
  /** 终态；非终态为 null */
  terminal: SmsTerminal | null
  /** 明确知道失败在哪个阶段时给出（download_failed → 下载阶段） */
  failedAt: number | null
}

/** 单个状态的阶段信息；未知状态按「仍在处理、阶段未知」兜底（stage 保守取 0） */
export function smsStageInfo(status: string): SmsStageInfo {
  switch (status) {
    case 'pending':
    case 'parsing':
      return { stage: 0, terminal: null, failedAt: null }
    case 'downloading':
      return { stage: 1, terminal: null, failedAt: null }
    case 'download_failed':
      // 非终态：后端 retry_count<3 时会建 +60s 一次性调度自动重试（状态翻回
      // pending→downloading），继续轮询才能跟着走完；重试用尽后端才置 failed
      return { stage: 1, terminal: null, failedAt: 1 }
    case 'matching':
      return { stage: 2, terminal: null, failedAt: null }
    case 'pending_manual':
      return { stage: 2, terminal: 'manual', failedAt: null }
    case 'renaming':
      return { stage: 3, terminal: null, failedAt: null }
    case 'notifying':
      return { stage: 4, terminal: null, failedAt: null }
    case 'completed':
      return { stage: SMS_STAGES.length, terminal: 'completed', failedAt: null }
    case 'failed':
      // failed 可能发生在任意阶段（错误细节看 error_message），阶段由调用方用观测到的最大阶段兜底
      return { stage: 2, terminal: 'failed', failedAt: null }
    default:
      return { stage: 0, terminal: null, failedAt: null }
  }
}

/** 短信类型的展示名（后端 CourtSMSType） */
export const SMS_TYPE_LABEL: Record<string, string> = {
  document_delivery: '文书送达',
  info_notification: '信息通知',
  filing_notification: '立案通知',
}

/** 状态的展示名（详情区用） */
export const SMS_STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  parsing: '解析中',
  downloading: '下载中',
  download_failed: '下载失败',
  matching: '匹配中',
  pending_manual: '待人工处理',
  renaming: '重命名中',
  notifying: '通知中',
  completed: '已完成',
  failed: '处理失败',
}
