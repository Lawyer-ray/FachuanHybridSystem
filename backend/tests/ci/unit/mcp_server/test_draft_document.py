"""MCP 工具 `draft_document`：必须在工具面里、必须判中级、payload 必须对上 REST 契约。

## 三条断言各自防的事故

| 断言 | 不守会怎样 |
|---|---|
| 注册进工具面 | 工具写完不注册没有任何报错，模型只会说「没有这个工具」，重启也修不了 |
| `classify_risk` = MEDIUM | 判 LOW 就是 `readOnlyHint=True` + 零留痕，模型可以静默起草并消耗模型额度 |
| payload 键与 REST 一致 | 键名漂移后端只丢参数不报错，表现是「生成了但没落到你说的位置」 |
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_server.tools.documents import draft as draft_tool


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((path, kwargs))
        return {"created": True, "file_url": "/api/v1/cases/1017/folder-file?subpath=x.docx"}


def test_draft_document_is_registered_in_the_tool_surface() -> None:
    from mcp_server.server import mcp

    assert "draft_document" in dict(mcp._tool_manager._tools)


def test_draft_document_is_medium_risk() -> None:
    """会落盘 + 触发模型调用，但同名不覆盖、可删稿重来 → 中级（静默放行 + 审计留痕）。"""
    from apps.agent.services.approval import RiskLevel, classify_risk

    assert classify_risk("draft_document") == RiskLevel.MEDIUM
    assert classify_risk("mcp__fachuan__draft_document") == RiskLevel.MEDIUM


def test_posts_the_documented_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(draft_tool, "client", fake)

    result = draft_tool.draft_document(
        doc_type=" 管辖权异议申请书 ",
        case_id=1017,
        facts={"异议人": "甲公司"},
        instruction="只写管辖问题",
    )

    assert result["created"] is True
    path, kwargs = fake.calls[0]
    assert path == "/doc-workspace/draft-by-type"
    assert kwargs["json"] == {
        "doc_type": "管辖权异议申请书",
        "case_id": 1017,
        "contract_id": None,
        "facts": {"异议人": "甲公司"},
        "instruction": "只写管辖问题",
        # 批注署名随请求走（缺省空串，后端回落 Lawyer）；不做系统配置
        "comment_author": "",
        # 起草前先判材料够不够（默认开）；材料是 blocking 时要想出草稿得显式 force
        "assess_first": True,
        "force": False,
    }


def test_requires_exactly_one_owner_id() -> None:
    """两个都不给就没有落点，两个都给说明引用块读串了——都直接拒绝，不猜。"""
    with pytest.raises(ValueError, match="二选一"):
        draft_tool.draft_document(doc_type="起诉状")
    with pytest.raises(ValueError, match="二选一"):
        draft_tool.draft_document(doc_type="起诉状", case_id=1, contract_id=2)


def test_docstring_states_the_three_boundaries() -> None:
    """工具描述是模型唯一能读到的「边界声明」，三件事必须写在里面。"""
    doc = draft_tool.draft_document.__doc__ or ""

    assert "不会自由排版" in doc
    assert "会落盘" in doc
    assert "批注" in doc
