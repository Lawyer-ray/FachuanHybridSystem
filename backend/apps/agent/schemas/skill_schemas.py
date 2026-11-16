"""技能清单与启停的请求响应契约。"""

from __future__ import annotations

from ninja import Schema


class SkillOut(Schema):
    """技能清单项。``description`` 来自 SKILL.md frontmatter。"""

    name: str
    description: str
    enabled: bool


class SkillListOut(Schema):
    skills: list[SkillOut]


class SkillToggleIn(Schema):
    enabled: bool


class SkillToggleOut(Schema):
    name: str
    enabled: bool
