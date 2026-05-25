"""类案检索 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


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
    return client.post("/legal-research/tasks", json=payload)  # type: ignore[return-value]


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
    return client.post("/legal-research/capability/search/mcp", json=payload)  # type: ignore[return-value]


def get_research_task(task_id: int) -> dict[str, Any]:
    """查询类案检索任务状态和进度。status: pending/running/completed/failed。"""
    return client.get(f"/legal-research/tasks/{task_id}")  # type: ignore[return-value]


def list_research_results(task_id: int) -> list[dict[str, Any]]:
    """获取检索任务的结果列表，包含相似度评分、案件摘要等。"""
    return client.get(f"/legal-research/tasks/{task_id}/results")  # type: ignore[return-value]


def download_research_result(task_id: int, result_id: int) -> dict[str, Any]:
    """下载单个检索结果的 PDF 文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(
        f"/legal-research/tasks/{task_id}/results/{result_id}/download"
    )
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_all_research_results(task_id: int) -> dict[str, Any]:
    """下载检索任务所有结果的 ZIP 压缩包。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(
        f"/legal-research/tasks/{task_id}/results/download"
    )
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
