/**
 * UI 动作清单（自动生成，禁手改 —— python -m apps.agent.services.ui_action --ts）
 *
 * 后端单一来源：apps/agent/services/ui_action/manifest.py。
 * 改清单请改那里再重跑上面那条命令，**不要**手改本文件
 * （CI 的 test_ui_action_manifest_same_source.py 逐字节比对会红）。
 *
 * 生成器是反射而不是手写模板：动作名 / 描述 / 风险档 / 参数 schema 只有 manifest
 * 一个来源。手抄两份的漂移是静默的（后端有动作、前端没执行器 → 模型调完页面
 * 毫无反应、无报错）。
 */

export type UiToolName =
  | 'ui_navigate'
  | 'ui_copilot_open'
  | 'ui_material_prep_set_stage'

/**
 * 三档风险：`safe` 无外部副作用直接执行；`confirm` 走后端审批；
 * `guarded` 审批之后再要前端本地二次确认。
 */
export type UiToolRisk = 'safe' | 'confirm' | 'guarded'

/** 工具面分层：`deferred` 由 tool_search 加载后仍以真名调用（审批不受影响） */
export type UiToolTier = 'direct' | 'deferred'

/** 撤销能力：只覆盖 UI 状态（nav/toggle），业务写库一律 none */
export type UiToolUndo = 'nav' | 'toggle' | 'none'

export interface UiToolSpec {
  name: UiToolName
  /** 审批卡 / banner 上的中文名（别在组件里另起一套文案） */
  title: string
  /** 给模型看的「何时该用 / 何时不该用」，含反例 */
  describe: string
  /** 参数 JSON Schema（additionalProperties 恒为 false，前端据此做第二道守卫） */
  argsSchema: Record<string, unknown>
  /** 期望路由前缀；`null` = 任意页面 */
  route: string | null
  risk: UiToolRisk
  tier: UiToolTier
  /** 前端执行器 id（可读标签；执行分派按 name 走闭集，不靠它） */
  handler: string
  idempotent: boolean
  undo: UiToolUndo
}

export const UI_TOOL_SPECS: readonly UiToolSpec[] = [
  {
    name: 'ui_navigate',
    title: '跳转页面',
    describe:
      '在应用内跳转到某个页面（只改 URL，不提交任何业务操作）。path 必须是站内路径，如 /material-prep?stage=todo。它不是浏览器：不能填表、不能调接口，也看不到跳转后页面的内容。',
    argsSchema: {
      additionalProperties: false,
      properties: {
        path: {
          description: '站内路径，形如 /material-prep?stage=todo；不带域名与协议。',
          type: 'string',
        },
      },
      required: ['path'],
      type: 'object',
    },
    route: null,
    risk: 'safe',
    tier: 'direct',
    handler: 'navigate',
    idempotent: true,
    undo: 'nav',
  },
  {
    name: 'ui_copilot_open',
    title: '打开 AI 助手面板',
    describe:
      '把 AI 助手面板打开并置前（律师能在里面看到对话）。不带参数就是普通打开；origin/refId/title 三项齐全才算「业务内会话」，面板头部会挂上对应的案件/合同。它不发送消息、不切换会话，也不打开别的弹窗——用户要提问请直接回答，不要调它代替回答。',
    argsSchema: {
      additionalProperties: false,
      properties: {
        origin: {
          description: '业务入口：case=案件内，contract=合同/委托内。',
          enum: ['case', 'contract'],
          type: 'string',
        },
        refId: {
          description: '对应业务 id（案件 id 或合同 id）。',
          type: 'integer',
        },
        title: {
          description: '展示名（面板头部 chip 用，如客户/委托名）。',
          type: 'string',
        },
      },
      required: [],
      type: 'object',
    },
    route: null,
    risk: 'safe',
    tier: 'direct',
    handler: 'openCopilot',
    idempotent: true,
    undo: 'toggle',
  },
  {
    name: 'ui_material_prep_set_stage',
    title: '切换材料预处理阶段',
    describe:
      '把材料预处理页切到某个阶段（收件箱 / 待处理 / 已归案 / 不接归档）。只切视图筛选，不改材料包本身的状态；要真的把材料包归案或上传，请用对应的业务工具，不要用这个动作代替。',
    argsSchema: {
      additionalProperties: false,
      properties: {
        stage: {
          description: 'inbox=收件箱，todo=待处理，done=已归案，filed=不接归档。',
          enum: ['inbox', 'todo', 'done', 'filed'],
          type: 'string',
        },
      },
      required: ['stage'],
      type: 'object',
    },
    route: '/material-prep',
    risk: 'safe',
    tier: 'direct',
    handler: 'setMaterialPrepStage',
    idempotent: true,
    undo: 'toggle',
  },
]

/**
 * 名字 → 规格。执行器分派先查这张表再查 `UI_EXECUTORS`：
 * 两边都是闭集，`resolveExecutor` 因此能把「清单里没有的名字」判成 unknown_action，
 * 而不是拿 `undefined` 硬调（那是运行期 TypeError，日志里看不出是版本漂移）。
 */
export const UI_TOOL_BY_NAME: Record<UiToolName, UiToolSpec> = Object.fromEntries(
  UI_TOOL_SPECS.map((spec) => [spec.name, spec]),
) as Record<UiToolName, UiToolSpec>
