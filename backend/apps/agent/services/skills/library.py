"""内置技能库（``pi/skills/<name>/SKILL.md``，随代码发布）的扫描与读取。

解析逻辑搬自原 ``services/skill_service.py``：只认文件头部的 frontmatter 块，
``name`` 缺失时用目录名兜底（pi 侧同样以目录名兜底，两边口径一致）。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .constants import BUILTIN_PREFIX

logger = logging.getLogger(__name__)

#: 技能库根目录：apps/agent/pi/skills（与 AGENTS.md 模板同处，随代码发布）
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "pi" / "skills"

#: 部署异位（如容器内路径不同）时的覆盖入口，与 mcp_server 侧同名变量一致
_SKILLS_DIR_ENV = "FACHUAN_AGENT_SKILLS_DIR"

#: SKILL.md frontmatter 里本模块关心的两行（name / description）
_FRONTMATTER_LINE = re.compile(r"^(name|description):\s*(.+)$", re.MULTILINE)


def skills_root() -> Path:
    """技能库根目录（环境变量优先，缺省随代码发布的仓库内路径）。"""
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_SKILLS_ROOT


def read_skill_file(name: str) -> str | None:
    """读一份内置技能的 SKILL.md 全文（复制内置技能时用）；不可读返回 ``None``。"""
    skill_file = skills_root() / name / "SKILL.md"
    try:
        return skill_file.read_text(encoding="utf-8")
    except OSError:
        logger.warning("内置技能文件不可读: %s", skill_file, exc_info=True)
        return None


def read_body(name: str) -> str:
    """内置技能的正文（去掉 frontmatter 块），供「复制为我的」预填。"""
    content = read_skill_file(name)
    if content is None:
        return ""
    parts = content.split("---", 2)
    return parts[2].strip() if len(parts) == 3 else content.strip()


def _parse_skill_file(skill_dir: Path) -> dict[str, str] | None:
    """读一份 SKILL.md 的 frontmatter，返回 ``{name, description}``。"""
    skill_file = skill_dir / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        logger.warning("技能文件不可读: %s", skill_file, exc_info=True)
        return None
    fields = dict(_FRONTMATTER_LINE.findall(content.split("---", 2)[1] if "---" in content else ""))
    name = fields.get("name", "").strip() or skill_dir.name
    return {"name": name, "description": fields.get("description", "").strip()}


def builtin_skills() -> list[dict]:
    """扫描技能库，返回按 name 排序的内置技能条目（清单字段见 P0-BRIEF §1.6）。"""
    root = skills_root()
    if not root.is_dir():
        return []
    results: list[dict] = []
    for skill_file in sorted(root.glob("*/SKILL.md")):
        parsed = _parse_skill_file(skill_file.parent)
        if parsed is None:
            continue
        results.append(
            {
                "key": f"{BUILTIN_PREFIX}{parsed['name']}",
                "name": parsed["name"],
                "title": parsed["name"],
                "description": parsed["description"],
                "source": "builtin",
                "scope": "",
                "editable": False,
                "version": 0,
            }
        )
    return results


def builtin_names() -> set[str]:
    """内置技能名集合（= 个人技能不得占用的保留名）。"""
    return {skill["name"] for skill in builtin_skills()}
