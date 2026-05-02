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
    def __init__(self, func: Any, args_schema: type[BaseModel] | None = None) -> None:
        update_wrapper(self, func)
        self._func = func
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
        return await sync_to_async(self.invoke, thread_sensitive=True)(args)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(*args, **kwargs)


def tool(*, args_schema: type[BaseModel] | None = None) -> Any:
    def _decorator(func: Any) -> _SimpleTool:
        return _SimpleTool(func=func, args_schema=args_schema)

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


@tool(args_schema=GetCaseInfoInput)
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


@tool(args_schema=GetEvidenceListInput)
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


@tool(args_schema=SearchEvidenceInput)
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


@tool(args_schema=GetRecommendedDocumentTypesInput)
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


@tool(args_schema=GenerateDraftInput)
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
        from apps.litigation_ai.services.generation.draft_service import DraftService

        service = DraftService()
        result = service.generate_draft_for_agent(
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


# ============================================================
# 工具集获取函数
# ============================================================


def get_litigation_tools(case_id: int) -> list[Any]:
    """
    获取诉讼文书生成的工具列表

    Args:
        case_id: 案件 ID(部分工具可能需要预绑定案件上下文)

    Returns:
        工具列表,可直接传递给 Agent
    """
    return [
        get_case_info,
        get_evidence_list,
        search_evidence,
        get_recommended_document_types,
        generate_draft,
    ]


def get_tool_descriptions() -> dict[str, str]:
    """
    获取所有工具的描述信息

    Returns:
        工具名称到描述的映射
    """
    tools = get_litigation_tools(0)
    return {tool.name: tool.description for tool in tools}
