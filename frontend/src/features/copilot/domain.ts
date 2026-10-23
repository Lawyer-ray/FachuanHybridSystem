/**
 * Copilot 纯领域逻辑：SSE 帧解析与历史转录映射。
 * 全部为纯函数，vitest 直接覆盖（node 环境，无 DOM）。
 */

import type { AgentHistoryMessage, AgentStreamEvent, ChatMessage, PendingApproval, PendingApprovalItem } from './types'

let localIdSeed = 0
/** 本地气泡 id（历史消息沿用后端 message_id，流式期间的本地消息用递增 id） */
export function nextLocalId(): string {
  localIdSeed += 1
  return `local-${localIdSeed}`
}

/**
 * 从缓冲区里切出完整的 SSE 帧，返回剩余半截。
 *
 * 线上格式（backend agent_api._sse）：`data: {json}\n\n`。
 * 网络分块与帧边界无关：调用方把每次 chunk 追加进 buffer，再交给本函数；
 * 帧内可能夹 CRLF（容忍），行首无 `data: ` 前缀的行按 SSE 规范忽略。
 */
export function takeSseFrames(buffer: string): { frames: string[]; rest: string } {
  const frames: string[] = []
  let rest = buffer
  let idx = rest.indexOf('\n\n')
  while (idx >= 0) {
    frames.push(rest.slice(0, idx))
    rest = rest.slice(idx + 2)
    idx = rest.indexOf('\n\n')
  }
  return { frames, rest }
}

/** 单帧 → 事件对象；空帧/非 data 帧/坏 JSON 一律返回 null（容错跳过，流不断）。 */
export function parseSseEvent(frame: string): AgentStreamEvent | null {
  const dataLines = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
  if (dataLines.length === 0) return null
  try {
    const parsed = JSON.parse(dataLines.join('\n')) as AgentStreamEvent
    return typeof parsed?.type === 'string' ? parsed : null
  } catch {
    return null
  }
}

/**
 * 历史消息 → 转录气泡。
 * tool 消息后端截断到 8000 字符，前端预览再收一刀；truncated 标记透传。
 */
export function historyToMessages(rows: AgentHistoryMessage[]): ChatMessage[] {
  return rows.map((row) => ({
    id: `db-${row.message_id}`,
    role: row.role,
    content: row.role === 'tool' ? row.content.slice(0, 2000) : row.content,
    toolName: row.tool_name || undefined,
    truncated: row.metadata?.truncated === true || undefined,
  }))
}

/** 工具名去掉 pi 的 mcp__fachuan__ 前缀（纯展示层归一） */
export function shortToolName(name: string | undefined): string {
  if (!name) return '工具'
  const marker = 'mcp__fachuan__'
  const i = name.indexOf(marker)
  return i >= 0 ? name.slice(i + marker.length) : name
}

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

/** 任务式会话状态 → 侧边栏徽标（label + 样式）；非任务态返回 null */
export function taskBadge(state: string | undefined): { label: string; cls: string } | null {
  switch (state) {
    case 'queued':
      return { label: '排队中', cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-400' }
    case 'running':
      return { label: '运行中', cls: 'bg-blue-500/15 text-blue-700 dark:text-blue-400' }
    case 'succeeded':
      return { label: '已完成', cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' }
    case 'failed':
      return { label: '失败', cls: 'bg-destructive/10 text-destructive' }
    case 'cancelled':
      return { label: '已取消', cls: 'bg-secondary text-muted-foreground' }
    default:
      return null
  }
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

/* ── 附件拖拽/选择的前端预检（与服务端白名单/限额同口径，提前拦住少跑一趟）── */

export const ATTACHMENT_EXTENSIONS = ['.pdf', '.docx', '.doc', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.txt']
export const ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024

/** 校验单个文件；不合规返回中文原因，合规返回 null */
export function validateAttachmentFile(file: { name: string; size: number }): string | null {
  const lower = file.name.toLowerCase()
  if (!ATTACHMENT_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `不支持的格式（仅 ${ATTACHMENT_EXTENSIONS.join(' / ')}）`
  }
  if (file.size > ATTACHMENT_MAX_BYTES) {
    return `超过 20MB 限额`
  }
  if (file.size <= 0) {
    return '文件为空'
  }
  return null
}

/** 人类可读的文件大小（chips 展示用） */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${bytes}B`
}

/** 批量分拣：合规附件与拒绝原因（「文件名」+原因） */
export function splitAttachmentFiles(
  files: File[],
): { accepted: File[]; rejected: string[] } {
  const accepted: File[] = []
  const rejected: string[] = []
  for (const file of files) {
    const reason = validateAttachmentFile(file)
    if (reason) rejected.push(`「${file.name}」${reason}`)
    else accepted.push(file)
  }
  return { accepted, rejected }
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

/* ── 输出速度（tok/s）估算 ──────────────────────────────────────────────
 * 后端流式期间只给文本增量；逐 token 计数在每段回答结束的 usage 事件才有。
 * 实时速度用字符启发式估算（展示带 ≈），结束后的总量/平均速度用真实值。
 */

const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]/

/** 字符数 → token 估算：CJK ≈ 0.7 token/字（中文优化分词器的常见区间），其余 ≈ 4 字符/token */
export function estimateTokens(text: string): number {
  let cjk = 0
  let other = 0
  for (const ch of text) {
    if (CJK_RE.test(ch)) cjk += 1
    else other += 1
  }
  return Math.round(cjk * 0.7 + other / 4)
}

/** 采样点 [时间, 累计估算 token]；滑动窗口内每秒 token 数 */
export function tokensPerSecond(samples: Array<[number, number]>, now: number, windowMs = 2000): number {
  if (samples.length < 2) return 0
  const last = samples[samples.length - 1]
  if (last === undefined || now < last[0]) return 0
  const windowStart = now - windowMs
  let baseline: [number, number] | undefined
  for (const s of samples) {
    if (s[0] >= windowStart) {
      baseline = s
      break
    }
  }
  if (baseline === undefined || baseline === last) return 0
  const elapsed = (last[0] - baseline[0]) / 1000
  return elapsed > 0 ? (last[1] - baseline[1]) / elapsed : 0
}

/**
 * 离线待审批列表项是否已超出等待窗口（服务端懒清理之外的客户端兜底）。
 * 坏日期（NaN/非法字符串）按未超期处理：宁多留一张卡也不误杀。
 */
export function isExpiredOfflineItem(item: PendingApprovalItem, now = Date.now()): boolean {
  const created = new Date(item.created_at).getTime()
  return Number.isFinite(created) && now - created > APPROVAL_OFFLINE_WINDOW_S * 1000
}
