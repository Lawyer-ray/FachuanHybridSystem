/**
 * Copilot 纯领域逻辑：SSE 帧解析与历史转录映射。
 * 全部为纯函数，vitest 直接覆盖（node 环境，无 DOM）。
 */

import type { AgentHistoryMessage, AgentSession, AgentStreamEvent, ChatMessage, PendingApproval, PendingApprovalItem, SentRefMeta, SessionGroup } from './types'

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
/**
 * 引用块行（发送时由 outgoing 拼入消息）：
 * - 文件（落了附件）：`[已引用文件：name (attachment_id=…, contract_id=N, subpath="…")]`
 *   案件文件把 contract_id 换成 case_id
 * - 目录（不落附件）：`[已引用目录：name (contract_id=N, subpath="…")]`
 *   模型收到后先用 list_folder_files 列目录、再 read_folder_file 读文件
 */
const SENT_REF_RE =
  /^\[已引用(文件|目录)：(.+?) \((?:attachment_id=[0-9a-f-]+, )?(contract_id|case_id)=(\d+), subpath="(.+?)"\)\]$/

/**
 * 把 user 消息正文拆成「引用块 + 剩余正文」。
 * 历史回放与本地发送走同一解析，气泡上方把引用重放为 chip——否则回看
 * 会话时引用只是一坨长文本。非引用消息原样返回（body 不动）。
 */
export function splitRefBlocks(content: string): { refs: SentRefMeta[]; body: string } {
  const refs: SentRefMeta[] = []
  const kept: string[] = []
  for (const line of content.split('\n')) {
    const m = SENT_REF_RE.exec(line.trim())
    if (m?.[1] && m[2] && m[3] && m[4] && m[5]) {
      refs.push({
        isFolder: m[1] === '目录' || undefined,
        name: m[2],
        kind: m[3] === 'case_id' ? 'case' : 'contract',
        ownerId: Number(m[4]),
        subpath: m[5],
      })
    } else kept.push(line)
  }
  if (refs.length === 0) return { refs, body: content }
  // 去掉引用块后正文可能只剩空白（默认语被引用块替换的场景）——保留原始
  // 换行结构，仅去掉首尾空段
  return { refs, body: kept.join('\n').replace(/^\n+|\n+$/g, '') }
}

/** 「[当前页面：xxx]」行——通用模式下 send 注入的页面锚点，回放折叠为 chip */
const PAGE_HINT_RE = /^\[当前页面：(.+?)\]$/

/** 「[当前业务：xxx]」行——业务范围（详情页工作区/浮层 context）下 send 注入的
 *  归属锚点，含委托/案件名与 id，模型据此直达对应绑定文件夹与数据 */
const BIZ_HINT_RE = /^\[当前业务：(.+?)\]$/

/** 把 user 消息开头的页面锚点行拆出来；无锚点原样返回 */
export function splitPageHintLine(content: string): { pageHint: string | null; body: string } {
  const lines = content.split('\n')
  const first = lines[0]?.trim() ?? ''
  const m = PAGE_HINT_RE.exec(first)
  if (!m?.[1]) return { pageHint: null, body: content }
  return { pageHint: m[1], body: lines.slice(1).join('\n').replace(/^\n+/, '') }
}

/** 把 user 消息开头的业务锚点行拆出来（与页面锚点同构）；无锚点原样返回 */
export function splitBizHintLine(content: string): { bizHint: string | null; body: string } {
  const lines = content.split('\n')
  const first = lines[0]?.trim() ?? ''
  const m = BIZ_HINT_RE.exec(first)
  if (!m?.[1]) return { bizHint: null, body: content }
  return { bizHint: m[1], body: lines.slice(1).join('\n').replace(/^\n+/, '') }
}

/**
 * 路由 → 页面描述（通用助手的页面感知兜底）。详情页会挂载后写更精确的
 * 描述（含实体名与 id，模型可拿 id 用工具深入了解页面内容）覆盖此值。
 */
export function describeLocation(pathname: string): string {
  if (pathname === '/') return '工作台首页'
  if (pathname.startsWith('/projects/')) return '委托详情页'
  if (pathname.startsWith('/projects')) return '办案列表页'
  if (pathname.startsWith('/material-prep')) return '材料预处理台'
  return `页面 ${pathname}`
}

export function historyToMessages(rows: AgentHistoryMessage[]): ChatMessage[] {
  return rows.map((row) => {
    const hintSplit = row.role === 'user' ? splitPageHintLine(row.content) : null
    const bizSplit = row.role === 'user' ? splitBizHintLine(hintSplit?.body ?? row.content) : null
    const refsSplit = row.role === 'user' ? splitRefBlocks(bizSplit?.body ?? row.content) : null
    return {
      id: `db-${row.message_id}`,
      role: row.role,
      content: row.role === 'tool' ? row.content.slice(0, 2000) : (refsSplit?.body ?? row.content),
      pageHint: hintSplit?.pageHint ?? undefined,
      bizHint: bizSplit?.bizHint ?? undefined,
      refs: refsSplit?.refs.length ? refsSplit.refs : undefined,
      toolName: row.tool_name || undefined,
      truncated: row.metadata?.truncated === true || undefined,
    }
  })
}

/**
 * 会话按业务范围分组（侧栏「项目分组」形态）：案件/合同各成组（组名 =
 * 案件名 / 委托人客户名，来自后端 scope_name 注水），任务式与通用对话
 * 各归一组兜底。组间按组内最新 updated_at 排序，组内保持传入顺序
 * （后端已按 updated_at 降序返回）。
 */
export function groupSessions(sessions: AgentSession[]): SessionGroup[] {
  const groups = new Map<string, SessionGroup>()
  const groupOf = (s: AgentSession): SessionGroup => {
    const kind = s.origin === 'task' ? 'task' : s.case_id ? 'case' : s.contract_id ? 'contract' : 'chat'
    const key =
      kind === 'task' || kind === 'chat'
        ? kind
        : `${kind}:${kind === 'case' ? s.case_id : s.contract_id}`
    let g = groups.get(key)
    if (!g) {
      const label =
        kind === 'task'
          ? '后台任务'
          : kind === 'chat'
            ? '通用对话'
            : (s.scope_name?.trim() || `${kind === 'case' ? '案件' : '合同'} #${kind === 'case' ? s.case_id : s.contract_id}`)
      g = { key, kind, label, sessions: [] }
      groups.set(key, g)
    }
    return g
  }
  for (const s of sessions) groupOf(s).sessions.push(s)
  return [...groups.values()].sort((a, b) => {
    const ta = a.sessions[0]?.updated_at ?? ''
    const tb = b.sessions[0]?.updated_at ?? ''
    return tb.localeCompare(ta)
  })
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
