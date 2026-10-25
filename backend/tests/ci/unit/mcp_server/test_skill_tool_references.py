"""技能文档 ↔ 工具面对账门禁(2026-10-25 审计七十三轮)。

背景:技能文档(SKILL.md)与 pi 系统提示词(AGENTS.md)教模型「用某工具做某事」,
引用的工具名一旦不存在(改名/删除/笔误),模型会反复调用一个 404 的工具——
63 轮的「记忆 router 漏注册」就是这类漂移的实锤,但当时是人工发现。
本门禁静态扫描文档中的工具动词前缀词,与 server.py 注册清单对账,
新漂移当场红灯。零违例后门禁化,防的是未来改名时的静默漂移。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.ci.unit.mcp_server.test_server_registration import _ALL_TOOLS

_REPO = Path(__file__).resolve().parents[4]  # backend/
_SKILL_FILES = sorted((_REPO / "apps/agent/pi/skills").glob("*/SKILL.md")) + [
    _REPO / "apps/agent/pi/AGENTS.md",
]

#: 工具动词前缀——文档里以这些开头的 snake_case 词按「工具引用」核对。
#: 参数名(case_id/attachment_id)与 reason 值(blocked_target)不以动词开头,
#: 天然不在口径内,无误报面。
_TOOLISH_PREFIX = re.compile(
    r"^(get_|list_|search_|create_|update_|delete_|fetch_|parse_|extract_|read_|web_|"
    r"check_|download_|send_|add_|approve_|execute_|retry_|trigger_|sync_|preview_|"
    r"quick_|upload_|cancel_)"
)
_SNAKE_CASE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def test_skill_files_exist() -> None:
    """前提自证:文档扫描目标真实存在, glob 空结果不能让对账静默通过。"""
    assert _SKILL_FILES, "未找到技能文档——路径变更时请同步本测试"
    assert all(f.exists() for f in _SKILL_FILES)


def test_referenced_tool_names_are_registered() -> None:
    missing: list[tuple[str, str]] = []
    for doc in _SKILL_FILES:
        words = set(_SNAKE_CASE.findall(doc.read_text()))
        toolish = {w for w in words if _TOOLISH_PREFIX.match(w)}
        for name in sorted(toolish - set(_ALL_TOOLS)):
            missing.append((doc.name, name))
    assert not missing, (
        f"文档引用了未注册的工具名(改名/删除后文档没跟上?): {missing}——"
        f"要么改文档,要么确认工具已在 mcp_server/server.py 注册"
    )
