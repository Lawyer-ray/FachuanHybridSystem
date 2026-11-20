/**
 * 会话 id、后端选择与会话列表展开状态的 localStorage 持久化（从 store.ts 抽出，
 * 控制单文件规模）。无 localStorage 环境（单测/SSR）静默降级。
 */

const SESSION_KEY = 'copilot:session'

/** 新建会话用的 agent 后端（跨刷新记住用户的偏好，不必每次重选） */
const AGENT_KIND_KEY = 'copilot:agent-kind'

/** 会话列表（rail）是否常驻 */
const RAIL_KEY = 'copilot:rail'

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

/**
 * 「会话列表要不要常驻」的偏好：抽屉面板与独立页（AssistantPage）共用一份。
 *
 * 用户对这件事只有一个态度，不该按宿主记两个 key —— 在抽屉里收起过列表，
 * 打开独立页时它又自己弹回来，就是没记住。默认展开。
 */
/**
 * 草稿按会话持久化（滑动窗口式保留最近几条，不无限增长）。
 *
 * 为什么需要一个 key 前缀而不是单个 key：律师在 A 会话说了一半去 B 会话查东西，
 * 回来时草稿必须还在。单 key 会在切会话那一刻被覆盖成空串。
 */
const DRAFT_PREFIX = 'copilot:draft:'
/** 同时保留多少个会话的草稿（超出时淘汰最早的那条） */
const DRAFT_LIMIT = 20
/** 新建会话（sessionId 为空）的草稿键 */
export const NEW_SESSION_DRAFT_KEY = 'new'

export function readDraft(sessionId: string | null): string {
  try {
    return localStorage.getItem(DRAFT_PREFIX + (sessionId ?? NEW_SESSION_DRAFT_KEY)) ?? ''
  } catch {
    return ''
  }
}

/** 写入草稿；空串等于删除（不留一堆空 key） */
export function storeDraft(sessionId: string | null, text: string): void {
  try {
    const key = DRAFT_PREFIX + (sessionId ?? NEW_SESSION_DRAFT_KEY)
    if (!text.trim()) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, text)
    // 淘汰：只在新增 key 时做一次，避免每次写都扫全表
    const keys = Object.keys(localStorage).filter((k) => k.startsWith(DRAFT_PREFIX))
    if (keys.length > DRAFT_LIMIT) {
      for (const stale of keys.slice(0, keys.length - DRAFT_LIMIT)) localStorage.removeItem(stale)
    }
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}

export function clearDraft(sessionId: string | null): void {
  storeDraft(sessionId, '')
}

export function readStoredRailOpen(): boolean {
  try {
    return localStorage.getItem(RAIL_KEY) !== '0'
  } catch {
    return true
  }
}

export function storeRailOpen(open: boolean): void {
  try {
    localStorage.setItem(RAIL_KEY, open ? '1' : '0')
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}
