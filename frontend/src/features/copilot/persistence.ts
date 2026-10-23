/**
 * 会话 id 的 localStorage 持久化（从 store.ts 抽出，控制单文件规模）。
 * 无 localStorage 环境（单测/SSR）静默降级。
 */

const SESSION_KEY = 'copilot:session'

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
