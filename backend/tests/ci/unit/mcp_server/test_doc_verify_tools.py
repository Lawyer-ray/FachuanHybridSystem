"""回传件核对 MCP 工具：**请求方法 + 完整路径 + 参数名**。

## 为什么要按路径逐条断言

MCP 工具就是薄 HTTP 客户端，它最容易的静默失效是路径写错（漏掉 router 挂载前缀
`/doc-verify`，或把 `/pending` 写成 `/unverified`）。写错时不会抛异常，模型只会拿到
404 并把「没有待裁决」当成结论——比报错危险得多。

## 为什么要区分 case_id 有无

两种口径走**两个不同的端点**：有 case_id 看该案（`/unverified`），没有看跨案待办
（`/pending`）。这条分支是本功能的产品核心（律师既可能问「这案」也可能问「今天」），
写反了不会报错，只会一直返回空。
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_server.tools import doc_verify as tools_mod
from mcp_server.tools.doc_verify import get_returned_document_check, list_unverified_returns, verify_returned_document


class _FakeClient:
    """记录调用形状的假 client：断言的就是它记下来的东西。"""

    def __init__(self, payload: Any = None) -> None:
        self.payload = {"items": []} if payload is None else payload
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def get(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", path, kwargs))
        return self.payload

    def post(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", path, kwargs))
        return self.payload


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(tools_mod, "client", client)
    return client


def test_case_scoped_call_hits_unverified(fake: _FakeClient) -> None:
    list_unverified_returns(case_id=42)

    assert fake.calls == [("GET", "/doc-verify/unverified", {"params": {"case_id": 42}})]


def test_cross_case_call_hits_pending_with_limit(fake: _FakeClient) -> None:
    """不传 case_id = 跨案待办口径，走 /pending 而不是 /unverified（后者必须带 case_id）。"""
    list_unverified_returns(limit=20)

    assert fake.calls == [("GET", "/doc-verify/pending", {"params": {"limit": 20}})]


def test_get_check_hits_run_detail(fake: _FakeClient) -> None:
    get_returned_document_check(run_id=7)

    assert fake.calls == [("GET", "/doc-verify/runs/7", {})]


def test_verify_posts_to_runs_with_payload(fake: _FakeClient) -> None:
    verify_returned_document(artifact_id=3, file_base64="QUJD", file_name="回传.pdf", tier=1)

    assert len(fake.calls) == 1
    method, path, kwargs = fake.calls[0]
    assert (method, path) == ("POST", "/doc-verify/runs")
    assert kwargs["json"] == {
        "artifact_id": 3,
        "file_base64": "QUJD",
        "file_name": "回传.pdf",
        "tier": 1,
    }


def test_verify_omits_tier_when_unspecified(fake: _FakeClient) -> None:
    """不传 tier = 交给后端自动升级（勾了核对 + 扫描件 → OCR 层），别硬塞 0 把升级挡掉。"""
    verify_returned_document(artifact_id=3, file_base64="QUJD")

    payload = fake.calls[0][2]["json"]
    assert "tier" not in payload
    # 没给文件名就不传这个键（后端默认空串），别在载荷里塞空值制造两个"没填"的表达
    assert "file_name" not in payload


def test_verify_is_registered_as_a_write_tool() -> None:
    """`verify_` 必须在写前缀里：漏了就被判 LOW（无留痕），而它确实会落一条核对运行。"""
    from apps.agent.services.approval.risk import WRITE_PREFIXES, classify_risk

    assert "verify_" in WRITE_PREFIXES
    assert classify_risk("verify_returned_document", {}) != "low"
