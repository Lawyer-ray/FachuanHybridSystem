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
from typing import Annotated, Callable, get_args, get_type_hints

import django
import pytest
from pydantic import Field

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from mcp.server.mcpserver.utilities.func_metadata import func_metadata

from apps.workflow.mcp.workflow_tools import (
    approve_workflow_step,
    create_workflow_template,
    list_workflows,
    start_workflow,
    update_workflow_template,
)
from mcp_server.tools.cases.cases import list_cases, search_cases, update_case
from mcp_server.tools.clients.clients import create_client, list_clients, update_client
from mcp_server.tools.contacts.contacts import create_contact, list_contacts, update_contact
from mcp_server.tools.contract_review.review import confirm_party
from mcp_server.tools.contracts.contracts import create_contract, list_contracts
from mcp_server.tools.contracts.folder_file import read_folder_file
from mcp_server.tools.core.agent_attachments import read_agent_attachment
from mcp_server.tools.documents.documents import create_document_template, list_document_templates
from mcp_server.tools.documents.folder_template_ops import create_folder_template
from mcp_server.tools.finance.lpr import calculate_interest, list_lpr_rates
from mcp_server.tools.finance.mortgage import mortgage_amortize
from mcp_server.tools.legal_research.legal_research import capability_search, create_research_task
from mcp_server.tools.message_hub.inbox import list_inbox_messages
from mcp_server.tools.message_hub.sources import create_message_source, update_message_source
from mcp_server.tools.organization.lawyers import create_lawyer, list_lawyers, update_lawyer

#: 已迁移到 schema 级参数描述的工具:名字 → (参数总数下界, 带描述数下界)
_DESCRIBED_TOOLS: dict[str, tuple[int, int]] = {
    "list_cases": (8, 8),
    "search_cases": (4, 4),
    "list_contracts": (9, 9),
    "create_contract": (15, 15),
    "list_lawyers": (2, 2),
    "create_lawyer": (10, 10),
    "update_lawyer": (10, 10),
    "list_clients": (5, 5),
    "create_client": (7, 7),
    "update_client": (8, 8),
    "list_inbox_messages": (5, 5),
    "list_contacts": (4, 4),
    "create_contact": (8, 8),
    "update_contact": (2, 2),
    "list_lpr_rates": (3, 3),
    "calculate_interest": (10, 10),
    "read_folder_file": (9, 9),
    "start_workflow": (2, 2),
    "list_workflows": (3, 3),
    "approve_workflow_step": (3, 3),
    "create_workflow_template": (5, 5),
    "update_workflow_template": (6, 6),
    "create_message_source": (10, 10),
    "update_message_source": (9, 9),
    "mortgage_amortize": (10, 10),
    "create_research_task": (8, 8),
    "capability_search": (7, 7),
    "update_case": (6, 6),
    "confirm_party": (7, 7),
    "read_agent_attachment": (7, 7),
    "list_document_templates": (4, 4),
    "create_document_template": (10, 10),
    "create_folder_template": (8, 8),
}


_ALL_DESCRIBED_FNS = [
    list_cases, search_cases, list_contracts, create_contract, list_lawyers, create_lawyer,
    update_lawyer, list_clients, create_client, update_client, list_inbox_messages,
    list_contacts, create_contact, update_contact, list_lpr_rates,
    calculate_interest, read_folder_file, start_workflow, list_workflows,
    approve_workflow_step, create_workflow_template, update_workflow_template,
    create_message_source, update_message_source, mortgage_amortize,
    create_research_task, capability_search, update_case, confirm_party,
    read_agent_attachment, list_document_templates, create_document_template,
    create_folder_template,
]


def _schema_of(fn: object) -> dict:
    """用 SDK 同款管道(func_metadata)离线生成 inputSchema,不需要起服务。"""
    metadata = func_metadata(fn)  # type: ignore[arg-type]
    return metadata.arg_model.model_json_schema()


def _registered_schema(name: str) -> dict:
    """从 server 注册表取线上真实 schema(workflow 工具经 _workflow_tool
    剥离 user/org_access/perm_open_access 后才是真工具面——裸函数签名
    会多出这三个无描述参数,对它们必须走注册表)。"""
    import mcp_server.server as srv

    for tool in srv.mcp._tool_manager.list_tools():  # type: ignore[attr-defined]
        if tool.name == name:
            return tool.parameters
    raise AssertionError(f"注册表里没有工具 {name}")


def _make_canary() -> Callable[..., int]:
    """金丝雀函数须在模块级名字空间可解析注解,故工厂返回而非闭包内联。"""

    def _canary(x: Annotated[int, Field(description="canary-desc", ge=2)] = 3) -> int:
        return x

    return _canary


