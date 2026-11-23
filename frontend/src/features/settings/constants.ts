/**
 * 设置域 query key 常量（本域唯一来源）。
 *
 * 三张状态卡（后端服务 / 任务队列 / LLM 网关）原本在组件里各写一份
 * `['settings', '<子名>']`，而「刷新」按钮要按前缀整组失效——两边都手写字面量，
 * 改一处忘另一处就会「点了刷新只重取一部分」。前缀与子 key 都收在这里，
 * 失效与订阅永远同源。
 */

/** 设置页所有状态卡 query key 的公共前缀（「刷新」按它整组失效） */
export const SETTINGS_KEY = ['settings'] as const

/**
 * 三张状态卡的子 key（都以 SETTINGS_KEY 打头，所以 `['settings']` 前缀失效能命中全部）。
 *
 * 无参数，故写成常量而不是工厂：工厂只会每次产出一个新数组引用，
 * 对 react-query 的 key 比较毫无好处。
 */
export const settingsKeys = {
  /** 后端服务：一次探活请求的 RTT（ms） */
  backendProbe: [...SETTINGS_KEY, 'backend-probe'] as const,
  /** Django-Q 集群心跳与队列深度 */
  qCluster: [...SETTINGS_KEY, 'q-cluster'] as const,
  /** LLM 网关模型列表 */
  llmModels: [...SETTINGS_KEY, 'llm-models'] as const,
  /** AI 任务用量（近 1 天） */
  agentUsage: [...SETTINGS_KEY, 'agent-usage'] as const,
}
