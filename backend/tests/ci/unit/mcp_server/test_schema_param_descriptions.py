"""inputSchema 参数描述门禁:Annotated+Field 的描述必须真实进入 schema。

背景(2026-10-25 二十六轮审计):全工具面 919 个参数在 inputSchema 里
**零描述**——SDK 只给名字+类型+自动 title("Case Type"),枚举陷阱
(fee_mode 大写/representation_stages 英文键)全靠 docstring 长文,
而模型**选参数值时看的是 schema**(pi 的 toParameters 原样透传
inputSchema)。参考 MCP server 的最佳实践是 Annotated[..., Field(
description=...)]——描述与数值约束(min/max)都会进 schema。

本门禁钉死两件事:
1. 语义级:已迁移工具的参数描述覆盖率与关键约束不回退;
2. 机制级:func_metadata 对 Field 注解的传导不因 SDK 升级静默失效
   (mcp 1.x→2.x 已搬过一次目录,若 3.x 再变,这里的失败即提醒重审)。

迁移是渐进的(919 参数非一日之功),已迁移名单见 ``_DESCRIBED_TOOLS``;
新增工具直接写 Annotated+Field,不要先裸参数再等补课。
"""

from __future__ import annotations

import os
from typing import Annotated, Callable

import django
import pytest
from pydantic import Field

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from mcp.server.mcpserver.utilities.func_metadata import func_metadata

from mcp_server.tools.cases.cases import list_cases, search_cases
from mcp_server.tools.contracts.contracts import create_contract, list_contracts

#: 已迁移到 schema 级参数描述的工具:名字 → (参数总数下界, 带描述数下界)
_DESCRIBED_TOOLS: dict[str, tuple[int, int]] = {
    "list_cases": (8, 8),
    "search_cases": (4, 4),
    "list_contracts": (9, 9),
    "create_contract": (15, 15),
}


def _schema_of(fn: object) -> dict:
    """用 SDK 同款管道(func_metadata)离线生成 inputSchema,不需要起服务。"""
    metadata = func_metadata(fn)  # type: ignore[arg-type]
    return metadata.arg_model.model_json_schema()


def _make_canary() -> Callable[..., int]:
    """金丝雀函数须在模块级名字空间可解析注解,故工厂返回而非闭包内联。"""

    def _canary(x: Annotated[int, Field(description="canary-desc", ge=2)] = 3) -> int:
        return x

    return _canary


@pytest.mark.parametrize("fn", [list_cases, search_cases, list_contracts, create_contract], ids=lambda f: f.__name__)
def test_described_tool_params_carry_schema_descriptions(fn) -> None:
    name = fn.__name__
    min_total, min_desc = _DESCRIBED_TOOLS[name]
    schema = _schema_of(fn)
    props = schema.get("properties", {})
    assert len(props) >= min_total, f"{name} 参数数 {len(props)} < {min_total}(签名被改坏?)"
    missing = [k for k, v in props.items() if not v.get("description")]
    assert not missing, f"{name} 参数缺 schema 描述: {missing}"
    assert len(props) >= min_desc


def test_numeric_constraints_reach_schema() -> None:
    """Field(ge/le/gt) 的数值约束必须进 schema——模型在调用前就能看到边界。"""
    cases_props = _schema_of(list_cases)["properties"]
    lim = cases_props["limit"]
    assert lim.get("minimum") == 1 and lim.get("maximum") == 2000, f"list_cases.limit 约束丢失: {lim}"
    off = cases_props["offset"]
    assert off.get("minimum") == 0, f"list_cases.offset 约束丢失: {off}"
    contracts_props = _schema_of(list_contracts)["properties"]
    ps = contracts_props["page_size"]
    assert ps.get("minimum") == 1 and ps.get("maximum") == 200, f"list_contracts.page_size 约束丢失: {ps}"


