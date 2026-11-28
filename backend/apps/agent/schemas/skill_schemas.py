"""技能清单 / 详情 / 正文出口 / 校验 / 双轨发布的请求响应契约（CONTRACT §2 §8）。

字段口径：``key`` 是身份（``builtin:<name>`` / ``skill:<uuid>``），``name`` 是命令名，
``scope`` 是四档作用域（``builtin`` / ``lawyer`` / ``team`` / ``law_firm``——内置不再是
空串），``source`` 是前端唯一来源判据。

## 为什么清单与详情是两个 ``Schema`` 而不是继承

``can_*`` / ``effective`` / ``shadowed_by`` 是**清单出口**（``resolve.list_visible_skills``）
逐条算出来的：它一次性拿到候选集、级联赢家与律师身份，才知道「这条能不能编辑」「这条
是不是被同名技能顶掉了」。**详情出口**（``user_skills.entry_for_row``）只拿到一行，
算不出这三样。

所以详情不继承 ``SkillOut``：硬要继承就只能给这三项填默认值，那会把「服务端没算」
伪装成 ``false`` ——前端会把「审批」按钮对管理员永久灰掉，而这种错没有任何报错，
只能靠人肉发现。前端按 ``key`` 把详情与清单合并，缺失的语义由清单提供。
"""

from __future__ import annotations

from ninja import Schema


class SkillShadowRef(Schema):
    """覆盖关系里的对手身份（``shadowed`` 的元素与 ``shadowed_by`` 同形）。"""

    key: str
    scope: str
    title: str


class SkillOut(Schema):
    """管理抽屉清单项（``resolve.list_visible_skills`` 的完整字段集，CONTRACT §2）。"""

    key: str
    name: str
    title: str
    description: str
    scope: str
    scope_weight: int
    source: str
    enabled: bool
    editable: bool
    version: int
    status: str
    review_status: str
    review_note: str
    published_version: int
    has_unpublished_changes: bool
    shadowed: list[SkillShadowRef]
    effective: bool
    shadowed_by: SkillShadowRef | None
    can_edit: bool
    can_submit: bool
    can_review: bool
    can_archive: bool
    can_restore: bool
    #: 能否把这条个人技能提到共享层（服务端算；前端只渲染，不自己判）
    can_promote: bool


class SkillDetailOut(Schema):
    """单条详情与写操作回执：工作区正文 + 详情出口算得出的字段（见模块 docstring）。"""

    key: str
    name: str
    title: str
    description: str
    scope: str
    scope_weight: int
    source: str
    enabled: bool
    editable: bool
    version: int
    status: str
    review_status: str
    review_note: str
    published_version: int
    has_unpublished_changes: bool
    shadowed: list[SkillShadowRef]
    body: str
    #: 服务端算出的动作权限。详情（含写操作回执）与清单必须下同一套字段，
    #: 否则「列表里能点、详情里点不了」——前端为了兼容只能自己算，那正好是
    #: 我们要禁止的事（见 ``services/skills/permissions.py`` 模块 docstring）。
    can_edit: bool
    can_submit: bool
    can_review: bool
    can_archive: bool
    can_restore: bool
    can_promote: bool


class SkillListOut(Schema):
    skills: list[SkillOut]


class SkillScopeCounts(Schema):
    """按作用域的计数（``by_scope`` 与 ``max_by_scope`` 同形；内置不占配额）。"""

    lawyer: int
    team: int
    law_firm: int


class SkillQuotaOut(Schema):
    max_skills: int
    used: int
    by_scope: SkillScopeCounts
    max_by_scope: SkillScopeCounts
    #: 能否新建所内技能（前端据此显示「新建到所内」入口，不自己判 is_admin）
    can_create_firm: bool
    #: 能把个人技能提到哪些作用域（顺序即展示顺序）；空列表 = 不显示「提升」入口
    promotable_scopes: list[str]


