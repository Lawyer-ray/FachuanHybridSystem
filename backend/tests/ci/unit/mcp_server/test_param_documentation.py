"""参数文档门禁——多参工具的 docstring 必须提及参数(2026-10-25 二十一轮)。

## 背景

SDK 把**整个 docstring** 当工具描述(``base.py`` 不解析 Args 段),JSON schema
里的参数只有名字和类型——参数语义若在 docstring 里完全没出现,模型只能靠猜
(实测 269/409 工具存在参数未提及,其中 23 个**零提及且 ≥3 参**,含
merge_id_card_manual 的四角坐标、mortgage_default_calculate 的罚息参数这类
不猜不可能对的领域参数)。2026-10-25 已把最糟的 23 个全部补齐 Args 段。

## 门禁口径

- 只拦「零提及且 ≥3 参」的最糟类(全文档级覆盖 269 个不在本轮范围);
- 参数名出现在 docstring 任意位置即算提及(Args 段、行文均可);
- ``user`` 是内部身份参数,不计。
"""

from __future__ import annotations

import inspect
from typing import Any


def _registered() -> dict[str, Any]:
    from mcp_server.server import mcp

    return dict(mcp._tool_manager._tools)


def _worst_class() -> list[str]:
    findings: list[str] = []
    for name, fn in sorted(_registered().items()):
        inner: Any = inspect.unwrap(fn.fn if hasattr(fn, "fn") else fn)
        doc = inspect.getdoc(inner) or ""
        if not doc:
            findings.append(f"{name}: 无 docstring")
            continue
        params = [p for p in inspect.signature(inner).parameters if p != "user"]
        if len(params) >= 3 and not any(p in doc for p in params):
            findings.append(f"{name}: {len(params)} 个参数全部未在 docstring 提及")
    return findings


def test_multi_param_tools_document_their_params():
    findings = _worst_class()
    assert not findings, (
        "≥3 参工具的 docstring 对参数零提及——模型只能瞎猜(补 Args 段,参数语义写清):\n  - "
        + "\n  - ".join(findings)
    )
