"""类案检索 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def create_research_task(
    credential_id: int,
    keyword: str,
    case_summary: str,
    search_mode: str = "expanded",
    target_count: int = 3,
    max_candidates: int = 100,
    min_similarity_score: float = 0.9,
    llm_model: str | None = None,
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
    credential_id: int,
    facts: str,
    intent: str = "similar_case",
    legal_issue: str = "",
    cause_type: str = "",
    target_count: int = 5,
    search_mode: str = "expanded",
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
