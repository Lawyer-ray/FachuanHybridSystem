"""证据 AI 辅助服务"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("apps.evidence")

PURPOSE_PROMPT = """你是一位资深诉讼律师。根据以下信息，为这份证据生成2-3个证明目的建议。

案由: {cause_of_action}
证据类型: {evidence_type}
证据名称: {evidence_name}
证据内容摘要: {content_summary}

要求:
1. 每个建议独立成行
2. 语言精准、专业，避免"证明案件事实"等空泛表述
3. 直接说明该证据能证明什么具体事实
4. 只返回建议列表，不要其他内容

格式:
1. xxx
2. xxx
3. xxx"""

CROSS_EXAM_PROMPT = """你是一位资深诉讼律师。请对以下对方证据生成质证意见。

案由: {cause_of_action}
我方主张: {our_claim}
对方证据名称: {evidence_name}
对方证据内容摘要: {content_summary}

请从真实性、合法性、关联性三个维度分析，返回JSON格式:
{{
  "authenticity": {{"opinion": "认可/不认可/部分认可", "reason": "具体理由"}},
  "legality": {{"opinion": "认可/不认可/部分认可", "reason": "具体理由"}},
  "relevance": {{"opinion": "认可/不认可/部分认可", "reason": "具体理由"}}
}}

只返回JSON，不要其他内容。"""


class EvidenceAIService:
    """证据 AI 辅助服务"""

    def suggest_purpose(
        self,
        *,
        cause_of_action: str = "",
        evidence_type: str = "",
        evidence_name: str = "",
        content_summary: str = "",
    ) -> list[str]:
        """AI 生成证明目的建议"""
        from apps.core.llm import get_llm_service

        prompt = PURPOSE_PROMPT.format(
            cause_of_action=cause_of_action or "未知",
            evidence_type=evidence_type or "未知",
            evidence_name=evidence_name or "未知",
            content_summary=content_summary[:500] if content_summary else "无",
        )

        try:
            llm = get_llm_service()
            resp = llm.complete(prompt=prompt, temperature=0.3, fallback=True)
            text = resp.content or ""
            # 解析编号列表
            suggestions: list[str] = []
            for line in text.strip().split("\n"):
                line = re.sub(r"^\d+[\.\)、]\s*", "", line.strip())
                if line:
                    suggestions.append(line)
            return suggestions[:3]
        except Exception as e:
            logger.warning("AI 证明目的建议失败: %s", e)
            return []

    def generate_cross_examination(
        self,
        *,
        cause_of_action: str = "",
        our_claim: str = "",
        evidence_name: str = "",
        content_summary: str = "",
    ) -> dict[str, Any]:
        """AI 生成质证意见"""
        from apps.core.llm import get_llm_service

        prompt = CROSS_EXAM_PROMPT.format(
            cause_of_action=cause_of_action or "未知",
            our_claim=our_claim or "未知",
            evidence_name=evidence_name or "未知",
            content_summary=content_summary[:500] if content_summary else "无",
        )

        try:
            llm = get_llm_service()
            resp = llm.complete(prompt=prompt, temperature=0.2, fallback=True)
            text = resp.content or ""
            # 提取 JSON
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group(0))  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("AI 质证意见生成失败: %s", e)
        return {}
