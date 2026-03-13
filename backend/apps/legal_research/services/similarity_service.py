from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from apps.core.interfaces import ServiceLocator

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    score: float
    reason: str
    model: str


class CaseSimilarityService:
    """用硅基流动模型计算案例相似度。"""

    def __init__(self) -> None:
        self._llm = ServiceLocator.get_llm_service()

    def score_case(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
        model: str | None = None,
    ) -> SimilarityResult:
        candidate_excerpt = (content_text or "")[:4000]
        prompt = (
            "请判断目标案情与候选案例的相似度，并返回严格JSON。\n"
            "输出格式: {\"score\":0.0-1.0之间的小数,\"reason\":\"不超过120字\"}\n"
            "判断标准: 事实要件、法律关系、争议焦点、裁判思路。\n\n"
            f"关键词: {keyword}\n"
            f"目标案情: {case_summary}\n\n"
            f"候选标题: {title}\n"
            f"候选摘要: {case_digest}\n"
            f"候选正文摘录: {candidate_excerpt}\n"
        )

        response = self._llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是法律案例匹配评估器，只输出JSON，不输出额外文本。",
                },
                {"role": "user", "content": prompt},
            ],
            backend="siliconflow",
            model=(model or None),
            fallback=False,
            temperature=0.1,
            max_tokens=400,
        )

        score = 0.0
        reason = ""
        parsed = self._extract_json(response.content)
        if isinstance(parsed, dict):
            try:
                score = float(parsed.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            reason = str(parsed.get("reason", "") or "")
        else:
            reason = (response.content or "")[:120]

        score = max(0.0, min(1.0, score))
        if not reason:
            reason = "模型未返回理由"

        return SimilarityResult(score=score, reason=reason, model=response.model)

    @staticmethod
    def _extract_json(text: str) -> dict[str, object] | None:
        if not text:
            return None

        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z0-9_-]*", "", candidate).strip()
            candidate = candidate.removesuffix("```").strip()

        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            logger.warning("相似度JSON解析失败", extra={"preview": text[:200]})

        return None
