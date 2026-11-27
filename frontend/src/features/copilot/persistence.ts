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

/** 会话 id → 持久化的存储键（新对话用固定键：还没 id 时也要记住） */
function answerModelsKey(sessionId: string | null): string {
  return `copilot:models:${sessionId || 'new'}`
}

/**
 * 读「这个会话上次各栏选的模型」（`kind → model`）。
 *
 * 为什么按会话存：模型是**本轮**参数，但律师的真实期待是「这个会话就继续用它」——
 * 刷新一次就回到默认模型，等于每次都要重挑（截图里 `MiniMax-M3.1-Fla…` 就是这么
 * 丢的）。服务端另有 `AgentSession.llm_model`（最近一轮**实际**用过的），两条一起
 * 用：本地这条保住「刚选还没跑」，服务端那条跨设备、跨浏览器也能续上。
 */
export function readStoredAnswerModels(sessionId: string | null): Record<string, string> {
  try {
    const raw = localStorage.getItem(answerModelsKey(sessionId))
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    const out: Record<string, string> = {}
    for (const [kind, model] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof model === 'string' && model) out[kind] = model
    }
    return out
  } catch {
    return {}
  }
}

export function storeAnswerModels(sessionId: string | null, models: Record<string, string>): void {
  try {
    if (Object.keys(models).length === 0) localStorage.removeItem(answerModelsKey(sessionId))
    else localStorage.setItem(answerModelsKey(sessionId), JSON.stringify(models))
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}

/** 会话 id → 勾选后端的存储键（与模型同一套「按会话」口径） */
function answerAgentsKey(sessionId: string | null): string {
  return `copilot:agents:${sessionId || 'new'}`
}

/**
 * 读「这个会话上次勾了哪几个 AI」（本轮参与方）。
 *
 * 与模型同理：勾选只活在前端内存里的话，刷新一次就退回「不勾＝只跑会话默认」，
 * 多答用户每开一次都要重勾。**顺序有意义**（第一栏决定新会话归属），所以存数组
 * 而不是集合。
 */
export function readStoredAnswerAgents(sessionId: string | null): string[] {
  try {
    const raw = localStorage.getItem(answerAgentsKey(sessionId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // 只信字符串，去重保序（上限由 store 再按 MAX_ANSWERS 截断——这里不知道那个常量）
    const out: string[] = []
    for (const item of parsed) {
      if (typeof item === 'string' && item && !out.includes(item)) out.push(item)
    }
    return out
  } catch {
    return []
  }
}

export function storeAnswerAgents(sessionId: string | null, kinds: string[]): void {
  try {
    if (kinds.length === 0) localStorage.removeItem(answerAgentsKey(sessionId))
    else localStorage.setItem(answerAgentsKey(sessionId), JSON.stringify(kinds))
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}

/**
 * 新会话建档时，把「新对话」里勾的 AI 与选的模型搬到这个会话名下。
 *
 * ## 为什么必须有这一步（2026-11-27 用户报「刷新后已选 0 个」的根因）
 *
 * 写盘用 `get().sessionId`：律师在**新对话**里勾选时它还是 null，于是落在
 * `copilot:agents:new`；发出第一条消息才建会话、`sessionId` 才变成真 id。
 * 而 `hydrateAnswerSelection(真 id)` 读的是 `copilot:agents:<真 id>` ——
 * 键不同 → 读到空 → **当场把刚勾的选择清成 0**，刷新之后照样是 0。
 * 读侧本身没错，缺的就是这一次搬家。
 *
 * ## 两个刻意的选择
 *
 * 1. **只搬不删**：`copilot:agents:new` 留着，它语义是「下一条新对话的初值」，
 *    律师连续开几个新对话时不必每次重勾。
 * 2. **只补空位**：目标会话已经有自己的选择就一律不覆盖——否则把 A 会话的偏好
 *    带进一个已经调过的会话，比不记住更让人意外。
 *
 * @returns 实际搬了哪几类（供调用方记日志/测试断言）
 */
export function seedAnswerSelectionFromNew(
  sessionId: string,
): { agents: boolean; models: boolean } {
  const moved = { agents: false, models: false }
  if (!sessionId) return moved
  try {
    const agents = localStorage.getItem(answerAgentsKey(null))
    if (agents && localStorage.getItem(answerAgentsKey(sessionId)) === null) {
      localStorage.setItem(answerAgentsKey(sessionId), agents)
      moved.agents = true
    }
    const models = localStorage.getItem(answerModelsKey(null))
    if (models && localStorage.getItem(answerModelsKey(sessionId)) === null) {
      localStorage.setItem(answerModelsKey(sessionId), models)
      moved.models = true
    }
  } catch {
    /* 无 localStorage 环境忽略 */
  }
  return moved
}

/**
 * 清掉「新对话」那对键（登出 / 401 刷新失败时调）。
 *
 * 不清的后果不是丢数据，是**串账号**：`reset()` 把 sessionId 置回 null 之后，
 * hydrate 会读 `copilot:agents:new`，于是上一个账号勾过的 AI 出现在下一个账号
 * 的输入区里。（模型那条同理。）
 */
export function clearNewAnswerSelection(): void {
  try {
    localStorage.removeItem(answerAgentsKey(null))
    localStorage.removeItem(answerModelsKey(null))
  } catch {
    /* 无 localStorage 环境忽略 */
  }
}
