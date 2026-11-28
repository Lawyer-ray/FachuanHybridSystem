/**
 * Copilot 技能类型：`/` 命令菜单与技能抽屉的类型契约。
 *
 * 字段口径以施工契约为准（`docs/analysis/user-skills-copilot-2026-11-28/CONTRACT.md`
 * §2 / §8 / §10）。`key` 是身份（`builtin:<name>` / `skill:<uuid>`）；`source` 与
 * `scope` 是「哪一层来的」的唯一判据——内置也是 `builtin`，**不再是空串**。
 *
 * 服务端字段缺省时的降级**只在 `skill-api.ts` 的归一化里做一次**（`normalizeAgentSkill`
 * / `normalizeAgentSkillQuota`）：本文件里的 `AgentSkill` 是归一化之后的形状，组件里
 * 不该再散落 `?? 默认值` 这类补丁，否则每个调用点各降级一次就会互相打架。
 *
 * 端点与请求构造见 `skill-api.ts`（前缀 `agent/skills`，后端
 * `backend/apps/agent/api/skill_api.py`）；消费方是 `domain/slash.ts`（菜单徽标）、
 * `components/SlashMenu.tsx`（展示）与 `components/skill/*`（管理抽屉）。
 */

/** 来源：内置随代码发布；其余三种是数据库条目（个人 / 团队 / 所内） */
export type AgentSkillSource = 'builtin' | 'user' | 'team' | 'law_firm'

/**
 * 作用域（级联层次 `builtin(-1) > lawyer(0) > team(1) > law_firm(2)`）。
 *
 * 前端只用它分 tab、写文案；**级联决胜在服务端**——拿到的 `shadowed` /
 * `shadowed_by` 已经是算好的结果，前端不再自己比较同名技能。
 */
export type AgentSkillScope = 'builtin' | 'lawyer' | 'team' | 'law_firm'

/**
 * 可写的三个作用域（内置是随代码发布的只读层，不能新建 / 提审到它）。
 * 与 `AgentSkillScope` 分开命名：一个是「能出现在哪一层」（含 builtin），
 * 一个是「能写进哪一层」，混用会让 `scope: 'builtin'` 在类型上也是合法的。
 */
export type AgentSkillWritableScope = 'lawyer' | 'team' | 'law_firm'

/** 线上槽位状态；**永不出现 `pending`**（待审是与它正交的 `review_status`） */
export type AgentSkillStatus = 'draft' | 'active' | 'archived'

/** 修订流状态：个人技能恒 `none`（自己的技能自己说了算，不进审批） */
export type AgentSkillReviewStatus = 'none' | 'pending' | 'rejected'

/** 覆盖关系里的一条（`shadowed` 的元素，也是 `shadowed_by` 的值） */
export interface AgentSkillShadowRef {
  key: string
  /** 被覆盖 / 覆盖者的作用域，用来写「被『我的』同名技能覆盖」这类文案 */
  scope: AgentSkillScope
  title: string
}

/**
 * `GET agent/skills` 的清单项（管理抽屉面）。
 *
 * 双轨语义：`status` 是线上槽位（`published_version` 那一版），`review_status` 是
 * 工作区修订流——编辑一条已生效的共享技能不会下线它，所以「已生效 + 待审」是常态。
 */
export interface AgentSkill {
  /** 身份：`builtin:<name>` / `skill:<uuid>`（启停、详情、编辑都用它，含 `:` 需 URL 编码） */
  key: string
  /** slug：目录名 = `/skill:` 命令名（内置「复制为我的」时沿用） */
  name: string
  /** 显示名（`/` 菜单与抽屉都用它，中文名也要能搜到） */
  title: string
  /**
   * 单行路由描述：抽屉与 `/` 菜单靠它辨认，也是系统提示里「技能索引」的一行
   * （支持提示注入的后端才会看到；见 CONTRACT §9 的 `skill_delivery`）。
   * 正文**不整篇注入**，AI 按需读取（`get_agent_skill` / `/skill:` 展开）。
   */
  description: string
  /** 作用域：分 tab 与写文案用，不可用它推权限 */
  scope: AgentSkillScope
  /** 级联权重（`-1/0/1/2`）：仅用于展示层级与排序核对，服务端对未知 scope 会回 4 */
  scope_weight: number
  source: AgentSkillSource
  /** 偏好启用态（个人技能是本体字段，其余三种写的是本人偏好；见 `setAgentSkillEnabled`） */
  enabled: boolean
  /** 个人 & 本人；所内 / 团队 & 有权限者（服务端算，前端不重算） */
  editable: boolean
  /** 乐观锁版本：内置为 0；修改时回传，不符后端 409 */
  version: number
  status: AgentSkillStatus
  review_status: AgentSkillReviewStatus
  /** 驳回理由（`review_status='rejected'` 时非空），也是驳回徽标的 tooltip */
  review_note: string
  /** 共享技能的线上生效版；个人技能 = `version` */
  published_version: number
  /** 共享技能：工作区版本 ≠ 线上版本（个人技能恒 false） */
  has_unpublished_changes: boolean
  /** 被本条目遮蔽的更低优先级同名条目（空数组 = 不覆盖任何条目） */
  shadowed: AgentSkillShadowRef[]
  /** 本轮是否实际胜出（被同名高优先级条目遮蔽时为 false） */
  effective: boolean
  /** 遮蔽本条目的赢家（没有则为 null），用于「被『我的』同名技能覆盖」 */
  shadowed_by: AgentSkillShadowRef | null
  /** 以下五个能力位**全部由服务端算**：前端只读，绝不按 `is_admin` 自己推 */
  can_edit: boolean
  can_submit: boolean
  can_review: boolean
  can_archive: boolean
  can_restore: boolean
  /**
   * 能否把这一条**提升**到共享层（个人 → 团队/所内）。**可选**：未升级的部署不下发，
   * 缺省按「不出现提升入口」处理，绝不默认 true。
   *
   * 与 `can_submit` 的分工不能混：`can_submit` 是「已在共享层的条目能不能再提审
   * 工作区」，而它对个人条目**恒 false**（`permissions.can_submit` 明确拒绝
   * `scope=lawyer`）。用 `can_submit` 判个人条目能不能提升，只会让入口永远不出现。
   */
  can_promote?: boolean
  /** 可提升到的目标层（服务端算）；缺失或空数组 = 不给提升入口，不在前端硬编码 */
  promotable_scopes?: AgentSkillWritableScope[]
}

