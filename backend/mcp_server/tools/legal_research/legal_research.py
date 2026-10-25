"""类案检索 MCP tools"""

from __future__ import annotations

import base64
from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result

#: 与后端 legal_research_schemas 的 Literal 逐值对账(门禁 test_schema_param_descriptions)。
_IntentL = Literal["similar_case", "same_court_precedent", "claim_style", "reasoning_style", "defense_risk"]
_SearchModeL = Literal["expanded", "single"]


def create_research_task(
    credential_id: Annotated[int, Field(description="威科先行账号凭证 ID(AccountCredential)", ge=1)],
    keyword: Annotated[str, Field(description="检索关键词(空格分隔 2-4 个核心词)")],
    case_summary: Annotated[str, Field(description="案情摘要(用于相似度比对)")],
    search_mode: Annotated[_SearchModeL, Field(description="expanded 扩展检索/single 单检索")] = "expanded",
    target_count: Annotated[int, Field(description="目标返回类案数", ge=1)] = 3,
    max_candidates: Annotated[int, Field(description="候选池上限(相似度筛选前)", ge=1)] = 100,
    min_similarity_score: Annotated[float, Field(description="相似度阈值(0-1,越高越严)", ge=0.0, le=1.0)] = 0.9,
    llm_model: Annotated[str | None, Field(description="指定 LLM 型号(可选,默认用系统配置)")] = None,
) -> dict[str, Any]:
    """创建类案检索任务。search_mode: expanded（扩展）或 single（单检索）。返回 task_id 和初始状态。"""
    payload: dict[str, Any] = {
        "credential_id": credential_id,
        "keyword": keyword,
        "case_summary": case_summary,
        "search_mode": search_mode,
        "target_count": target_count,
        "max_candidates": max_candidates,
        "min_similarity_score": min_similarity_score,
    }
    if llm_model:
        payload["llm_model"] = llm_model
    return client.post("/legal-research/tasks", json=payload)  # type: ignore[no-any-return]


def capability_search(
    credential_id: Annotated[int, Field(description="威科先行账号凭证 ID(AccountCredential)", ge=1)],
    facts: Annotated[str, Field(description="案情事实描述(检索的种子文本)")],
    intent: Annotated[_IntentL, Field(description="检索意图:similar_case 类案/same_court_precedent 同院先例/claim_style 诉请风格/reasoning_style 说理风格/defense_risk 抗辩风险")] = "similar_case",
    legal_issue: Annotated[str, Field(description="争议焦点(可选,提高检索精度)")] = "",
    cause_type: Annotated[str, Field(description="案由(可选)")] = "",
    target_count: Annotated[int, Field(description="目标返回条数", ge=1)] = 5,
    search_mode: Annotated[_SearchModeL, Field(description="expanded 扩展检索/single 单检索")] = "expanded",
) -> dict[str, Any]:
    """Agent 直接调用的类案检索能力接口（同步返回结果）。intent 可选：similar_case、same_court_precedent、claim_style、reasoning_style、defense_risk。"""
    payload: dict[str, Any] = {
        "version": "v1",
        "credential_id": credential_id,
        "intent": intent,
        "facts": facts,
        "legal_issue": legal_issue,
        "cause_type": cause_type,
        "target_count": target_count,
        "search_mode": search_mode,
    }
    # 端点同步执行威科检索（Playwright 会话 + 多页抓取,实测 30-90s）,
    # 60s 默认超时不够;pi 侧 mcp.json timeout=200 兜住。
    return client.post("/legal-research/capability/search/mcp", json=payload, timeout=180)  # type: ignore[no-any-return]


def get_research_task(task_id: int) -> dict[str, Any]:
    """查询类案检索任务状态和进度。status: pending/queued/running/completed/failed/cancelled。"""
    return client.get(f"/legal-research/tasks/{task_id}")  # type: ignore[no-any-return]


def list_research_results(task_id: int) -> dict[str, Any]:
    """获取检索任务的结果列表，包含相似度评分、案件摘要等。"""
    return list_result(client.get(f"/legal-research/tasks/{task_id}/results"))


def download_research_result(task_id: int, result_id: int) -> dict[str, Any]:
    """下载单个检索结果的 PDF 文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/legal-research/tasks/{task_id}/results/{result_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_all_research_results(task_id: int) -> dict[str, Any]:
    """下载检索任务所有结果的 ZIP 压缩包。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/legal-research/tasks/{task_id}/results/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def check_law_references(text: str, credential_id: int) -> dict[str, Any]:
    """校验文书中的法律条文引用是否有效。text 为文书全文；credential_id 为法规检索服务账号的凭证 ID。"""
    return client.post(  # type: ignore[no-any-return]
        "/legal-research/law-verification/check",
        json={"text": text, "credential_id": credential_id},
        # 后端同步阻塞(威科 Playwright 登录 10-15s + 逐条核查 HTTP IO)——
        # 60s 默认超时对长文书必掐断;pi 侧 mcp.json timeout=200 兜住。
        timeout=180,
    )
