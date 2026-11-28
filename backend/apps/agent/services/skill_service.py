"""技能面门面：内置库 + 数据库技能 + 用户偏好（既有 import 路径的唯一入口）。

## 技能面的三条交付通道

方案 A 之后，技能到模型的路径只有三条，全部由 ``services/skills/`` 提供：

1. **显式点名**：``services/skills/expand.py`` 在编排层把 ``/skill:名字`` 展开成
   正文（锚点感知，全后端统一——pi 原生展开会被 ``[当前业务：…]`` 前缀打断）。
2. **自主发现**：``services/skills/prompt_block.py`` 渲染索引块，后端经系统提示
   注入（pi 走 ``--append-system-prompt``）。
3. **按需取全文**：MCP ``get_agent_skill`` → ``GET /agent/skills/resolve/{ref}/content``。

**没有第四条**：不再有「把技能目录物化到磁盘再 ``--skill`` 注入 pi」这条路。
详见 ``services/skills/user_skills.py`` 模块 docstring 的取证。

## 为什么这个文件只是一层门面

``pi_backend.py`` 与 ``api/skill_api.py`` 依赖这里的公开签名，实现整体在
``services/skills/`` 子包（P0-BRIEF §1.3），本文件只做转发。
"""

from __future__ import annotations

from pathlib import Path

from .skills import flags, library, resolve, user_skills
from .skills.constants import NAME_RE
from .skills.errors import SkillNotFound


def skills_root() -> Path:
    """技能库根目录（内置技能：环境变量优先，缺省随代码发布的仓库内路径）。"""
    return library.skills_root()


def list_skills() -> list[dict]:
    """扫描技能库，返回按 name 排序的内置技能条目。"""
    return library.builtin_skills()


def skills_for_user(user_id: int) -> list[dict]:
    """技能清单：该律师可见的全部条目（含禁用项与 ``shadowed``）。"""
    return user_skills.list_for_user(user_id)


def deliverable_skills(user_id: int) -> list[dict]:
    """本轮可交付的技能（已启用 + 已生效，共享取线上已审批版）。"""
    return resolve.resolve_for_user(user_id)


def user_skills_mode() -> str:
    """总开关当前档位（``on`` / ``dry`` / ``off``，见 ``skills/flags.py``）。"""
    return flags.user_skills_mode()


def set_skill_enabled(user_id: int, key: str, enabled: bool) -> dict[str, object]:
    """设置技能启停状态（幂等 upsert；``key`` 兼容裸内置名，自动补 ``builtin:``）。

    Raises:
        ValueError: 内置技能名非法或不在库内（与改造前的公开行为一致）。
        SkillNotFound: 数据库技能不存在或不在可见范围内。
        SkillForbidden: 运营开关关闭，或该技能已下线。
    """
    normalized = (key or "").strip()
    if normalized.startswith("skill:"):
        return user_skills.set_enabled(user_id=user_id, key=normalized, enabled=enabled)
    builtin_name = normalized[len("builtin:") :] if normalized.startswith("builtin:") else normalized
    if not NAME_RE.fullmatch(builtin_name or ""):
        raise ValueError(f"非法技能名: {key!r}")
    builtin = {skill["name"]: skill for skill in library.builtin_skills()}
    if builtin_name not in builtin:
        # 裸名字还可能是数据库技能（前端旧版只传 name）：再试一次，仍失败才报错。
        try:
            return user_skills.set_enabled(user_id=user_id, key=builtin_name, enabled=enabled)
        except SkillNotFound:
            raise ValueError(f"未知技能: {key!r}") from None
    return user_skills.set_enabled(user_id=user_id, key=f"builtin:{builtin_name}", enabled=enabled)
