"""技能面门面：内置库 + 个人技能 + 用户偏好（既有 import 路径的唯一入口）。

## 技能面与工具面的分工

- **工具面**（mcp_server）：``get_agent_skill`` 按名读技能全文——模型在
  对话中**自主**判断场景后查阅，路径在 ``mcp_server/tools/core/agent_skills.py``。
- **技能面**（本模块 + rpc_client）：把技能目录经 ``--skill`` 注入 pi，
  使律师能在输入框用 ``/skill:名字`` **显式点名**（pi 在发给模型前展开全文）。

## 为什么这个文件只是一层门面

``pi_backend.py:43`` 与 ``api/skill_api.py`` 依赖这里的公开签名，实现整体
搬进 ``services/skills/`` 子包（P0-BRIEF §1.3），本文件只做转发。
``AgentSkillPreference`` 只记差异：内置技能没有数据库行，偏好缺省即启用。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .skills import library, resolve, store, user_skills
from .skills.constants import NAME_RE
from .skills.errors import SkillNotFound

logger = logging.getLogger(__name__)


def skills_root() -> Path:
    """技能库根目录（内置技能：环境变量优先，缺省随代码发布的仓库内路径）。"""
    return library.skills_root()


def list_skills() -> list[dict]:
    """扫描技能库，返回按 name 排序的内置技能条目。"""
    return library.builtin_skills()


def skills_for_user(user_id: int) -> list[dict]:
    """技能清单：内置 + 个人（含禁用项与 ``shadowed``，字段见 P0-BRIEF §1.6）。"""
    return user_skills.list_for_user(user_id)


def enabled_skill_paths(user_id: int) -> list[str]:
    """该用户启用的技能目录绝对路径（逐个 ``--skill`` 注入 pi）。

    个人技能的目录由 ``transaction.on_commit`` 物化；这里**不写盘**，目录缺失
    就跳过并告警（``skills_reconcile`` 可重建）。缺失不报错是刻意的：一个用户
    的磁盘问题不该让整轮对话挂掉。
    """
    skills = resolve.resolve_for_user(user_id)
    personal_root: Path | None = None
    if any(s["source"] != "builtin" for s in skills):
        try:
            # 只取路径，**不建目录**（见 store.root_path 的注释）：本函数在每轮
            # 对话的热路径上，磁盘异常不能让整轮挂掉。
            personal_root = store.root_path(int(user_id))
        except OSError:
            logger.warning("个人技能根目录不可用，本轮只注入内置技能", exc_info=True)
    paths: list[str] = []
    for skill in skills:
        root = skills_root() if skill["source"] == "builtin" else personal_root
        candidate = root / skill["name"] if root is not None else None
        if candidate is not None and candidate.is_dir():
            paths.append(str(candidate))
        elif skill["source"] != "builtin":
            logger.warning("个人技能目录缺失，已跳过注入（运行 manage.py skills_reconcile 可修复）: %s", candidate)
        else:
            logger.warning("内置技能目录缺失，已跳过注入: %s", candidate)
    return paths


def set_skill_enabled(user_id: int, key: str, enabled: bool) -> dict[str, object]:
    """设置技能启停状态（幂等 upsert；``key`` 兼容裸内置名，自动补 ``builtin:``）。

    Raises:
        ValueError: 内置技能名非法或不在库内（与改造前的公开行为一致）。
    """
    normalized = (key or "").strip()
    if normalized.startswith("skill:"):
        try:
            return user_skills.set_enabled(user_id=user_id, key=normalized, enabled=enabled)
        except SkillNotFound as exc:
            raise ValueError(str(exc)) from exc
    name = normalized[len("builtin:") :] if normalized.startswith("builtin:") else normalized
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"非法技能名: {key!r}")
    if name not in library.builtin_names():
        raise ValueError(f"未知技能: {key!r}")
    return user_skills.set_enabled(user_id=user_id, key=f"builtin:{name}", enabled=enabled)
