/**
 * 会话 id 与后端选择的 localStorage 持久化（从 store.ts 抽出，控制单文件规模）。
 * 无 localStorage 环境（单测/SSR）静默降级。
 */

const SESSION_KEY = 'copilot:session'

/** 新建会话用的 agent 后端（跨刷新记住用户的偏好，不必每次重选） */
const AGENT_KIND_KEY = 'copilot:agent-kind'

export function readStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY) || null
  } catch {
    return null
  }
}

export function storeSession(id: string | null): void {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id)
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}

/**
 * 读取「新建会话用哪个后端」的偏好。
 *
 * 只返回**字符串**不做白名单校验：后端清单还没拉到时无法判断合法性，而校验
 * 写在这里等于把可用性判断复制一份。非法 / 已下线的 kind 会被后端 400 拒绝，
 * 由 `selectAgentKind` 在清单到手后收敛（见 store/backends.ts）。
 */
export function readStoredAgentKind(): string {
  try {
    return localStorage.getItem(AGENT_KIND_KEY) || ''
  } catch {
    return ''
  }
}

export function storeAgentKind(kind: string): void {
  try {
    if (kind) localStorage.setItem(AGENT_KIND_KEY, kind)
    else localStorage.removeItem(AGENT_KIND_KEY)
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}
