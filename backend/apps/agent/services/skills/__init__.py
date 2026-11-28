"""Agent 技能子包：解析 / 渲染 / 校验 / 交付 / 闸门。

模块职责（单个文件 ≤300 行）：

- ``constants``：name 正则、配额与长度上限、保留命令、作用域权重与标签
- ``flags``：总开关 ``FACHUAN_AGENT_USER_SKILLS``（on / dry / off）
- ``errors``：领域异常（API 层翻译成 HTTP 状态码）
- ``library``：内置技能（``pi/skills/*/SKILL.md``）扫描与正文读取（带 mtime 缓存）
- ``validation``：表单归一化 + 字段级校验（纯函数）
- ``render``：交付文本渲染（frontmatter 白名单 + 按作用域的来源声明，纯函数）
- ``safety``：两级 PII / 提示注入闸门（共享技能提审与发布时用）
- ``resolve``：**唯一解析入口**（可见集 + 偏好过滤 + 级联去重）
- ``permissions``：谁能编辑 / 提审 / 审批 / 下线（服务端唯一判据）
- ``review``：双轨发布生命周期（提审 / 通过 / 驳回 / 下线 / 恢复 / 裁剪版本）
- ``user_skills``：技能 CRUD 门面（事务、版本、配额）
- ``expand``：编排层 ``/skill:`` 展开（锚点感知，全后端统一）
- ``prompt_block``：系统提示里的技能索引（预算裁剪、稳定排序）

``services/skill_service.py`` 只是本包的门面，既有 import 路径不变。
"""

from __future__ import annotations

from .library import builtin_names, builtin_skills, read_body, skills_root
from .render import render_skill_body, render_skill_md, scope_label, scope_preamble
from .resolve import list_visible_skills, resolve_for_user

__all__ = [
    "builtin_names",
    "builtin_skills",
    "list_visible_skills",
    "read_body",
    "render_skill_body",
    "render_skill_md",
    "resolve_for_user",
    "scope_label",
    "scope_preamble",
    "skills_root",
]
