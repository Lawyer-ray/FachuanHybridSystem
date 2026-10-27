/**
 * 位置与分组：路由 → 页面描述、会话按业务范围分组。
 */

import type { AgentSession, SessionGroup } from '../types'

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
      g = { key, kind, label, sessions: [], refId: kind === 'case' ? s.case_id ?? undefined : kind === 'contract' ? s.contract_id ?? undefined : undefined }
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
