"""技能清单 / 详情 / 校验 / 启停的请求响应契约（P0-BRIEF §1.5–§1.6）。

字段口径：``key`` 是身份（``builtin:<name>`` / ``skill:<uuid>``），``name`` 是
命令名与目录名。内置技能 ``scope`` 用空串，前端按 ``source`` 分支而不是靠
``scope`` 判空。
"""

from __future__ import annotations

from ninja import Schema


class SkillOut(Schema):
    """清单项（``shadowed`` 不进 P0 契约，前端暂不展示覆盖关系）。"""

    key: str
    name: str
    title: str
    description: str
    enabled: bool
    source: str
    scope: str
    editable: bool
    version: int


class SkillDetailOut(SkillOut):
    """详情：多一个可编辑正文。"""

    body: str


class SkillListOut(Schema):
    skills: list[SkillOut]


class SkillQuotaOut(Schema):
    max_skills: int
    used: int


class SkillValidateIn(Schema):
    name: str | None = None
    title: str
    description: str
    body: str


class SkillFieldError(Schema):
    field: str
    message: str


class SkillValidateOut(Schema):
    """校验结果：``preview`` 是渲染后 AI 实际读到的内容。"""

    ok: bool
    errors: list[SkillFieldError]
    preview: str


class SkillCreateIn(Schema):
    name: str | None = None
    title: str
    description: str
    body: str


class SkillUpdateIn(Schema):
    """``version`` 是乐观锁：不符 → 409。``name`` 不可改。"""

    title: str
    description: str
    body: str
    version: int


class SkillToggleIn(Schema):
    enabled: bool


class SkillToggleOut(Schema):
    key: str
    enabled: bool