class SkillContentOut(Schema):
    """运行时正文分段（MCP ``get_agent_skill`` 的直接数据源）。

    ``total_bytes`` 是渲染后正文的字节数（不是字符数），``next_start`` 为 ``None``
    表示已到末尾；两者一起让调用方能「按字节续读」而不必猜分页边界。
    """

    key: str
    name: str
    title: str
    scope: str
    version: int
    content: str
    start: int
    total_bytes: int
    truncated: bool
    next_start: int | None


class SkillDiffHunk(Schema):
    """一段逐行差异：``op`` 为 ``equal`` / ``ins`` / ``del``。"""

    op: str
    lines: list[str]


class SkillDiffOut(Schema):
    v1: int
    v2: int
    hunks: list[SkillDiffHunk]


class SkillValidateIn(Schema):
    name: str | None = None
    title: str
    description: str
    body: str


class SkillFieldError(Schema):
    field: str
    message: str


class SkillSafetyFinding(Schema):
    """安全闸门的一条命中（``level`` 为 ``hard`` 拦发布 / ``soft`` 仅告警）。"""

    code: str
    level: str
    field: str
    message: str
    excerpt: str


class SkillValidateOut(Schema):
    """校验结果：``preview`` 是渲染后 AI 实际读到的内容，``safety`` 是 PII/注入命中。"""

    ok: bool
    errors: list[SkillFieldError]
    preview: str
    safety: list[SkillSafetyFinding]


class SkillCreateIn(Schema):
    """新建：缺省个人技能；``scope=law_firm`` / ``team`` 需要对应管理权限。"""

    name: str | None = None
    title: str
    description: str
    body: str
    scope: str = "lawyer"
    team_id: int | None = None


class SkillUpdateIn(Schema):
    """``version`` 是乐观锁：不符 → 409。``name`` 建后不可改（改名会断偏好与审计链）。"""

    title: str
    description: str
    body: str
    version: int


class SkillToggleIn(Schema):
    enabled: bool


class SkillToggleOut(Schema):
    key: str
    enabled: bool


class SkillSubmitIn(Schema):
    """提审：个人技能必须给 ``target_scope``（提升到团队/所内）。

    ``name`` 与 ``team_id`` 都是可选的，存在的理由是**目标层可能已经有同名技能**：
    ``uniq_agent_skill_firm_name`` / ``uniq_agent_skill_team_name`` 会让改名前的
    提升直接撞唯一约束。提审是这个唯一能改名的时机（``name`` 建后不可改的规则
    针对的是「已落库的身份」，而跨层提升本质上是一次新的落位）。
    """

    target_scope: str = ""
    note: str = ""
    acknowledged_firm_wide: bool = False
    #: 目标层已有同名技能时，用这个新名字落位（不传 = 沿用原名）
    name: str | None = None
    #: ``target_scope=team`` 时指定落到哪个团队（不传 = 取第一个律师团队）
    team_id: int | None = None


class SkillTrialIn(Schema):
    """试跑请求：不给问题就用服务端默认探针问法。"""

    question: str = ""
    #: 用哪个后端跑（默认 pi）。声明 ``skill_delivery=tool_only`` 的后端会被拒绝。
    backend: str = ""


class SkillTrialOut(Schema):
    """试跑回执。

    ``injected`` 是**实际注入给模型的那段文字**——审批人必须能看见「我们到底让模型
    看了什么」，否则一个奇怪的回答无法归因（技能写得不好？还是注入时拼错了？）。
    ``tool_calls`` 是模型在试跑里真的调用了哪些工具（只读工具面，不会有写操作）。
    """

    ok: bool
    text: str
    backend: str
    model: str | None
    duration_ms: int
    skill_key: str
    skill_name: str
    skill_scope: str
    skill_version: int
    injected: str
    tool_calls: list[str]
    error: str


class SkillReviewIn(Schema):
    """审批：``decision`` 二选一；``reject`` 必须带 ``note``（否则作者只能盲改）。"""

    decision: str
    note: str = ""
    acknowledged_firm_wide: bool = False
