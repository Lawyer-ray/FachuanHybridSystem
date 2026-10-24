"""诉讼文书生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def generate_complaint(
    case_id: int,
    cause_of_action: str,
    plaintiff: str,
    defendant: str,
    litigation_request: str,
    facts_and_reasons: str,
) -> dict[str, Any]:
    """生成起诉状（LLM 结构化链）。

    Args:
        case_id: 关联案件 id。
        cause_of_action: 案由（如「机动车交通事故责任纠纷」）。
        plaintiff: 原告名称（个人或单位全称）。
        defendant: 被告名称。
        litigation_request: 请判事项（逐项列明，含赔偿项与费用承担）。
        facts_and_reasons: 纠纷经过与法律依据（案情叙事 + 支持请判事项的论证）。
    """
    return client.post(  # type: ignore[no-any-return]
        "/documents/litigation/complaint/generate",
        json={
            "case_id": case_id,
            "cause_of_action": cause_of_action,
            "plaintiff": plaintiff,
            "defendant": defendant,
            "litigation_request": litigation_request,
            "facts_and_reasons": facts_and_reasons,
        },
        timeout=180,
    )


def generate_defense(
    case_id: int,
    cause_of_action: str,
    plaintiff: str,
    defendant: str,
    defense_opinion: str,
    defense_reasons: str,
) -> dict[str, Any]:
    """生成答辩状（LLM 结构化链）。

    Args:
        case_id: 关联案件 id。
        cause_of_action: 案由。
        plaintiff: 原告名称。
        defendant: 被告名称（本方为答辩人时的对方当事人按后端约定填写）。
        defense_opinion: 答辩意见（核心主张，如「被告不应承担赔偿责任」）。
        defense_reasons: 答辩理由（事实与法律依据）。
    """
    return client.post(  # type: ignore[no-any-return]
        "/documents/litigation/defense/generate",
        json={
            "case_id": case_id,
            "cause_of_action": cause_of_action,
            "plaintiff": plaintiff,
            "defendant": defendant,
            "defense_opinion": defense_opinion,
            "defense_reasons": defense_reasons,
        },
        timeout=180,
    )


def preview_litigation_context(case_id: int, litigation_type: str) -> dict[str, Any]:
    """预览诉讼文书替换词上下文。litigation_type: complaint / defense。"""
    return client.get(f"/documents/cases/{case_id}/litigation/{litigation_type}/preview")  # type: ignore[return-value]


def download_litigation_document(
    case_id: int, litigation_type: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """生成并下载诉讼文书为 DOCX（起诉状/答辩状等;LLM 链路,耗时较长,1MB 闸门）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/litigation/{litigation_type}/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
