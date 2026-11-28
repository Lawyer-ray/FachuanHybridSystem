"""内置技能库（``pi/skills/<name>/SKILL.md``，随代码发布）的扫描与读取。

解析逻辑搬自原 ``services/skill_service.py``：只认文件头部的 frontmatter 块，
``name`` 缺失时用目录名兜底（pi 侧同样以目录名兜底，两边口径一致）。

## 为什么加进程内缓存

方案 A 之后本模块在**每轮对话的热路径**上：``resolve_for_user`` 要拿内置清单做
级联、``prompt_block`` 要拿描述做索引、``expand`` 要拿正文展开。每次对话扫一遍
目录 + 读 4 个文件在单机看不出来，但池化 4 槽满载时就是每秒几十次 read。

缓存键是**目录路径**，值是 ``(目录 mtime_ns, 条目列表)``：技能库随代码发布，
改它必然伴随部署（目录 mtime 会变），所以 mtime 判等就足够安全，不需要文件级
watch。进程内字典而不是 ``lru_cache``——后者没法在测试里清空，而测试要能在同一
进程里换 ``FACHUAN_AGENT_SKILLS_DIR``。

**正文不进缓存**：``read_body`` 只在「复制为我的」与「详情」这类低频路径上调用，
缓存正文会把律师可能正在改的大文件常驻内存，收益与风险不成比例。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .constants import BUILTIN_PREFIX, BUILTIN_RANK

logger = logging.getLogger(__name__)

#: 技能库根目录：apps/agent/pi/skills（与 AGENTS.md 模板同处，随代码发布）
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "pi" / "skills"

#: 部署异位（如容器内路径不同）时的覆盖入口，与 mcp_server 侧同名变量一致
_SKILLS_DIR_ENV = "FACHUAN_AGENT_SKILLS_DIR"

#: SKILL.md frontmatter 里本模块关心的两行（name / description）
_FRONTMATTER_LINE = re.compile(r"^(name|description):\s*(.+)$", re.MULTILINE)

#: 目录路径 → (mtime_ns, 条目列表)。见模块 docstring「为什么加进程内缓存」。
_cache: dict[str, tuple[int, list[dict]]] = {}


def skills_root() -> Path:
    """技能库根目录（环境变量优先，缺省随代码发布的仓库内路径）。"""
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_SKILLS_ROOT


def clear_cache() -> None:
    """清空扫描缓存（测试用；部署换库时也可在线调后重启无关）。"""
    _cache.clear()


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
    """扫描技能库，返回按 name 排序的内置技能条目。

    条目的字段形状与 ``resolve`` 的输出**刻意对齐**（含 ``scope`` / ``scope_weight``）：
    调用方拿到内置条目与数据库条目之后可以直接拼在一起级联，不必两套形状互相转换。
    """
    root = skills_root()
    if not root.is_dir():
        return []
    try:
        mtime = root.stat().st_mtime_ns
    except OSError:  # pragma: no cover - 目录刚被删掉
        logger.warning("技能库目录不可读: %s", root, exc_info=True)
        return []
    cache_key = str(root)
    cached = _cache.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
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
                "scope": "builtin",
                "scope_weight": BUILTIN_RANK,
                "editable": False,
                "version": 0,
                "status": "active",
                "review_status": "none",
            }
        )
    _cache[cache_key] = (mtime, results)
    return results


def builtin_names() -> set[str]:
    """内置技能名集合（= 个人技能不得占用的保留名）。"""
    return {skill["name"] for skill in builtin_skills()}
