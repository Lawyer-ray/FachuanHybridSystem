"""个人技能子包：内置库扫描 / 校验 / 渲染 / 物化 / 解析 / CRUD。

模块职责（单个文件 ≤300 行）：

- ``constants``：name 正则、配额与长度上限、保留命令、``SCOPE_RANK``
- ``library``：内置技能（``pi/skills/*/SKILL.md``）扫描与正文读取
- ``validation``：表单归一化 + 字段级校验（纯函数）
- ``render``：``SKILL.md`` 渲染（frontmatter 白名单，纯函数）
- ``store``：物化落盘（原子写、幂等、prune）
- ``resolve``：**唯一解析入口**（可见集 + 级联去重 + 偏好过滤）
- ``user_skills``：个人技能 CRUD（事务、版本、配额）
- ``errors``：领域异常（API 层翻译成 HTTP 状态码）

``services/skill_service.py`` 只是本包的门面，既有 import 路径不变。
"""

from __future__ import annotations

from .library import builtin_names, builtin_skills, read_body, skills_root
from .render import render_skill_md
from .resolve import resolve_for_user, visible_skills

__all__ = [
    "builtin_names",
    "builtin_skills",
    "read_body",
    "render_skill_md",
    "resolve_for_user",
    "skills_root",
    "visible_skills",
]