/** `GET agent/skills` 的响应体 */
export interface AgentSkillList {
  skills: AgentSkill[]
}

/** `GET agent/skills/{key}`：清单字段 + 工作区正文（编辑器打开时才拉） */
export interface AgentSkillDetail extends AgentSkill {
  body: string
}

/** `PATCH agent/skills/{key}` 的回执（只改启停偏好，不改正文） */
export interface AgentSkillToggleReceipt {
  key: string
  enabled: boolean
}

/**
 * 新建请求体。
 *
 * `name` 省略 = 后端生成 `skill-<6位base36>`；`scope` 省略 = 个人技能。
 * `team_id` 只在 `scope='team'` 时给（团队归属由发布对话框选择，抽屉不提供）。
 */
export interface AgentSkillCreateInput {
  name?: string
  title: string
  description: string
  body: string
  scope?: AgentSkillWritableScope
  team_id?: string
}

/** 修改的请求体（`name` 建后不可改；`version` 不符后端 409，编辑器保留草稿） */
export interface AgentSkillUpdateInput {
  title: string
  description: string
  body: string
  version: number
}

/** 字段级校验错误（`field` 是表单字段名：name/title/description/body） */
export interface AgentSkillValidationError {
  field: string
  message: string
}

/**
 * 安全闸门的一条命中（`safety`）。`hard` = 提交直接 422；`soft` = 需勾选确认。
 * `excerpt` 已由服务端脱敏，可以原样展示给作者定位。
 */
export interface AgentSkillFinding {
  /** id_card / phone / bank_card / court_case_no / email / secret / entity_name / injection / dangerous_tool */
  code: string
  level: 'hard' | 'soft'
  field: string
  message: string
  excerpt: string
}

/** `POST agent/skills/validate` 的回执：`preview` 是「AI 实际读到的 SKILL.md」 */
export interface AgentSkillValidation {
  ok: boolean
  errors: AgentSkillValidationError[]
  preview: string
  /** 服务端未接入安全闸门时不带这个字段（按空处理即可） */
  safety?: AgentSkillFinding[]
}

/** 行级 diff 的操作：未变 / 新增 / 删除（「替换」被服务端拆成 del + ins） */
export type AgentSkillDiffOp = 'equal' | 'ins' | 'del'

/**
 * diff 的一个块：同一操作下的整行文本。
 *
 * 服务端用 `SequenceMatcher` 逐行比对后给 `lines` 数组（不是 CONTRACT §8 写的单段
 * `text`）——契约与实现不一致处在交付回报里记一笔，以实现为准才能直接渲染。
 */
export interface AgentSkillDiffHunk {
  op: AgentSkillDiffOp
  /** 整行文本（不含换行符） */
  lines: string[]
}

/** `GET agent/skills/{key}/diff`：默认「线上生效版 vs 工作区」 */
export interface AgentSkillDiff {
  v1: number
  v2: number
  hunks: AgentSkillDiffHunk[]
}

/** `GET agent/skills/resolve/{ref}/content`：运行时正文（MCP 取全文的同一条出口） */
export interface AgentSkillContent {
  key: string
  name: string
  title: string
  scope: AgentSkillScope
  version: number
  /** 本页正文（服务端按 UTF-8 字符边界切分，不会切坏多字节字符） */
  content: string
  start: number
  total_bytes: number
  truncated: boolean
  /** 下一页起点；`truncated=false` 时为 null */
  next_start: number | null
}

/** 按作用域分列的计数 / 上限（`lawyer` / `team` / `law_firm` 三层） */
export interface AgentSkillScopeCounts {
  lawyer: number
  team: number
  law_firm: number
}

/**
 * `GET agent/skills/quota`：配额回执。
 *
 * `max_by_scope` 某层为 0 表示服务端没给该层的上限（旧后端），前端据此**不显示**
 * 配额条也不禁用新建——拿 0 当「已满」会把入口关死。
 */
