"""Agent 专项技能指引 —— 按需向模型提供场景化操作说明。

## 为什么是一个工具而不是全部塞进系统提示词

系统提示词（AGENTS.md）每轮全量注入：全部 395+ 工具的操作指引如果常驻，
上下文成本高且不聚焦。把场景化指引拆成技能包（SKILL.md，Agent Skills
规范格式），AGENTS.md 只保留一行路由，模型遇到对应场景时用本工具按名
取全文——「按需加载」。

pi 原生 Skills 机制要求模型用 read/bash 工具读技能文件，而本系统出于
安全不向模型声明任何文件读取工具（防提示注入直通服务器文件面），所以
技能内容经由 MCP 工具面供给：静态内容、不调 REST、不碰用户数据，
与「工具面只在 mcp__fachuan__」的原则一致。

## 安全

- 只读随代码发布的静态文件，无用户数据面；
- 名称白名单 = 技能目录下实际存在的子目录名（先正则后实存双校验），
  路径穿越（``../``、斜杠、绝对路径）一律拒绝。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

#: 技能包根目录：apps/agent/pi/skills（与 AGENTS.md 模板同处，随代码发布）
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[3] / "apps" / "agent" / "pi" / "skills"

#: 合法技能名：小写字母/数字/连字符（Agent Skills 规范），不含路径分隔符
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: 部署异位（如容器内路径不同）时的覆盖入口
_SKILLS_DIR_ENV = "FACHUAN_AGENT_SKILLS_DIR"


def _skills_root() -> Path:
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_SKILLS_ROOT


def available_skill_names() -> list[str]:
    """当前技能包目录下全部可用技能名（按目录名排序，供错误提示与测试）。"""
    root = _skills_root()
    if not root.is_dir():
        return []
    return sorted(p.parent.name for p in root.glob("*/SKILL.md"))


def get_agent_skill(name: str) -> dict[str, Any]:
    """读取一份 agent 专项操作指引的全文。

    遇到以下场景时，先调用本工具读取对应指引再决定用哪些工具、怎么传参：
    - 期限 / 排期 / 开庭 / 到期 / 异步任务进度 → ``deadline-queries``
    - 列表 / 汇总 / 统计 / 取明细 → ``list-projection``
    - 读材料 / 解析文档 / 提取正文表格 → ``materials-parsing``
    - 联网搜索 / 查法条 / 抓网页原文 → ``web-research``

    返回 ``name`` 与 ``content``（Markdown 全文，含 frontmatter）。
    """
    normalized = (name or "").strip().lower()
    if not _NAME_RE.fullmatch(normalized):
        raise ValueError(f"非法技能名: {name!r}")
    skill_file = _skills_root() / normalized / "SKILL.md"
    # 双校验：正则已挡住路径分隔符；resolve 后必须仍在技能根目录内（防 symlink 逃逸）
    if not skill_file.is_file() or skill_file.resolve().parent.parent != _skills_root().resolve():
        available = ", ".join(available_skill_names()) or "（无）"
        raise ValueError(f"未知技能: {name!r}，可用技能: {available}")
    content = skill_file.read_text(encoding="utf-8")
    return {"name": normalized, "content": content}
