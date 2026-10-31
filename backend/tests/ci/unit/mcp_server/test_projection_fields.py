"""投影字段契约:工具默认投影列出的字段必须是 API 真实返回的字段。

背景（2026-10-25 审计）:``list_cases`` / ``list_contracts`` 走「精简投影」
降 token——投影里列了一个 API 不返回的字段时,模型按 docstring 点名要它
(``fields=["xxx"]``)会**静默拿到更少字段**（project 只是按键挑选,不会报错）,
或默认投影承诺的字段悄悄缺失。此测试把投影清单与 OpenAPI 逐字段对账。
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.django_db

from apiSystem.api import api
from mcp_server.tools.core.projection import CASE_LIST_FIELDS, CONTRACT_LIST_FIELDS

#: 端点后缀 → (投影清单, 响应里 items 数组的定位键链)。
#: contracts 是分页信封 {items: [...]}, cases 是裸数组。
_TARGETS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("/cases/cases", CASE_LIST_FIELDS, ()),
    ("/contracts/contracts", CONTRACT_LIST_FIELDS, ("items",)),
)


def _openapi_spec() -> Any:
    return api.get_openapi_schema()


def _resolve_ref(spec: Any, schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        schema = spec["components"]["schemas"][ref]
    return schema


def _item_props(spec: Any, path_suffix: str, item_keys: tuple[str, ...]) -> set[str]:
    """定位端点 2xx 响应里列表元素 schema 的属性名集合。"""
    for path, ops in spec["paths"].items():
        if not path.endswith(path_suffix):
            continue
        op = ops.get("get")
        if op is None:
            continue
        for code, resp in op.get("responses", {}).items():
            if not str(code).startswith("2"):
                continue
            schema = resp.get("content", {}).get("application/json", {}).get("schema", {})
            schema = _resolve_ref(spec, schema)
            for key in item_keys:  # 分页信封:进 items
                schema = _resolve_ref(spec, schema.get("properties", {}).get(key, {}))
            if schema.get("type") == "array" or "items" in schema:
                schema = _resolve_ref(spec, schema.get("items", {}))
            return set(schema.get("properties", {}).keys())
    pytest.fail(f"OpenAPI 里找不到端点 {path_suffix} 的 GET 2xx 数组响应")
    raise AssertionError("unreachable: pytest.fail 总是抛异常")  # 仅为满足返回类型


@pytest.mark.parametrize(("path_suffix", "fields", "item_keys"), _TARGETS)
def test_projection_fields_exist_in_api(path_suffix: str, fields: tuple[str, ...], item_keys: tuple[str, ...]) -> None:
    spec = _openapi_spec()
    api_props = _item_props(spec, path_suffix, item_keys)
    missing = [f for f in fields if f not in api_props]
    assert not missing, (
        f"{path_suffix} 默认投影列出了 API 不返回的字段 {missing}——"
        "要么投影清单过期,要么 API 字段改名;模型点名要这些字段会静默落空"
    )