def test_field_description_plumbing_canary() -> None:
    """机制金丝雀:不经我们代码,直接验证 SDK 对 Field 注解的传导。

    若 SDK 升级后此测试失败,说明 func_metadata 不再把 Field 描述带进
    schema——全工具面的参数描述将静默消失,必须重审迁移路径。"""
    canary = _make_canary()
    props = _schema_of(canary)["properties"]["x"]
    assert props.get("description") == "canary-desc", f"描述未传导: {props}"
    assert props.get("minimum") == 2, f"约束未传导: {props}"


def _has_title(node: object) -> bool:
    if isinstance(node, dict):
        return "title" in node or any(_has_title(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_title(i) for i in node)
    return False


def test_registered_schemas_carry_no_redundant_titles() -> None:
    """注册后瘦身通道必须生效:inputSchema 里的自动 title 全部剥离。

    pydantic 给每个参数生成与参数名同义的 title("case_type"→"Case Type"),
    919 个 ≈ 20KB 零信息上下文税。server.py 末尾 ``_slim_registered_tool_schemas``
    在全部注册后统一剥;本测试防两类回退:①通道被删/没跑到(_titles 出现在
    线上 schema);②SDK 升级把 parameters 改成不可变/重新生成。"""
    import mcp_server.server as srv

    tools = srv.mcp._tool_manager.list_tools()  # type: ignore[attr-defined]
    assert len(tools) >= 400, f"注册表异常: {len(tools)}(瘦身通道可能跑在注册完成前)"
    offenders = [t.name for t in tools if _has_title(t.parameters)]
    assert not offenders, f"{len(offenders)} 个工具的 schema 仍带冗余 title: {offenders[:5]}"
    assert srv._SLIMMED_TITLES >= 900, f"剥离量 {srv._SLIMMED_TITLES} 异常(应 ≈919+顶层)"


def _schema_enums(prop: dict) -> set[str]:
    """收集参数 schema 节点里全部 enum 值(直接/anyOf 分支/list 的 items 内)。"""
    values: set[str] = set()
    if "enum" in prop:
        values.update(prop["enum"])
    for branch in prop.get("anyOf", []):
        if "enum" in branch:
            values.update(branch["enum"])
        items = branch.get("items")
        if isinstance(items, dict) and "enum" in items:
            values.update(items["enum"])
    items = prop.get("items")
    if isinstance(items, dict) and "enum" in items:
        values.update(items["enum"])
    return values


def test_schema_enums_match_model_choices() -> None:
    """schema 级 enum(Literal)必须与模型 TextChoices 逐值同步。

    枚举陷阱的根治层:模型选值时只见合法集(小写 fee_mode 在调用前就被
    挡住)。代价是双份口径——后端 TextChoices 加值而 Literal 不跟,schema
    会把新值挡在外面;本测试用权威表逐值对账,drift 即红灯。"""
    from apps.contracts.models.contract import ContractStatus, FeeMode
    from apps.core.models.enums import CaseStage, CaseStatus, CaseType, SimpleCaseType
    from mcp_server.tools.cases.cases import list_cases
    from mcp_server.tools.contracts.contracts import create_contract, list_contracts

    authoritative: dict[tuple[str, str], set[str]] = {
        ("list_cases", "case_type"): set(SimpleCaseType.values),
        ("list_cases", "status"): set(CaseStatus.values),
        ("list_contracts", "case_type"): set(CaseType.values),
        ("list_contracts", "status"): set(ContractStatus.values),
        ("list_contracts", "fee_mode"): set(FeeMode.values),
        ("create_contract", "case_type"): set(CaseType.values),
        ("create_contract", "status"): set(ContractStatus.values),
        ("create_contract", "fee_mode"): set(FeeMode.values),
        ("create_contract", "representation_stages"): set(CaseStage.values),
    }
    schemas = {
        "list_cases": _schema_of(list_cases),
        "list_contracts": _schema_of(list_contracts),
        "create_contract": _schema_of(create_contract),
    }
    for (tool, param), expected in authoritative.items():
        prop = schemas[tool]["properties"][param]
        got = _schema_enums(prop)
        assert got, f"{tool}.{param} 的 schema 没有 enum(Literal 丢失?)"
        assert got == expected, f"{tool}.{param} enum 与 TextChoices 漂移: 多 {got - expected} / 少 {expected - got}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
