"""
诉讼 Agent 数据结构定义

定义 Agent 输入输出的 Pydantic 模型,用于结构化数据验证.

Requirements: 1.3, 2.6
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """
    Agent 响应结构

    统一的响应格式,兼容现有 WebSocket 接口.

    Attributes:
        type: 响应类型 (system_message, assistant_complete, error)
        content: 响应内容
        metadata: 附加元数据
    """

    type: str = Field(description="响应类型: system_message, assistant_complete, error")
    content: str = Field(description="响应内容")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据,如 tool_calls、draft 等")


class DraftOutput(BaseModel):
    """
    文书草稿输出结构

    根据文书类型包含不同的字段.

    Attributes:
        document_type: 文书类型
        litigation_request: 诉讼请求(起诉状/反诉状)
        facts_and_reasons: 事实与理由(起诉状/反诉状)
        defense_opinion: 答辩意见(答辩状/反诉答辩状)
        defense_reason: 答辩理由(答辩状/反诉答辩状)
        evidence_citations: 证据引用列表
    """

    document_type: str = Field(description="文书类型: complaint, defense, counterclaim, counterclaim_defense")
    litigation_request: str | None = Field(default=None, description="诉讼请求(起诉状/反诉状使用)")
    facts_and_reasons: str | None = Field(default=None, description="事实与理由(起诉状/反诉状使用)")
    defense_opinion: str | None = Field(default=None, description="答辩意见(答辩状/反诉答辩状使用)")
    defense_reason: str | None = Field(default=None, description="答辩理由(答辩状/反诉答辩状使用)")
    evidence_citations: list[dict[str, Any]] = Field(
        default_factory=list, description="证据引用列表,每项包含 evidence_item_id、text、page_range"
    )


class ToolCallRecord(BaseModel):
    """
    工具调用记录

    记录 Agent 的工具调用历史,用于调试和审计.

    Attributes:
        tool_name: 工具名称
        arguments: 调用参数
        result: 调用结果
        timestamp: 调用时间
        duration_ms: 执行耗时(毫秒)
    """

    tool_name: str = Field(description="工具名称")
    arguments: dict[str, Any] = Field(description="调用参数")
    result: Any = Field(description="调用结果")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="调用时间(ISO 格式)")
    duration_ms: float | None = Field(default=None, description="执行耗时(毫秒)")


class CaseInfoResult(BaseModel):
    """
    案件信息结果

    get_case_info 工具的返回结构.

    Attributes:
        case_id: 案件 ID
        case_name: 案件名称
        cause_of_action: 案由
        target_amount: 标的额
        our_legal_status: 我方诉讼地位
        parties: 当事人列表
        court_info: 法院信息
    """

    case_id: int = Field(description="案件 ID")
    case_name: str = Field(description="案件名称")
    cause_of_action: str = Field(description="案由")
    target_amount: str | None = Field(default=None, description="标的额")
    our_legal_status: str = Field(description="我方诉讼地位")
    parties: list[dict[str, Any]] = Field(default_factory=list, description="当事人列表")
    court_info: dict[str, Any] | None = Field(default=None, description="法院信息")


class EvidenceSearchResult(BaseModel):
    """
    证据检索结果

    search_evidence 工具的返回结构.

    Attributes:
        evidence_item_id: 证据项 ID
        text: 检索到的文本片段
        page_start: 起始页码
        page_end: 结束页码
        source_name: 证据来源名称
        relevance_score: 相关性分数
    """

    evidence_item_id: int = Field(description="证据项 ID")
    text: str = Field(description="检索到的文本片段")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    source_name: str = Field(description="证据来源名称")
    relevance_score: float = Field(default=0.0, description="相关性分数")


class EvidenceListItem(BaseModel):
    """
    证据列表项

    get_evidence_list 工具的返回结构中的单个证据项.

    Attributes:
        evidence_item_id: 证据项 ID
        name: 证据名称
        evidence_type: 证据类型
        ownership: 证据归属 (our/opponent)
        description: 证据描述
        has_content: 是否已提取内容
    """

    evidence_item_id: int = Field(description="证据项 ID")
    name: str = Field(description="证据名称")
    evidence_type: str | None = Field(default=None, description="证据类型")
    ownership: str = Field(description="证据归属: our(我方), opponent(对方)")
    description: str | None = Field(default=None, description="证据描述")
    has_content: bool = Field(default=False, description="是否已提取内容")


class GenerateDraftInput(BaseModel):
    """
    生成草稿输入参数

    generate_draft 工具的输入结构.

    Attributes:
        case_id: 案件 ID
        document_type: 文书类型
        litigation_goal: 诉讼目标
        evidence_context: 证据上下文摘要
    """

    case_id: int = Field(description="案件 ID")
    document_type: str = Field(description="文书类型: complaint, defense, counterclaim, counterclaim_defense")
    litigation_goal: str = Field(description="诉讼目标描述")
    evidence_context: str = Field(description="证据上下文摘要")


class GenerateDraftResult(BaseModel):
    """
    生成草稿结果

    generate_draft 工具的返回结构.

    Attributes:
        display_text: 用于显示的文本
        draft: 结构化草稿内容
        model: 使用的模型名称
    """

    display_text: str = Field(description="用于显示的文本")
    draft: dict[str, Any] = Field(description="结构化草稿内容")
    model: str = Field(description="使用的模型名称")
