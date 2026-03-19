"""材料分类服务。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.core.services.wiring import get_llm_service

logger = logging.getLogger(__name__)


class MaterialClassificationService:
    """为自动捕获场景提供合同/案件材料分类建议。"""

    _CONTRACT_CATEGORIES = {"contract_original", "supplementary_agreement", "other"}
    _CASE_CATEGORIES = {"party", "non_party", "unknown"}
    _CASE_SIDES = {"our", "opponent", "unknown"}

    def classify_contract_material(self, *, filename: str, text_excerpt: str) -> dict[str, Any]:
        default = {
            "category": "other",
            "confidence": 0.0,
            "reason": "AI 分类不可用，请手动确认",
        }
        content = self._complete(
            system_prompt=(
                "你是合同材料分类助手。仅输出 JSON，不要输出其他内容。"
                'JSON 结构: {"category":"contract_original|supplementary_agreement|other","confidence":0-1,"reason":"..."}'
            ),
            user_prompt=(
                f"文件名: {filename}\n"
                "请根据文件名和文本片段给出材料分类。\n"
                f"文本片段:\n{text_excerpt[:1800]}"
            ),
        )
        if not content:
            return default

        payload = self._extract_json(content)
        if not isinstance(payload, dict):
            return default

        category = str(payload.get("category") or "other").strip()
        if category not in self._CONTRACT_CATEGORIES:
            category = "other"

        return {
            "category": category,
            "confidence": self._to_confidence(payload.get("confidence")),
            "reason": str(payload.get("reason") or ""),
        }

    def classify_case_material(self, *, filename: str, text_excerpt: str) -> dict[str, Any]:
        default = {
            "category": "unknown",
            "side": "unknown",
            "type_name_hint": "",
            "confidence": 0.0,
            "reason": "AI 分类不可用，请手动确认",
        }
        content = self._complete(
            system_prompt=(
                "你是案件材料预分类助手。仅输出 JSON，不要输出其他内容。"
                "只返回预填建议，不要假设你知道主管机关或当事人映射。"
                'JSON 结构: {"category":"party|non_party|unknown","side":"our|opponent|unknown","type_name_hint":"",'
                '"confidence":0-1,"reason":"..."}'
            ),
            user_prompt=(
                f"文件名: {filename}\n"
                "请根据文件名和文本片段给出预填建议。\n"
                f"文本片段:\n{text_excerpt[:1800]}"
            ),
        )
        if not content:
            return default

        payload = self._extract_json(content)
        if not isinstance(payload, dict):
            return default

        category = str(payload.get("category") or "unknown").strip()
        if category not in self._CASE_CATEGORIES:
            category = "unknown"

        side = str(payload.get("side") or "unknown").strip()
        if side not in self._CASE_SIDES:
            side = "unknown"

        if category != "party":
            side = "unknown"

        return {
            "category": category,
            "side": side,
            "type_name_hint": str(payload.get("type_name_hint") or "").strip(),
            "confidence": self._to_confidence(payload.get("confidence")),
            "reason": str(payload.get("reason") or ""),
        }

    def _complete(self, *, system_prompt: str, user_prompt: str) -> str:
        try:
            response = get_llm_service().complete(
                prompt=user_prompt,
                system_prompt=system_prompt,
                backend="ollama",
                fallback=True,
                temperature=0.1,
                max_tokens=300,
            )
            return str(getattr(response, "content", "") or "")
        except Exception:
            logger.exception("material_classification_failed")
            return ""

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None

        for candidate in (text, *re.findall(r"\{[\s\S]*\}", text)):
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                continue

        fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        for block in fenced:
            try:
                loaded = json.loads(block)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                continue

        return None

    @staticmethod
    def _to_confidence(value: Any) -> float:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return 0.0
        if val < 0:
            return 0.0
        if val > 1:
            return 1.0
        return val
