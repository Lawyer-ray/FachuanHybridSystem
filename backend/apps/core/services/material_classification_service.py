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

    _CONTRACT_CATEGORIES = {"contract_original", "supplementary_agreement", "invoice"}
    _CASE_CATEGORIES = {"party", "non_party", "unknown"}
    _CASE_SIDES = {"our", "opponent", "unknown"}
    _SUPPLEMENTARY_KEYWORDS = (
        "补充协议",
        "补充合同",
        "变更协议",
        "续签协议",
        "补遗",
        "补充条款",
    )
    _INVOICE_KEYWORDS = (
        "发票",
        "invoice",
        "专票",
        "普票",
        "开票",
    )
    _CONTRACT_KEYWORDS = (
        "合同",
        "协议",
    )
    _CASE_OPPONENT_HINTS = (
        "被申请人",
        "被执行人",
        "对方",
        "被告",
        "债务人",
        "相对方",
        "被上诉人",
    )
    _CASE_OUR_HINTS = (
        "申请执行人",
        "申请人",
        "我方",
        "原告",
        "债权人",
        "上诉人",
    )
    _CASE_RULES: tuple[dict[str, Any], ...] = (
        {
            "keywords": ("执行申请书", "强制执行申请书", "申请执行书", "执行申请"),
            "category": "party",
            "side": "our",
            "type_name_hint": "执行申请书",
            "confidence": 0.98,
        },
        {
            "keywords": ("当事人身份证明", "主体资格证明", "营业执照", "身份证", "户口簿", "户口本"),
            "category": "party",
            "side": "auto",
            "type_name_hint": "当事人身份证明",
            "confidence": 0.97,
        },
        {
            "keywords": ("委托材料", "授权委托书", "授权委托", "律师执业证", "律师证", "所函", "委托代理"),
            "category": "party",
            "side": "auto",
            "type_name_hint": "委托材料",
            "confidence": 0.96,
        },
        {
            "keywords": ("限制性措施", "限制高消费", "限高令", "查封", "冻结", "扣划", "财产保全"),
            "category": "non_party",
            "side": "unknown",
            "type_name_hint": "限制性措施材料",
            "confidence": 0.95,
        },
        {
            "keywords": ("执行依据及生效证明", "执行依据", "生效证明", "判决书", "裁定书", "调解书"),
            "category": "non_party",
            "side": "unknown",
            "type_name_hint": "执行依据及生效证明",
            "confidence": 0.97,
        },
        {
            "keywords": ("送达地址确认书", "送达地址"),
            "category": "non_party",
            "side": "unknown",
            "type_name_hint": "送达地址确认书",
            "confidence": 0.97,
        },
        {
            "keywords": ("退费账户确认书", "退费账户", "收款退费账户", "收款账户确认"),
            "category": "non_party",
            "side": "unknown",
            "type_name_hint": "退费账户确认书",
            "confidence": 0.97,
        },
        {
            "keywords": ("证据清单", "证据目录", "证据材料"),
            "category": "party",
            "side": "our",
            "type_name_hint": "证据材料",
            "confidence": 0.93,
        },
    )

    def classify_contract_material(self, *, filename: str, text_excerpt: str, enable_ai: bool = True) -> dict[str, Any]:
        rule_suggestion = self._classify_contract_by_filename(filename)
        if rule_suggestion is not None:
            return rule_suggestion

        default = {
            "category": "invoice",
            "confidence": 0.0,
            "reason": "未命中关键词规则，请手动确认",
        }
        if not enable_ai:
            default["reason"] = "未启用识别，且未命中关键词规则"
            return default

        content = self._complete(
            system_prompt=(
                "你是合同材料分类助手。仅输出 JSON，不要输出其他内容。"
                'JSON 结构: {"category":"contract_original|supplementary_agreement|invoice","confidence":0-1,"reason":"..."}'
            ),
            user_prompt=(
                f"文件名: {filename}\n"
                "请根据文件名和文本片段给出材料分类。\n"
                f"文本片段:\n{text_excerpt[:1800]}"
            ),
        )
        if not content:
            default["reason"] = "AI 分类不可用，请手动确认"
            return default

        payload = self._extract_json(content)
        if not isinstance(payload, dict):
            default["reason"] = "AI 输出解析失败，请手动确认"
            return default

        category = str(payload.get("category") or "invoice").strip()
        if category not in self._CONTRACT_CATEGORIES:
            category = "invoice"

        return {
            "category": category,
            "confidence": self._to_confidence(payload.get("confidence")),
            "reason": str(payload.get("reason") or ""),
        }

    def _classify_contract_by_filename(self, filename: str) -> dict[str, Any] | None:
        normalized = (filename or "").strip().lower()
        if not normalized:
            return None

        for keyword in self._SUPPLEMENTARY_KEYWORDS:
            if keyword in normalized:
                return {
                    "category": "supplementary_agreement",
                    "confidence": 0.98,
                    "reason": f"命中文件名关键词：{keyword}",
                }

        for keyword in self._INVOICE_KEYWORDS:
            if keyword in normalized:
                return {
                    "category": "invoice",
                    "confidence": 0.98,
                    "reason": f"命中文件名关键词：{keyword}",
                }

        for keyword in self._CONTRACT_KEYWORDS:
            if keyword in normalized:
                return {
                    "category": "contract_original",
                    "confidence": 0.96,
                    "reason": f"命中文件名关键词：{keyword}",
                }

        return None

    def classify_case_material(
        self,
        *,
        filename: str,
        text_excerpt: str,
        source_path: str = "",
        enable_ai: bool = True,
        context: dict[str, Any] | None = None,
        scan_subfolder: str = "",
    ) -> dict[str, Any]:
        context = context or {}
        default = {
            "category": "unknown",
            "side": "unknown",
            "type_name_hint": "",
            "suggested_supervising_authority_id": None,
            "suggested_party_ids": [],
            "confidence": 0.0,
            "reason": "未命中关键词规则，请手动确认",
        }

        # 指定子文件夹扫描时，优先用子文件夹名作为 type_name_hint
        subfolder_hint = self._extract_subfolder_hint(scan_subfolder)

        rule_suggestion = self._classify_case_by_filename_and_path(
            filename=filename,
            source_path=source_path,
            context=context,
            subfolder_hint=subfolder_hint,
        )
        if rule_suggestion is not None:
            return rule_suggestion

        if not enable_ai:
            default["reason"] = "未启用识别，且未命中关键词规则"
            if subfolder_hint:
                default["type_name_hint"] = subfolder_hint
                default["reason"] = f"未启用识别，按扫描子文件夹命名预填（{subfolder_hint}）"
            return default

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
            default["reason"] = "AI 分类不可用，请手动确认"
            return default

        payload = self._extract_json(content)
        if not isinstance(payload, dict):
            default["reason"] = "AI 输出解析失败，请手动确认"
            return default

        category = str(payload.get("category") or "unknown").strip()
        if category not in self._CASE_CATEGORIES:
            category = "unknown"

        side = str(payload.get("side") or "unknown").strip()
        if side not in self._CASE_SIDES:
            side = "unknown"

        if category != "party":
            side = "unknown"

        return self._build_case_suggestion(
            category=category,
            side=side,
            type_name_hint=str(payload.get("type_name_hint") or "").strip(),
            confidence=self._to_confidence(payload.get("confidence")),
            reason=str(payload.get("reason") or ""),
            context=context,
        )

    def _classify_case_by_filename_and_path(
        self,
        *,
        filename: str,
        source_path: str,
        context: dict[str, Any],
        subfolder_hint: str = "",
    ) -> dict[str, Any] | None:
        filename_match_text = self._normalize_for_match(filename)
        path_match_text = self._normalize_for_match(source_path)
        match_text = self._normalize_for_match(f"{source_path} {filename}")
        if not match_text:
            return None
        in_filing_material_folder = "立案材料" in str(source_path or "")

        if in_filing_material_folder and not filename_match_text:
            return self._build_case_suggestion(
                category="party",
                side="our",
                type_name_hint=subfolder_hint or "立案材料",
                confidence=0.9,
                reason="命中目录规则：立案材料目录默认归类为我方当事人材料",
                context=context,
            )

        for rule in self._CASE_RULES:
            keywords = tuple(str(keyword) for keyword in (rule.get("keywords") or ()))
            hit_keyword = next((keyword for keyword in keywords if self._normalize_for_match(keyword) in match_text), "")
            if not hit_keyword:
                continue

            side = str(rule.get("side") or "unknown")
            if side == "auto":
                side = self._infer_case_side(match_text=filename_match_text, context=context)
                if side == "unknown":
                    side = self._infer_case_side(match_text=path_match_text, context=context)
                if side == "unknown" and context.get("our_party_ids"):
                    side = "our"
                elif side == "unknown" and context.get("opponent_party_ids"):
                    side = "opponent"

            category = str(rule.get("category") or "unknown")
            if in_filing_material_folder:
                category = "party"
                side = "our"

            # 指定子文件夹扫描时，优先用子文件夹名作为 type_name_hint
            rule_hint = str(rule.get("type_name_hint") or "").strip()
            type_name_hint = subfolder_hint or rule_hint

            return self._build_case_suggestion(
                category=category,
                side=side,
                type_name_hint=type_name_hint,
                confidence=float(rule.get("confidence") or 0.9),
                reason=(
                    f"命中目录规则：立案材料目录默认归类为我方当事人材料（关键词：{hit_keyword}）"
                    if in_filing_material_folder
                    else f"命中路径/文件名关键词：{hit_keyword}"
                ),
                context=context,
            )

        if in_filing_material_folder:
            return self._build_case_suggestion(
                category="party",
                side="our",
                type_name_hint=subfolder_hint or "立案材料",
                confidence=0.9,
                reason="命中目录规则：立案材料目录默认归类为我方当事人材料",
                context=context,
            )

        return None

    def _build_case_suggestion(
        self,
        *,
        category: str,
        side: str,
        type_name_hint: str,
        confidence: float,
        reason: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_category = category if category in self._CASE_CATEGORIES else "unknown"
        normalized_side = side if side in self._CASE_SIDES else "unknown"

        if normalized_category != "party":
            normalized_side = "unknown"

        suggested_party_ids: list[int] = []
        suggested_supervising_authority_id: int | None = None
        if normalized_category == "party":
            suggested_party_ids = self._extract_party_ids_by_side(side=normalized_side, context=context)
        elif normalized_category == "non_party":
            suggested_supervising_authority_id = self._extract_primary_supervising_authority_id(context)

        return {
            "category": normalized_category,
            "side": normalized_side,
            "type_name_hint": type_name_hint,
            "suggested_supervising_authority_id": suggested_supervising_authority_id,
            "suggested_party_ids": suggested_party_ids,
            "confidence": self._to_confidence(confidence),
            "reason": reason,
        }

    def _infer_case_side(self, *, match_text: str, context: dict[str, Any]) -> str:
        if not match_text:
            return "unknown"

        opponent_hits = 0
        our_hits = 0

        for hint in self._CASE_OPPONENT_HINTS:
            if self._normalize_for_match(hint) in match_text:
                opponent_hits += 1

        for name in context.get("opponent_party_names") or []:
            normalized_name = self._normalize_for_match(str(name))
            if normalized_name and normalized_name in match_text:
                opponent_hits += 1

        for hint in self._CASE_OUR_HINTS:
            if self._normalize_for_match(hint) in match_text:
                our_hits += 1

        for name in context.get("our_party_names") or []:
            normalized_name = self._normalize_for_match(str(name))
            if normalized_name and normalized_name in match_text:
                our_hits += 1

        if our_hits and not opponent_hits:
            return "our"
        if opponent_hits and not our_hits:
            return "opponent"
        if our_hits and opponent_hits:
            return "unknown"

        if context.get("our_party_ids"):
            return "our"
        if context.get("opponent_party_ids"):
            return "opponent"
        return "unknown"

    @staticmethod
    def _extract_party_ids_by_side(*, side: str, context: dict[str, Any]) -> list[int]:
        key = "our_party_ids" if side == "our" else "opponent_party_ids"
        raw_party_ids = context.get(key) or []
        if not isinstance(raw_party_ids, list):
            return []

        parsed: list[int] = []
        seen: set[int] = set()
        for item in raw_party_ids:
            try:
                party_id = int(item)
            except (TypeError, ValueError):
                continue
            if party_id <= 0 or party_id in seen:
                continue
            seen.add(party_id)
            parsed.append(party_id)
        return parsed

    @staticmethod
    def _extract_primary_supervising_authority_id(context: dict[str, Any]) -> int | None:
        primary = context.get("primary_supervising_authority_id")
        try:
            value = int(primary)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return value

    @staticmethod
    def _extract_subfolder_hint(scan_subfolder: str) -> str:
        """从子文件夹路径提取用户友好的类型提示名称。

        例如 "2-立案材料" → "立案材料"，"3_执行依据" → "执行依据"，
        无编号前缀则原样返回。
        """
        raw = str(scan_subfolder or "").strip()
        if not raw:
            return ""
        # 取最后一段（支持多级路径如 "子目录A/子目录B"）
        last_segment = raw.rsplit("/", 1)[-1]
        # 去掉常见编号前缀：1- / 1_ / 1. / (1) 等
        cleaned = re.sub(r"^[\d]+[\s.\-_]*[\)）]?\s*", "", last_segment).strip()
        return cleaned or last_segment

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        value = str(text or "").strip().lower()
        if not value:
            return ""
        value = value.replace("\\", "/")
        value = re.sub(r"\s+", "", value)
        return value

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
