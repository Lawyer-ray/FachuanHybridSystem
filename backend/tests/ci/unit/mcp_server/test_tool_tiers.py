"""工具面分层清单 ↔ 实际注册表对账门禁。

## 背景

工具面分层（`mcp_server/tool_tiers.py`）把 415 个工具拆成「高频直连」与
「长尾按需」两层，实测每轮省 ~88% 的工具 schema token。

但这套机制有一个**静默失效模式**：清单里写了不存在的工具名，pi 会**忽略**
该条目（不报错），于是那个工具既不直连也不按需可达——模型永远找不到它，
且**没有任何日志**。

2026-10-25 首次落地分层时就踩到了：第一批清单里 6 个名字是凭印象写的
（`list_reminders` / `search_documents` / `get_deadline_digest` /
`list_documents` / `get_document` / `list_agent_skills`），真实注册表里
一个都没有（实际是 `list_all_reminders` / `list_upcoming_deadlines` /
`list_document_templates` 等）。

本门禁对账真实注册表，幽灵工具名当场红灯。
"""

from __future__ import annotations

import fnmatch

import pytest

from mcp_server.tool_tiers import DIRECT_PATTERNS, DIRECT_TOOLS, build_tool_exposure, describe_tiers, tiers_enabled
from tests.ci.unit.mcp_server.test_server_registration import _ALL_TOOLS

#: 视为「破坏性」的工具名模式（与 approval.py 的判定口径一致）。
_DESTRUCTIVE = ("delete_", "remove_", "destroy_", "clear_all", "reset_and_")


def _is_direct(name: str) -> bool:
    """与 pi 的匹配口径一致：精确名优先，模式用 `*` 通配。"""
    if name in DIRECT_TOOLS:
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DIRECT_PATTERNS)


class TestCatalogIntegrity:
    """清单本身必须干净——这是所有分层收益的前提。"""

    def test_no_ghost_tool_names(self) -> None:
        """清单里的精确名必须真实存在于注册表。

        写错名字的后果不是报错，而是该工具**彻底不可达**（pi 忽略未知条目），
        且没有日志。这条测试就是防这个静默失效。
        """
        registered = set(_ALL_TOOLS)
        ghosts = sorted(DIRECT_TOOLS - registered)
        assert not ghosts, (
            f"工具分层清单里有 {len(ghosts)} 个不存在的工具名: {ghosts}——"
            f"pi 会静默忽略这些条目，导致对应工具既不在直连层也不在按需层可达"
        )

    def test_direct_tools_non_empty(self) -> None:
        """直连层不能空——空了等于所有工具都要 tool_search，弱模型会懵。"""
        assert DIRECT_TOOLS, "直连清单为空"
        assert len(DIRECT_TOOLS) >= 10, "直连清单过少，高频工具没覆盖到"

    def test_core_tools_are_direct(self) -> None:
        """几个「每轮几乎必用」的工具必须在直连层。"""
        must_have = {
            "get_current_user",  # 身份：AGENTS.md 要求涉及「我的」先确认
            "get_server_time",  # 时间：期限类结论的前提
            "get_agent_skill",  # 技能索引
            "list_cases",  # 最高频业务查询
            "read_agent_attachment",  # 读材料
        }
        missing = sorted(must_have - DIRECT_TOOLS)
        assert not missing, f"这些高频工具不在直连层: {missing}"


class TestDestructiveAlwaysDirect:
    """破坏性工具必须直连——这是安全要求，不是性能取舍。"""

    def test_all_destructive_tools_are_direct(self) -> None:
        """任何删除/清空类工具都必须在直连层。

        理由不是 token：律师要能一眼看见「这个 AI 有删除能力」，而审批弹窗
        里显示的工具名必须与模型选的是同一个。把破坏性工具藏进 tool_search
        只会让风险不可见，不会降低风险。

        注意：`deferred` 加载后仍以真名调用，审批链本身不受影响——所以这条
        是**产品可见性**要求，不是审批正确性要求。审批正确性由
        `test_agent_risk_tiers.py` 的 parity 测试单独守。
        """
        destructive = [name for name in _ALL_TOOLS if any(marker in name for marker in _DESTRUCTIVE)]
        assert destructive, "注册表里没有破坏性工具，对账逻辑可能失效"
        hidden = sorted(name for name in destructive if not _is_direct(name))
        assert not hidden, f"这些破坏性工具被分层藏起来了（律师将看不到 AI 的删除能力）: {hidden}"


class TestExposureMapping:
    """生成的 `toolExposure` 映射必须符合 pi 的匹配语义。"""

    def test_mapping_only_contains_valid_values(self) -> None:
        mapping = build_tool_exposure()
        assert mapping, "toolExposure 映射为空"
        assert set(mapping.values()) <= {"direct"}, (
            "本函数只负责「哪些直连」，非直连的不写条目（由服务端 exposure 兜底）"
        )

    def test_mapping_keys_are_exact_names_or_patterns(self) -> None:
        """键必须要么是真实工具名，要么是含 `*` 的模式——不能是拼错的裸名字。"""
        registered = set(_ALL_TOOLS)
        mapping = build_tool_exposure()
        bad = [key for key in mapping if key not in registered and "*" not in key]
        assert not bad, f"toolExposure 里有既不是真实工具名也不含通配符的键: {bad}"

    def test_patterns_only_match_destructive(self) -> None:
        """直连模式只应命中破坏性工具——否则模式太宽会悄悄把长尾拉回直连。"""
        for pattern in DIRECT_PATTERNS:
            matched = [n for n in _ALL_TOOLS if fnmatch.fnmatchcase(n, pattern)]
            non_destructive = [n for n in matched if not any(m in n for m in _DESTRUCTIVE)]
            assert not non_destructive, (
                f"模式 {pattern!r} 命中了非破坏性工具 {non_destructive[:5]}，会让它们绕过分层回到直连层"
            )


class TestTiersSwitch:
    def test_enabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FACHUAN_MCP_TOOL_TIERS", raising=False)
        assert tiers_enabled() is True

    def test_off_switch_rolls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`off` 是一键回滚口——出问题时不改代码就能回到全量直连。"""
        monkeypatch.setenv("FACHUAN_MCP_TOOL_TIERS", "off")
        assert tiers_enabled() is False

    def test_invalid_value_falls_back_to_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_MCP_TOOL_TIERS", "yes-please")
        assert tiers_enabled() is True

    def test_describe_tiers_mentions_counts(self) -> None:
        text = describe_tiers()
        assert "direct=" in text
        assert "按需" in text