export interface AgentSkillQuota {
  /** 个人技能上限（旧字段，等价于 `max_by_scope.lawyer`） */
  max_skills: number
  used: number
  by_scope: AgentSkillScopeCounts
  max_by_scope: AgentSkillScopeCounts
  /**
   * 能否直建所内草稿（服务端 `can_create_firm`）。回执没带时归一化为 false：
   * 宁可不给入口，也不让普通律师点进去撞 403。
   */
  can_create_firm: boolean
}

/**
 * 提审请求体。
 *
 * 个人技能提审**必须**给 `target_scope`（服务端据此把条目提升到目标层再置待审）；
 * 已经在共享层的条目改层同样要管理员，所以前端只在「我的」里发起提升。
 */
export interface AgentSkillSubmitInput {
  target_scope: AgentSkillWritableScope
  note?: string
  /** 所内层发布要勾「会影响全所」确认（同记忆策展口径） */
  acknowledged_firm_wide?: boolean
  /**
   * 提审时改名（只对「个人 → 共享」这条路径生效）：目标层已有同名技能时用它避撞名。
   * 服务端按 `NAME_RE` / 保留字 / 目标层查重校验，撞名回 409。
   */
  name?: string
  /**
   * 目标团队（仅 `target_scope='team'`）。**数字**而非字符串：后端是 `int | None`，
   * 传 `"3"` 会被 Ninja 判 422。省略 = 服务端按本人所属律师团队选定。
   */
  team_id?: number
}

/** 审批请求体（`note` 在驳回时必填，通过时可选） */
export interface AgentSkillReviewInput {
  decision: 'approve' | 'reject'
  note?: string
  acknowledged_firm_wide?: boolean
}

// ── 试跑（发布前真跑一轮，把模型的实际回复交给审批人）──────────────

/**
 * 试跑的注入模式：三档分别验证**不同的一层**，混起来就会把一次通过当成上线保证。
 * `auto` 由服务端按发布态挑（已发布走真实索引，未发布走内联全文）；`inline` 把正文
 * 整篇内联，验的是**指令语义**；`index` 只给名字与描述、模型得自己调
 * `get_agent_skill`，验的是**自主发现**。
 */
export type AgentSkillTrialMode = 'auto' | 'inline' | 'index'

/** `POST agent/skills/{key}/trial` 的请求体（三个字段都可省，服务端各有缺省） */
export interface AgentSkillTrialInput {
  /** 留空 = 服务端默认探针问法（先原样复述第一条要求，再说明接下来怎么做） */
  question?: string
  /** 用哪个后端跑；省略 = 服务端默认（pi）。声明 `tool_only` 的后端会被 422 */
  backend?: string
  mode?: AgentSkillTrialMode
}

/** 试跑里没调通的一次工具调用（模型想调 X 但失败了） */
export interface AgentSkillTrialToolError {
  /** 工具名（服务端原样给的，可能是 `mcp__fachuan__get_agent_skill` 这种全名） */
  tool: string
  message: string
}

/**
 * 试跑回执（`SkillTrialOut`）。★ 三项是后端并行 lane 正在扩的字段：**缺失即当没有**，
 * 界面绝不补默认值。尤其 `mode`——补成 `auto` 等于替服务端表态「这次是按索引验的」。
 */
export interface AgentSkillTrialResult {
  ok: boolean
  /** 模型回复正文（保留换行原样展示） */
  text: string
  backend: string
  /** 服务端报不出模型名时为 null / 空串；界面**整项不显示**（不能渲染成 "null"） */
  model: string | null
  duration_ms: number
  skill_key: string
  skill_name: string
  /** 作用域原始字符串（服务端口径）：只展示，不用它推权限 */
  skill_scope: string
  skill_version: number
  /** 实际注入给模型的那段文字——审批人要能看见「我们到底让它看了什么」 */
  injected: string
  tool_calls: string[]
  /** `ok=false` 时的原因；`ok=true` 时为空串 */
  error: string
  /** ★ 这次实际用的注入方式（可能因服务端降级而与请求不同） */
  mode?: AgentSkillTrialMode
  /** ★ 失败的工具调用；非空说明模型没读到全文 */
  tool_errors?: AgentSkillTrialToolError[]
  /** ★ 试跑流水号（服务端审计用；缺失只是不能追号） */
  trial_id?: string
}

/**
 * `GET agent/skills/trial-quota`：今日试跑额度。整个端点都是新加的（★），所以**每个
 * 字段都可缺**：旧后端回 `{}` / 404 时不能被读成「剩余 0 次」把按钮禁死。只有明确拿到
 * `remaining === 0` 才拦。
 */
export interface AgentSkillTrialQuota {
  /** 每日上限；缺失 = 服务端没下发额度信息 */
  limit?: number
  used?: number
  /** 今日剩余次数（服务端算的权威值）；缺失 = 不知道，不拦 */
  remaining?: number
  /** 恢复时间（ISO8601，带时区）；只做展示，缺失时不说恢复时间 */
  reset_at?: string
}
