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
}
