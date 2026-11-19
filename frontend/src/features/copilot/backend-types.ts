/**
 * Copilot 多后端类型：可选后端清单与「新建会话用哪个」的选择状态。
 *
 * 从 `types.ts` 拆出（后者贴近 350 行软红线），语义上也自成一节——后端选择
 * 只在**建会话那一刻**生效，与转录/审批/流式无关。
 */

/**
 * GET /agent/backends 的可选后端项（新建会话时的后端切换器数据源）。
 *
 * `available=false` 时必须读 `reason` 并置灰：用户若选中它，报错会发生在**建完
 * 会话之后**，而 `agent_kind` 不能改——只能换个后端重开。
 */
export interface AgentBackendOption {
  kind: string
  /** 给用户看的名字（"Pi" / "DeepSeek Harness"） */
  label: string
  /** 一句话说明（切换器副标题） */
  description: string
  available: boolean
  /** 不可用原因；`available=true` 时为空串 */
  reason: string
  /** 能力声明（字段见后端 `BackendCapabilities`），前端据此隐藏插话框等 */
  capabilities: Record<string, boolean>
  /**
   * 该后端可选的模型（`GET /agent/backends` 的 `models`；空 = 跟随平台默认）。
   *
   * 三个后端最终都落到同一个 LiteLLM，所以共用同一份清单；将来某后端有独占
   * 模型时在它自己返回值里收窄，前端不写死任何对应关系。
   *
   * **缺省 `[]`**：后端尚未上线该字段的部署里它不存在，前端据此隐去模型下拉
   * （见 {@link AgentBackendOption.default_model} 的注释）。
   */
  models?: string[]
  /** 未显式指定时用的模型（UI 预填；`null`/缺省 = 不知道，不预填） */
  default_model?: string | null
}

/**
 * 本轮一个参与方：哪个后端 + 用哪个模型（`POST /agent/sessions/{id}/messages`
 * 的 `agents` 数组元素，与后端 `AgentSpecIn` 同形）。
 *
 * `model` 缺省 = 用平台默认模型——与引入本字段前发纯字符串 `"pi"` 完全等价。
 */
export interface AgentSpec {
  kind: string
  model?: string
}

/**
 * store 的后端选择字段（并入 `CopilotState`，实现见 `store/backends.ts`）。
 */
export interface AgentBackendSelection {
  /**
   * 新建会话用哪个 agent 后端（建会话时作为 `agent_kind` 下发）。
   *
   * 只作用于**还没建的**会话：已有会话的后端是 `currentSession.agent_kind`，
   * 不可更换（换了上下文就断）。空串 = 不指定，由后端用默认值（pi）。
   */
  selectedAgentKind: string
  /** 可选后端清单（切换器数据源；拉取失败时为空数组，切换器退化为纯展示） */
  backends: AgentBackendOption[]
  /** 拉取可选后端清单（面板打开时调；失败静默保留上一次结果） */
  loadBackends: () => Promise<void>
  /** 选择新建会话用的后端（不可用的选项直接忽略） */
  selectAgentKind: (kind: string) => void
  /**
   * 本轮各栏指定的模型（`kind → 模型名`，只对有值的 kind 存在键）。
   *
   * 与 `answerAgents` 分开存：`answerAgents` 决定「跑哪几家」，本字段决定
   * 「每家跑哪个模型」。没指定模型的后端不出现在这里（发消息时省略 `model`
   * 字段，后端回落平台默认）。`reset()` 清空。
   */
  answerModels: Record<string, string>
  /** 给某一栏指定模型（空串 = 取消指定，回落平台默认） */
  setAnswerModel: (kind: string, model: string) => void
}
