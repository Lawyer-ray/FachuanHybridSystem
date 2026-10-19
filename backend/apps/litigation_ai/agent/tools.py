"""
诉讼文书生成 Agent 工具定义

定义 Agent 可调用的工具集,包括案件信息获取、证据检索、文书生成等.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

import logging
from functools import update_wrapper
from typing import Any

from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field

logger = logging.getLogger("apps.litigation_ai")


class _SimpleTool:
    def __init__(self, func: Any, args_schema: type[BaseModel] | None = None, async_func: Any = None) -> None:
        update_wrapper(self, func)
        self._func = func
        self._async_func = async_func
        self.args_schema = args_schema
        self.name = getattr(func, "__name__", "tool")
        self.description = (getattr(func, "__doc__", "") or "").strip()

    def _normalize_args(self, args: Any) -> dict[str, Any]:
        if args is None:
            payload: dict[str, Any] = {}
        elif isinstance(args, BaseModel):
            payload = args.model_dump()
        elif isinstance(args, dict):
            payload = dict(args)
        else:
            raise TypeError(f"Tool args must be dict/BaseModel/None, got {type(args).__name__}")

        if self.args_schema is None:
            return payload
        validated = self.args_schema.model_validate(payload)
        return validated.model_dump()

    def invoke(self, args: Any | None = None) -> Any:
        return self._func(**self._normalize_args(args))

    async def ainvoke(self, args: Any | None = None) -> Any:
        normalized = self._normalize_args(args)
        if self._async_func is not None:
            return await self._async_func(**normalized)
        return await sync_to_async(self._func, thread_sensitive=True)(**normalized)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(*args, **kwargs)


def tool(*, args_schema: type[BaseModel] | None = None, async_func: Any = None) -> Any:
    def _decorator(func: Any) -> _SimpleTool:
        return _SimpleTool(func=func, args_schema=args_schema, async_func=async_func)

    return _decorator


# ============================================================
# 工具输入模型定义
# ============================================================


class GetCaseInfoInput(BaseModel):
    """get_case_info 工具输入"""

    case_id: int = Field(description="案件 ID")


class GetEvidenceListInput(BaseModel):
    """get_evidence_list 工具输入"""

    case_id: int = Field(description="案件 ID")
    ownership: str | None = Field(default=None, description="证据归属过滤: 'our'(我方), 'opponent'(对方), None(全部)")


class SearchEvidenceInput(BaseModel):
    """search_evidence 工具输入"""

    query: str = Field(description="检索查询文本")
    evidence_item_ids: list[int] = Field(description="要检索的证据项 ID 列表")
    top_k: int = Field(default=5, description="返回结果数量")


class GetRecommendedDocumentTypesInput(BaseModel):
    """get_recommended_document_types 工具输入"""

    case_id: int = Field(description="案件 ID")


class GenerateDraftInput(BaseModel):
    """generate_draft 工具输入"""

    case_id: int = Field(description="案件 ID")
    document_type: str = Field(
        description=(
            "文书类型: complaint(起诉状), defense(答辩状), counterclaim(反诉状), counterclaim_defense(反诉答辩状)"
        )
    )
    litigation_goal: str = Field(description="诉讼目标描述")
    evidence_context: str = Field(description="证据上下文摘要")


# ============================================================
# 工具定义
# ============================================================


async def _get_case_info_async(case_id: int, **kwargs: Any) -> dict[str, Any]:
    """get_case_info 的异步实现。"""
    from apps.litigation_ai.services.session.context_service import LitigationContextService

    return await LitigationContextService().aget_case_info_for_agent(case_id)


async def _get_evidence_list_async(case_id: int, ownership: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    """get_evidence_list 的异步实现。"""
    from apps.litigation_ai.services.session.context_service import LitigationContextService

    return await LitigationContextService().aget_evidence_list_for_agent(case_id, ownership)


async def _search_evidence_async(
    query: str, evidence_item_ids: list[int], top_k: int = 5, **kwargs: Any
) -> list[dict[str, Any]]:
    """search_evidence 的异步实现。"""
    from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

    return await EvidenceDigestService().asearch_evidence_for_agent(
        query=query, evidence_item_ids=evidence_item_ids, top_k=top_k
    )


async def _get_recommended_document_types_async(case_id: int, **kwargs: Any) -> list[str]:
    """get_recommended_document_types 的异步实现。"""
    from apps.litigation_ai.services.session.conversation_service import ConversationService

    return await sync_to_async(ConversationService().get_recommended_document_types)(case_id)


@tool(args_schema=GetCaseInfoInput, async_func=_get_case_info_async)
def get_case_info(case_id: int) -> dict[str, Any]:
    """
    获取案件基本信息,包括当事人、案由、标的额等.

    在生成诉讼文书前,应先调用此工具了解案件基本情况.

    Args:
        case_id: 案件 ID

    Returns:
        案件详细信息,包含 case_id, case_name, cause_of_action,
        target_amount, our_legal_status, parties, court_info 等字段
    """
    logger.info("调用 get_case_info 工具", extra={"case_id": case_id})

    try:
        from apps.litigation_ai.services.session.context_service import LitigationContextService

        service = LitigationContextService()
        case_info = service.get_case_info_for_agent(case_id)

        return case_info
    except Exception as e:
        logger.error("get_case_info 工具执行失败", extra={"case_id": case_id, "error": str(e)})
        return {"error": f"获取案件信息失败: {e!s}"}


@tool(args_schema=GetEvidenceListInput, async_func=_get_evidence_list_async)
def get_evidence_list(
    case_id: int,
    ownership: str | None = None,
) -> list[dict[str, Any]]:
    """
    获取案件的证据清单.

    可以按归属过滤证据,用于了解案件有哪些证据可用.

    Args:
        case_id: 案件 ID
        ownership: 证据归属过滤,可选值: 'our'(我方), 'opponent'(对方), None(全部)

    Returns:
        证据项列表,每项包含 evidence_item_id, name, evidence_type,
        ownership, description, has_content 等字段
    """
    logger.info("调用 get_evidence_list 工具", extra={"case_id": case_id, "ownership": ownership})

    try:
        from apps.litigation_ai.services.session.context_service import LitigationContextService

        service = LitigationContextService()
        evidence_list = service.get_evidence_list_for_agent(case_id, ownership)

        return evidence_list
    except Exception as e:
        logger.error("get_evidence_list 工具执行失败", extra={"case_id": case_id, "error": str(e)})
        return [{"error": f"获取证据列表失败: {e!s}"}]


@tool(args_schema=SearchEvidenceInput, async_func=_search_evidence_async)
def search_evidence(
    query: str,
    evidence_item_ids: list[int],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    在指定证据中检索相关内容(RAG 检索).

    用于在生成文书时查找支持论点的证据内容.

    Args:
        query: 检索查询文本,描述要查找的内容
        evidence_item_ids: 要检索的证据项 ID 列表
        top_k: 返回结果数量,默认 5

    Returns:
        相关证据片段列表,每项包含 evidence_item_id, text,
        page_start, page_end, source_name, relevance_score 等字段
    """
    logger.info(
        "调用 search_evidence 工具",
        extra={
            "query": query[:50],
            "evidence_count": len(evidence_item_ids),
            "top_k": top_k,
        },
    )

    try:
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        service = EvidenceDigestService()
        results = service.search_evidence_for_agent(
            query=query,
            evidence_item_ids=evidence_item_ids,
            top_k=top_k,
        )

        return results
    except Exception as e:
        logger.error("search_evidence 工具执行失败", extra={"query": query[:50], "error": str(e)})
        return [{"error": f"证据检索失败: {e!s}"}]