@pytest.mark.parametrize("fn", _ALL_DESCRIBED_FNS, ids=lambda f: f.__name__)
def test_described_tool_params_carry_schema_descriptions(fn) -> None:
    name = fn.__name__
    min_total, min_desc = _DESCRIBED_TOOLS[name]
    schema = _registered_schema(name)
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
    from apps.client.models.client import ClientType
    from apps.contract_review.schemas.review_schemas import ConfirmPartyIn
    from apps.contracts.models.contract import ContractStatus, FeeMode
    from apps.core.models.enums import CaseStage, CaseStatus, CaseType, SimpleCaseType
    from apps.documents.models.choices import DocumentCaseType, DocumentTemplateType
    from apps.finance.schemas.lpr_schemas import InterestCalculateRequest, MortgageAmortizeRequest
    from apps.legal_research.schemas.legal_research_schemas import AgentSearchRequestV1, LegalResearchTaskCreateIn
    from apps.message_hub.models.message_source import SourceType
    from apps.workflow.models.run import WorkflowRun
    from apps.workflow.models.template import WorkflowTemplate
    from mcp_server.tools.cases.cases import list_cases
    from mcp_server.tools.clients.clients import list_clients
    from mcp_server.tools.contracts.contracts import create_contract, list_contracts
    from mcp_server.tools.finance.lpr import calculate_interest

    def _backend_literal(schema_cls: type, field_name: str) -> set:
        hints = get_type_hints(schema_cls)
        return set(get_args(hints[field_name]))

    authoritative: dict[tuple[str, str], set] = {
        ("list_cases", "case_type"): set(SimpleCaseType.values),
        ("list_cases", "status"): set(CaseStatus.values),
        ("list_contracts", "case_type"): set(CaseType.values),
        ("list_contracts", "status"): set(ContractStatus.values),
        ("list_contracts", "fee_mode"): set(FeeMode.values),
        ("create_contract", "case_type"): set(CaseType.values),
        ("create_contract", "status"): set(ContractStatus.values),
        ("create_contract", "fee_mode"): set(FeeMode.values),
        ("create_contract", "representation_stages"): set(CaseStage.values),
        ("list_clients", "client_type"): set(ClientType.values),
        ("create_client", "client_type"): set(ClientType.values),
        ("update_client", "client_type"): set(ClientType.values),
        ("calculate_interest", "rate_mode"): _backend_literal(InterestCalculateRequest, "rate_mode"),
        ("calculate_interest", "rate_type"): _backend_literal(InterestCalculateRequest, "rate_type"),
        ("calculate_interest", "custom_rate_unit"): _backend_literal(InterestCalculateRequest, "custom_rate_unit"),
        ("calculate_interest", "date_inclusion"): _backend_literal(InterestCalculateRequest, "date_inclusion"),
        ("mortgage_amortize", "repayment_method"): _backend_literal(MortgageAmortizeRequest, "repayment_method"),
        ("mortgage_amortize", "rate_mode"): _backend_literal(MortgageAmortizeRequest, "rate_mode"),
        ("mortgage_amortize", "lpr_type"): _backend_literal(MortgageAmortizeRequest, "lpr_type"),
        ("create_message_source", "source_type"): set(SourceType.values),
        ("create_research_task", "search_mode"): _backend_literal(LegalResearchTaskCreateIn, "search_mode"),
        ("capability_search", "intent"): _backend_literal(AgentSearchRequestV1, "intent"),
        ("capability_search", "search_mode"): _backend_literal(AgentSearchRequestV1, "search_mode"),
        ("update_case", "status"): set(CaseStatus.values),
        ("confirm_party", "represented_party"): _backend_literal(ConfirmPartyIn, "represented_party"),
        ("list_document_templates", "template_type"): set(DocumentTemplateType.values),
        ("list_document_templates", "case_type"): set(DocumentCaseType.values),
        ("create_document_template", "template_type"): set(DocumentTemplateType.values),
        ("create_document_template", "case_types"): set(DocumentCaseType.values),
        ("create_folder_template", "template_type"): set(DocumentTemplateType.values),
        ("create_folder_template", "case_types"): set(DocumentCaseType.values),
        ("list_workflows", "status"): set(WorkflowRun.Status.values),
        ("create_workflow_template", "category"): set(WorkflowTemplate.Category.values),
        ("update_workflow_template", "category"): set(WorkflowTemplate.Category.values),
    }
    schemas = {
        "list_cases": _schema_of(list_cases),
        "list_contracts": _schema_of(list_contracts),
        "create_contract": _schema_of(create_contract),
        "list_clients": _schema_of(list_clients),
        "create_client": _schema_of(create_client),
        "update_client": _schema_of(update_client),
        "calculate_interest": _schema_of(calculate_interest),
        "mortgage_amortize": _schema_of(mortgage_amortize),
        "create_message_source": _schema_of(create_message_source),
        "create_research_task": _schema_of(create_research_task),
        "capability_search": _schema_of(capability_search),
        "update_case": _schema_of(update_case),
        "confirm_party": _schema_of(confirm_party),
        "list_document_templates": _schema_of(list_document_templates),
        "create_document_template": _schema_of(create_document_template),
        "create_folder_template": _schema_of(create_folder_template),
        # workflow 工具必须走注册表(_workflow_tool 剥离了身份参数)
        "list_workflows": _registered_schema("list_workflows"),
        "create_workflow_template": _registered_schema("create_workflow_template"),
        "update_workflow_template": _registered_schema("update_workflow_template"),
    }
    for (tool, param), expected in authoritative.items():
        prop = schemas[tool]["properties"][param]
        got = _schema_enums(prop)
        assert got, f"{tool}.{param} 的 schema 没有 enum(Literal 丢失?)"
        assert got == expected, f"{tool}.{param} enum 与 TextChoices 漂移: 多 {got - expected} / 少 {expected - got}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
