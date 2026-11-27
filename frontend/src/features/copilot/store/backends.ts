/**
 * store slice：agent 后端选择（新建会话用 pi 还是 dsh）。
 *
 * 为什么选择放进 store 而不是组件本地 state：`send` 到 `store/turn-send.ts` 里建会话
 * 时需要它，而建会话发生在「用户敲下回车」那一刻，不是组件能拦的路由。
 *
 * ## 语义：只能为新会话选
 *
 * `agent_kind` 是**会话级、不可更换**的属性——上下文归后端自己管（pi 有自己的
 * session 文件），换后端等于换脑子，前面的对话对它不存在。所以：
 * - 没会话（`sessionId === null`）时**本轮勾选的第一个后端**决定新建会话的
 *   归属（见 store/turn.ts 与 components/AnswerAgentMenu）；`selectedAgentKind`
 *   是本轮没勾任何后端时的兜底（= 部署默认）；
 * - 已建会话只读展示 `session.agent_kind`（标题后的后缀，不是控件）。
 *
 * ## 读不到清单时怎么办
 *
 * `backends` 为空（接口失败 / 还没拉）时多选菜单只显示一句「清单暂不可用」，
 * **不阻塞**发消息：空串 `selectedAgentKind` 就是「不指定」，后端走默认值 pi。
 * 为一次探测失败拦住用户提问，代价远大于收益。
 */

import * as copilotApi from '../api'
import { readStoredAgentKind, storeAgentKind } from '../persistence'
import type { AgentBackendOption, CopilotState } from '../types'
import type { Slice } from './slice'

export type BackendsSlice = Pick<
  CopilotState,
  'backends' | 'backendsState' | 'selectedAgentKind' | 'loadBackends' | 'selectAgentKind'
>

/** 在清单里找一个 kind 对应的选项（找不到返回 undefined）。 */
export function findBackend(backends: AgentBackendOption[], kind: string): AgentBackendOption | undefined {
  return backends.find((b) => b.kind === kind)
}

/**
 * 「默认边界」：清单里的第一项。
 *
 * 顺序由后端给（注册表有序 + 未注册的 dsh 追加在后），前端不再排序——两处排序
 * 迟早漂移。清单为空时返回 undefined，调用方据此退化为不指定。
 */
export function defaultAgentKind(backends: AgentBackendOption[]): string {
  return backends[0]?.kind ?? ''
}

/**
 * 后端能力声明的保守缺省值。
 *
 * 清单还没拉到（或拉取失败）时用它：**按 pi 的能力放行**（`steer` 等为 true）。
 * 反过来（缺省全 false）会把插话框、逐字动画在每次冷启动时隐藏一遍——用户会
 * 先看到「没有插话框」再突然出现，比短暂多显示一个按钮糟糕得多。而且空清单的
 * 默认后端就是 pi（见 `defaultAgentKind`），放行才是真的对齐。
 */
export const DEFAULT_CAPABILITIES: Record<string, boolean> = {
  streaming: true,
  tool_calls: true,
  approval: true,
  compaction: true,
  steer: true,
  concurrent_in_session: false,
}

/**
 * 取某个 kind 的能力声明（找不到该后端时返回保守缺省）。
 *
 * UI 据此隐藏入口，而不是硬编码 `if (agentKind === 'pi')`：新后端注册后只要
 * 如实声明能力，前端不需要跟着改。
 */
export function resolveCapabilities(backends: AgentBackendOption[], kind: string): Record<string, boolean> {
  return findBackend(backends, kind)?.capabilities ?? DEFAULT_CAPABILITIES
}

/**
 * 要不要给这个后端挂「无审批闸门」标记。
 *
 * 两件事必须分开看：
 *
 * - **清单里查不到这个 kind**（`backends` 还没拉到 / 历史消息里的未知后端）→ **不挂**。
 *   那一刻所有 kind 都查不到，按「查不到＝没闸门」显示会让 pi 的回答栏头也闪一遍
 *   「无审批」——这个标记一旦误报过一次，之后每次真报都会被当成噪声。
 * - **查到了但没声明 `approval`**（或声明为 false）→ **挂**。合规默认值必须偏向披露：
 *   把「没声明」当成「有闸门」，正是审计里最危险的那种乐观
 *   （`BackendCapabilities.approval` 的原话：`False` 的后端在高危动作上没有人工闸门）。
 */
export function noApprovalWarn(option: AgentBackendOption | undefined): boolean {
  return option !== undefined && option.capabilities?.approval !== true
}

export const createBackendsSlice: Slice<BackendsSlice> = (set, get) => ({
  backends: [],
  backendsState: 'idle',
  selectedAgentKind: readStoredAgentKind(),

  loadBackends: async () => {
    // 在飞时不重复发（菜单每次打开都可能触发重拉，这里靠状态自身去重）
    if (get().backendsState === 'loading') return
    set({ backendsState: 'loading' })
    try {
      const backends = await copilotApi.fetchBackends()
      const selected = get().selectedAgentKind
      // 偏好还可用就留着；不可用（已下线 / 未安装）回落默认——否则用户下次
      // 发消息会撞上「选中项其实是灰的」这个自相矛盾的界面。
      const kept = findBackend(backends, selected)
      const next = kept?.available ? selected : defaultAgentKind(backends.filter((b) => b.available))
      set({ backends, backendsState: 'ready', selectedAgentKind: next })
      storeAgentKind(next)
    } catch {
      // 不再静默：`backendsState='error'` 让切换器给出「重试」而不是一句「暂不可用」。
      // 旧实现是 catch 里什么都不做，于是失败一次 = 整个页面生命周期都不会再拉，
      // 用户只能刷新页面（2026-11-27：qoder 模型清单探测卡 15 秒 → 首屏菜单永久空）。
      set({ backendsState: 'error' })
    }
  },

  selectAgentKind: (kind) => {
    const option = findBackend(get().backends, kind)
    // 不可用的选项直接忽略：用户点不到（UI 置灰），键盘/程序路径也不该放行
    if (!option?.available) return
    set({ selectedAgentKind: kind })
    storeAgentKind(kind)
  },
})