@tool(args_schema=GetRecommendedDocumentTypesInput, async_func=_get_recommended_document_types_async)
def get_recommended_document_types(case_id: int) -> list[str]:
    """
    根据案件状态推荐适合生成的文书类型.

    根据案件的诉讼地位和当前状态,推荐用户可以生成的文书类型.

    Args:
        case_id: 案件 ID

    Returns:
        推荐的文书类型列表,如 ['complaint', 'counterclaim_defense']
        可能的值: complaint(起诉状), defense(答辩状),
        counterclaim(反诉状), counterclaim_defense(反诉答辩状)
    """
    logger.info("调用 get_recommended_document_types 工具", extra={"case_id": case_id})

    try:
        from apps.litigation_ai.services.session.conversation_service import ConversationService

        service = ConversationService()
        recommended = service.get_recommended_document_types(case_id)

        return recommended
    except Exception as e:
        logger.error("get_recommended_document_types 工具执行失败", extra={"case_id": case_id, "error": str(e)})
        return []


async def _generate_draft_async(
    case_id: int,
    document_type: str,
    litigation_goal: str,
    evidence_context: str,
) -> dict[str, Any]:
    """generate_draft 的异步实现，避免 asyncio.run() 嵌套事件循环"""
    logger.info(
        "调用 generate_draft 工具(异步)",
        extra={
            "case_id": case_id,
            "document_type": document_type,
        },
    )

    try:
        from apps.litigation_ai.services.generation.draft_service import DraftService

        service = DraftService()
        result = await service.generate_draft_for_agent(
            case_id=case_id,
            document_type=document_type,
            litigation_goal=litigation_goal,
            evidence_context=evidence_context,
        )

        return result
    except Exception as e:
        logger.error(
            "generate_draft 工具执行失败",
            extra={
                "case_id": case_id,
                "document_type": document_type,
                "error": str(e),
            },
        )
        return {"error": f"生成草稿失败: {e!s}"}


