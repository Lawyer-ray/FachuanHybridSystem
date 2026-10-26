"""技能库读取与用户偏好（skill 面的数据源）。

## 技能面与工具面的分工

- **工具面**（mcp_server）：``get_agent_skill`` 按名读技能全文——模型在
  对话中**自主**判断场景后查阅，路径在 ``mcp_server/tools/core/agent_skills.py``。
- **技能面**（本模块 + rpc_client）：把技能目录经 ``--skill`` 注入 pi，
  使律师能在输入框用 ``/技能名`` **显式点名**（pi 在发给模型前展开全文）。
  两个通道共用同一份技能库（``pi/skills/``），互不排斥。

## 用户偏好的表达位置

技能库目录（``PI_CODING_AGENT_DIR``）是全所共享的稳定目录，**不能**靠
「往目录里放/删文件」表达某个用户的启用状态——所以差异落本表
（``AgentSkillPreference``），会话启动时按用户算出启用清单、逐个
``--skill`` 注入（见 ``rpc_client.PiRpcSession``）。默认全启用：新技能
上线即刻可用，不要求给每个用户补一行数据。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from apps.agent.models.agent import AgentSkillPreference

logger = logging.getLogger(__name__)

#: 技能库根目录：apps/agent/pi/skills（与 AGENTS.md 模板同处，随代码发布）
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "pi" / "skills"

#: 合法技能名：小写字母/数字/连字符（Agent Skills 规范），不含路径分隔符。
#: 与 mcp_server/tools/core/agent_skills.py 的 ``_NAME_RE`` 同构。
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: 部署异位（如容器内路径不同）时的覆盖入口，与 mcp_server 侧同名变量一致
_SKILLS_DIR_ENV = "FACHUAN_AGENT_SKILLS_DIR"

#: SKILL.md frontmatter 里本模块关心的两行（name / description）
_FRONTMATTER_LINE = re.compile(r"^(name|description):\s*(.+)$", re.MULTILINE)


def skills_root() -> Path:
    """技能库根目录（环境变量优先，缺省随代码发布的仓库内路径）。"""
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_SKILLS_ROOT


def _parse_skill_file(skill_dir: Path) -> dict[str, str] | None:
    """读一份 SKILL.md 的 frontmatter，返回 ``{name, description}``。

    只认文件头部的 frontmatter 块（``---`` 包裹）；name 缺失时用目录名兜底
    （pi 侧同样以目录名/文件名兜底，两边口径一致）。
    """
    skill_file = skill_dir / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        logger.warning("技能文件不可读: %s", skill_file, exc_info=True)
        return None
    fields = dict(_FRONTMATTER_LINE.findall(content.split("---", 2)[1] if "---" in content else ""))
    name = fields.get("name", "").strip() or skill_dir.name
    return {"name": name, "description": fields.get("description", "").strip()}


def list_skills() -> list[dict[str, str]]:
    """扫描技能库，返回按 name 排序的 ``[{name, description}]``。"""
    root = skills_root()
    if not root.is_dir():
        return []
    results: list[dict[str, str]] = []
    for skill_file in sorted(root.glob("*/SKILL.md")):
        parsed = _parse_skill_file(skill_file.parent)
        if parsed is not None:
            results.append(parsed)
    return results


def skills_for_user(user_id: int) -> list[dict]:
    """技能清单合并用户偏好（偏好只记差异，缺省启用）。"""
    skills = list_skills()
    if not skills:
        return []
    disabled = set(
        AgentSkillPreference.objects.filter(user_id=user_id, enabled=False).values_list("skill_name", flat=True)
    )
    return [{**skill, "enabled": skill["name"] not in disabled} for skill in skills]


def enabled_skill_paths(user_id: int) -> list[str]:
    """该用户启用的技能目录绝对路径（逐个 ``--skill`` 注入 pi）。"""
    root = skills_root()
    return [
        str(root / skill["name"])
        for skill in skills_for_user(user_id)
        if skill["enabled"] and (root / skill["name"]).is_dir()
    ]


def set_skill_enabled(user_id: int, skill_name: str, enabled: bool) -> dict[str, object]:
    """设置某用户的技能启用状态（幂等 upsert）。

    Raises:
        ValueError: 技能名不在库内（先正则后实存双校验，与 mcp_server 同口径）。
    """
    normalized = (skill_name or "").strip()
    if not _NAME_RE.fullmatch(normalized):
        raise ValueError(f"非法技能名: {skill_name!r}")
    known_names = {skill["name"] for skill in list_skills()}
    if normalized not in known_names:
        raise ValueError(f"未知技能: {skill_name!r}")
    AgentSkillPreference.objects.update_or_create(
        user_id=user_id,
        skill_name=normalized,
        defaults={"enabled": enabled},
    )
    return {"name": normalized, "enabled": enabled}
