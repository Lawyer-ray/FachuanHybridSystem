"""MCP ToolAnnotations 门禁:行为提示必须与审批分层权威表共源一致。

背景(2026-10-25 第五轮):server.py 统一注册口 ``_t`` 从
``apps.agent.services.approval.classify_risk`` 推导每个工具的
readOnlyHint/destructiveHint——官方参考 server 均设 annotations,
客户端可用只读徽标/免审批策略。共源的意义:annotations 不另立第三份
口径(审批已有 Python/TS 双表 parity 门禁)。

两层防护:
1. 源级:server.py 不允许再出现裸 ``mcp.tool()(`` 注册(绕过 ``_t``
   即绕过标注推导);
2. 语义级:代表性工具名的推导结果必须与 classify_risk 一致。
"""

from __future__ import annotations

# --- django setup:本测试需要 approval 表(依赖 models.TextChoices) ---
import os
import re
from pathlib import Path

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.agent.services.approval import RiskLevel, classify_risk

_SERVER_PY = Path(__file__).resolve().parents[4] / "mcp_server" / "server.py"


def _tool_annotations_from_source() -> tuple:
    """直接复用 server.py 的推导逻辑(保持单一实现,不复制算法)。"""
    import importlib

    import mcp_server.server as srv

    importlib.reload(srv)  # 确保 pytest 环境里拿到的是当前源码
    return srv._tool_annotations, srv._DESTRUCTIVE_PREFIXES


def test_no_bare_mcp_tool_registration_remains() -> None:
    """所有注册必须走统一注册口 ``_t(``,裸 mcp.tool() 会绕过标注推导。"""
    source = _SERVER_PY.read_text(encoding="utf-8")
    bare = re.findall(r"^\s*mcp\.tool\(\)\(", source, re.M)
    assert not bare, f"发现 {len(bare)} 处裸 mcp.tool() 注册(应全部走 _t)"
    assert "def _t(" in source


@pytest.mark.parametrize(
    ("name", "expect_read_only", "expect_destructive"),
    [
        ("list_cases", True, None),  # 读 → LOW → readOnly
        ("get_case", True, None),
        ("calculate_lpr_interest", True, None),  # 无副作用计算刻意 LOW
        ("chat_with_context", True, None),
        ("create_case", None, None),  # MEDIUM 普通写 → 不带标注
        ("rename_material_group", None, None),
        ("reorder_archive_materials", None, None),
        ("delete_case", None, True),  # 销毁前缀
        ("clear_cache", None, True),
        ("execute_court_filing", None, True),  # HIGH 递交类
        ("approve_contract_payment", None, True),  # 高危审批链
    ],
)
def test_annotation_matches_risk_tier(name: str, expect_read_only: bool, expect_destructive: bool) -> None:
    derive, _ = _tool_annotations_from_source()
    ann = derive(name)
    if expect_read_only is None and expect_destructive is None:
        assert ann is None, f"{name} 应为 MEDIUM 普通写(不带标注),得到 {ann}"
        return
    assert ann is not None, f"{name} 应带标注(classify_risk={classify_risk(name)})"
    assert ann.read_only_hint == expect_read_only
    assert ann.destructive_hint == expect_destructive


def test_every_registered_tool_name_derives_consistently() -> None:
    """对 tools/__all__ 全量 409 个名字,推导结果与 classify_risk 分层一致。"""
    derive, destructive_prefixes = _tool_annotations_from_source()
    tools_init = _SERVER_PY.parent / "tools" / "__init__.py"
    names: list[str] = []
    for m in re.finditer(r"__all__\s*[\+]?=\s*\[(.*?)\]", tools_init.read_text(encoding="utf-8"), re.DOTALL):
        names.extend(re.findall(r'"(\w+)"', m.group(1)))
    assert len(names) >= 400, f"__all__ 名单异常: {len(names)}"

    for name in names:
        ann = derive(name)
        level = classify_risk(name)
        if name.startswith(destructive_prefixes) or level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            assert ann is not None and ann.destructive_hint is True, f"{name} ({level}) 应标 destructive"
        elif level == RiskLevel.LOW:
            assert ann is not None and ann.read_only_hint is True, f"{name} (LOW) 应标 readOnly"
        else:
            assert ann is None, f"{name} ({level}) MEDIUM 不应带标注,得到 {ann}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