@tool(args_schema=GenerateDraftInput, async_func=_generate_draft_async)
def generate_draft(
    case_id: int,
    document_type: str,
    litigation_goal: str,
    evidence_context: str,
) -> dict[str, Any]:
    """
    生成诉讼文书草稿.

    根据案件信息、文书类型、诉讼目标和证据上下文生成文书草稿.

    Args:
        case_id: 案件 ID
        document_type: 文书类型 (complaint/defense/counterclaim/counterclaim_defense)
        litigation_goal: 诉讼目标描述,说明希望达成的诉讼结果
        evidence_context: 证据上下文摘要,包含支持论点的关键证据内容

    Returns:
        生成的文书草稿,包含 display_text, draft, model 等字段
    """
    logger.info(
        "调用 generate_draft 工具",
        extra={
            "case_id": case_id,
            "document_type": document_type,
        },
    )

    try:
        # NOTE: generate_draft_for_agent is async; this sync stub is never called
        # in practice because @tool(async_func=_generate_draft_async) routes
        # async calls to _generate_draft_async instead.
        raise NotImplementedError("Use _generate_draft_async for async execution")
    except Exception as e:
        logger.error(
            "generate_draft 工具执行失败",
            extra={
                "case_id": case_id,
                "document_type": document_type,
                "error": str(e),
            },
        )
        return {"error": f"生成草稿失败: {e!s}"}


# ============================================================
# 工具集获取函数
# ============================================================


def _bind_tool_case_id(tool: Any, case_id: int) -> Any:
    """安全审计（2026-10-19）：把工具的 case_id 参数闭包绑定到会话案件.

    Agent 工具的 case_id 参数由 LLM 填充（GetCaseInfoInput 等），历史实现
    直接透传给 get_case_with_details_internal / 证据查询等无归属过滤的内部
    接口，提示词注入即可诱导 Agent 跨案件读取他人案情与证据.这里在工厂
    创建工具集时用闭包把 case_id 钉死到会话案件，忽略模型给的值（与
    LitigationAgentFactory.create_agent(session_id, case_id) 的绑定方式
    对齐）.args_schema 不含 case_id 的工具（如 search_evidence）原样返回.
    """
    schema_fields = getattr(getattr(tool, "args_schema", None), "model_fields", None) or {}
    if "case_id" not in schema_fields:
        return tool

    sync_func = tool._func
    async_func = tool._async_func

    def bound_sync(**kwargs: Any) -> Any:
        kwargs["case_id"] = case_id
        return sync_func(**kwargs)

    async def bound_async(**kwargs: Any) -> Any:
        kwargs["case_id"] = case_id
        if async_func is not None:
            return await async_func(**kwargs)
        return await sync_to_async(sync_func, thread_sensitive=True)(**kwargs)

    bound = _SimpleTool(func=bound_sync, args_schema=tool.args_schema, async_func=bound_async)
    bound.name = tool.name
    bound.description = tool.description
    return bound


def get_litigation_tools(case_id: int) -> list[Any]:
    """
    获取诉讼文书生成的工具列表

    Args:
        case_id: 案件 ID(工具的 case_id 参数闭包绑定到该案件,忽略 LLM 填充值)

    Returns:
        工具列表,可直接传递给 Agent
    """
    return [
        _bind_tool_case_id(get_case_info, case_id),
        _bind_tool_case_id(get_evidence_list, case_id),
        _bind_tool_case_id(search_evidence, case_id),
        _bind_tool_case_id(get_recommended_document_types, case_id),
        _bind_tool_case_id(generate_draft, case_id),
    ]


def get_tool_descriptions() -> dict[str, str]:
    """
    获取所有工具的描述信息

    Returns:
        工具名称到描述的映射
    """
    tools = get_litigation_tools(0)
    return {tool.name: tool.description for tool in tools}
