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

    _CONTRACT_CATEGORIES = {
        "contract_original",
        "supplementary_agreement",
        "invoice",
        "supervision_card",
        "archive_document",
        "authorization_material",
    }
    _CASE_CATEGORIES = {"party", "non_party", "unknown"}
    _CASE_SIDES = {"our", "opponent", "unknown"}
    _SUPERVISION_CARD_KEYWORDS = (
        "监督卡",
        "质量监督卡",
        "服务质量监督卡",
        "办案服务质量监督卡",
        "律师办案服务质量监督卡",
    )
    _AUTHORIZATION_KEYWORDS = (
        "授权委托书",
        "授权委托",
        "委托书",
        "所函",
        "律师函",
    )
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
            "category": "archive_document",
            "confidence": 0.0,
            "reason": "未命中关键词规则，请手动确认",
        }
        if not enable_ai:
            default["reason"] = "未启用识别，且未命中关键词规则"
            return default

        content = self._complete(
            system_prompt=(
                "你是合同材料分类助手。仅输出 JSON，不要输出其他内容。"
                'JSON 结构: {"category":"contract_original|supplementary_agreement|invoice|supervision_card|archive_document|authorization_material","confidence":0-1,"reason":"..."}'
            ),
            user_prompt=(f"文件名: {filename}\n请根据文件名和文本片段给出材料分类。\n文本片段:\n{text_excerpt[:1800]}"),
        )
        if not content:
            default["reason"] = "AI 分类不可用，请手动确认"
            return default

        payload = self._extract_json(content)
        if not isinstance(payload, dict):
            default["reason"] = "AI 输出解析失败，请手动确认"
            return default

        category = str(payload.get("category") or "archive_document").strip()
        if category not in self._CONTRACT_CATEGORIES:
            category = "archive_document"

        return {
            "category": category,
            "confidence": self._to_confidence(payload.get("confidence")),
            "reason": str(payload.get("reason") or ""),
        }

    def _classify_contract_by_filename(self, filename: str) -> dict[str, Any] | None:
        normalized = (filename or "").strip().lower()
        if not normalized:
            return None

        for keyword in self._SUPERVISION_CARD_KEYWORDS:
            if keyword in normalized:
                return {
                    "category": "supervision_card",
                    "confidence": 0.98,
                    "reason": f"命中文件名关键词：{keyword}",
                }

        for keyword in self._AUTHORIZATION_KEYWORDS:
            if keyword in normalized:
                return {
                    "category": "authorization_material",
                    "confidence": 0.97,
                    "reason": f"命中文件名关键词：{keyword}",
                }

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
        parent_folder_hint: str = "",
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

        # 优先级：文件所在父文件夹名 > 扫描子文件夹名
        folder_hint = parent_folder_hint or self._extract_subfolder_hint(scan_subfolder)

        rule_suggestion = self._classify_case_by_filename_and_path(
            filename=filename,
            source_path=source_path,
            context=context,
            folder_hint=folder_hint,
        )
        if rule_suggestion is not None:
            return rule_suggestion

        if not enable_ai:
            default["reason"] = "未启用识别，且未命中关键词规则"
            if folder_hint:
                default["type_name_hint"] = folder_hint
                default["reason"] = f"未启用识别，按文件夹命名预填（{folder_hint}）"
            return default

        content = self._complete(
            system_prompt=(
                "你是案件材料预分类助手。仅输出 JSON，不要输出其他内容。"
                "只返回预填建议，不要假设你知道主管机关或当事人映射。"
                'JSON 结构: {"category":"party|non_party|unknown","side":"our|opponent|unknown","type_name_hint":"",'
                '"confidence":0-1,"reason":"..."}'
            ),
            user_prompt=(f"文件名: {filename}\n请根据文件名和文本片段给出预填建议。\n文本片段:\n{text_excerpt[:1800]}"),
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
        folder_hint: str = "",
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
                type_name_hint=folder_hint or "立案材料",
                confidence=0.9,
                reason="命中目录规则：立案材料目录默认归类为我方当事人材料",
                context=context,
            )

        for rule in self._CASE_RULES:
            keywords = tuple(str(keyword) for keyword in (rule.get("keywords") or ()))
            hit_keyword = next(
                (keyword for keyword in keywords if self._normalize_for_match(keyword) in match_text), ""
            )
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

            # 优先用文件所在文件夹名作为 type_name_hint，保持用户分类习惯
            rule_hint = str(rule.get("type_name_hint") or "").strip()
            type_name_hint = folder_hint or rule_hint

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
                type_name_hint=folder_hint or "立案材料",
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

    # ================================================================
    # 归档材料分类（合同域 → 归档清单项）
    # ================================================================

    _ARCHIVE_FOLDER_KEYWORD_RULES: dict[str, dict[str, list[str]]] = {
        # 归档分类 → { 文件夹名关键词 → archive_item_code }
        # 匹配规则：文件夹路径中包含关键词时，该文件夹下的文件映射到对应清单项
        "litigation": {
            "起诉状": "lt_7",
            "起诉书": "lt_7",
            "上诉书": "lt_7",
            "答辩状": "lt_7",
            "答辩书": "lt_7",
            "管辖依据": "lt_10",
            "材料清单": "lt_10",
            "证据材料": "lt_10",
            "主要证据": "lt_10",
            "送达地址": "lt_10",
            "委托授权": "lt_20",
            "授权委托": "lt_20",
            "原被告身份": "lt_20",
            "身份信息": "lt_20",
            "财产保全": "lt_11",
            "阅卷": "lt_8",
            "会见": "lt_9",
            "谈话笔录": "lt_9",
            "代理词": "lt_15",
            "代理意见": "lt_15",
            "辩护意见": "lt_12",
            "辩护词": "lt_12",
            "庭审笔录": "lt_16",
            "开庭笔录": "lt_16",
            "出庭通知": "lt_14",
            "传票": "lt_14",
            "判决": "lt_17",
            "裁定": "lt_17",
            "调解书": "lt_17",
            "终本裁定": "lt_17",
            "执行申请书": "lt_7",
            "执行依据": "lt_17",
            "限制性措施": "lt_10",
            "失信": "lt_10",
            "收取执行款": "lt_10",
            "续封": "lt_10",
            "解除保全": "lt_11",
        },
        "criminal": {
            "授权委托": "cr_18",
            "委托授权": "cr_18",
            "会见笔录": "cr_7",
            "会见": "cr_7",
            "取保候审": "cr_8",
            "调查材料": "cr_8",
            "不起诉申请": "cr_11",
            "起诉书": "cr_11",
            "辩护意见": "cr_12",
            "辩护词": "cr_12",
            "代理词": "cr_12",
            "判决书": "cr_14",
            "判决": "cr_14",
            "裁定书": "cr_14",
            "裁定": "cr_14",
            "出庭通知": "cr_13",
            "传票": "cr_13",
        },
        "non_litigation": {
            "授权": "nl_12",
            "委托书": "nl_12",
            "委托材料": "nl_12",
            "律师函": "nl_8",
            "法律意见书": "nl_8",
            "合同": "nl_9",
            "修订版": "nl_9",
            "批注版": "nl_9",
        },
    }

    _ARCHIVE_FILENAME_RULES: dict[str, dict[str, str]] = {
        # 归档分类 → { 文件名关键词 → archive_item_code }
        "litigation": {
            "起诉状": "lt_7",
            "起诉书": "lt_7",
            "上诉状": "lt_7",
            "上诉书": "lt_7",
            "答辩状": "lt_7",
            "答辩书": "lt_7",
            "执行申请书": "lt_7",
            "强制执行申请书": "lt_7",
            "续封申请书": "lt_7",
            "授权委托书": "lt_20",
            "所函": "lt_20",
            "律师证": "lt_20",
            "身份证": "lt_20",
            "营业执照": "lt_20",
            "送达地址确认书": "lt_10",
            "财产保全申请书": "lt_11",
            "阅卷笔录": "lt_8",
            "会见笔录": "lt_9",
            "谈话笔录": "lt_9",
            "代理词": "lt_15",
            "辩护词": "lt_12",
            "庭审笔录": "lt_16",
            "开庭笔录": "lt_16",
            "出庭通知": "lt_14",
            "传票": "lt_14",
            "判决书": "lt_17",
            "裁定书": "lt_17",
            "调解书": "lt_17",
            "终本裁定": "lt_17",
            "民事调解书": "lt_17",
            "限制高消费": "lt_10",
            "限高令": "lt_10",
            "查封": "lt_10",
            "冻结": "lt_10",
        },
        "criminal": {
            "授权委托书": "cr_18",
            "所函": "cr_18",
            "律师证": "cr_18",
            "会见笔录": "cr_7",
            "取保候审申请书": "cr_8",
            "不起诉申请书": "cr_11",
            "起诉书": "cr_11",
            "辩护词": "cr_12",
            "辩护意见": "cr_12",
            "代理词": "cr_12",
            "判决书": "cr_14",
            "裁定书": "cr_14",
            "出庭通知": "cr_13",
            "传票": "cr_13",
        },
        "non_litigation": {
            "授权委托书": "nl_12",
            "所函": "nl_12",
            "律师函": "nl_8",
            "法律意见书": "nl_8",
            "修订版": "nl_9",
            "批注版": "nl_9",
        },
    }

    def classify_archive_material(
        self,
        *,
        filename: str,
        source_path: str,
        archive_category: str,
        parent_folder_hint: str = "",
    ) -> dict[str, Any]:
        """根据文件夹路径和文件名，为合同域扫描的文件匹配归档清单项。

        Args:
            filename: 文件名（含扩展名）
            source_path: 文件完整路径
            archive_category: 归档分类 (litigation/criminal/non_litigation)
            parent_folder_hint: 父文件夹名提示

        Returns:
            dict: {
                "archive_item_code": str,  # 归档清单编号，空字符串表示未匹配
                "archive_item_name": str,  # 归档清单项名称
                "category": str,           # MaterialCategory 值
                "confidence": float,       # 匹配置信度
                "reason": str,             # 匹配原因
            }
        """
        valid_categories = {"litigation", "criminal", "non_litigation"}
        if archive_category not in valid_categories:
            archive_category = "litigation"

        # 1. 先尝试文件夹路径匹配（优先级最高，用户手动组织的分类最可靠）
        folder_result = self._match_archive_by_folder(
            source_path=source_path,
            archive_category=archive_category,
            parent_folder_hint=parent_folder_hint,
        )
        if folder_result:
            return folder_result

        # 2. 再尝试文件名匹配
        filename_result = self._match_archive_by_filename(
            filename=filename,
            archive_category=archive_category,
        )
        if filename_result:
            return filename_result

        # 3. 使用 CASE_MATERIAL_KEYWORD_MAPPING 作为兜底
        mapping_result = self._match_archive_by_keyword_mapping(
            filename=filename,
            source_path=source_path,
            archive_category=archive_category,
        )
        if mapping_result:
            return mapping_result

        # 4. 未匹配
        return {
            "archive_item_code": "",
            "archive_item_name": "未匹配",
            "category": "case_material",
            "confidence": 0.0,
            "reason": "未命中归档清单规则，请手动选择归档清单项",
        }

    def _match_archive_by_folder(
        self,
        *,
        source_path: str,
        archive_category: str,
        parent_folder_hint: str = "",
    ) -> dict[str, Any] | None:
        """通过文件夹路径匹配归档清单项。"""
        rules = self._ARCHIVE_FOLDER_KEYWORD_RULES.get(archive_category, {})
        if not rules:
            return None

        # 收集所有路径段（从source_path提取所有目录名）
        path_parts = self._extract_path_parts(source_path)
        # 也加上 parent_folder_hint
        if parent_folder_hint:
            path_parts.append(parent_folder_hint)

        # 按优先级匹配：路径中越靠后（越靠近文件）的目录名优先
        best_match: tuple[str, str] | None = None
        for part in reversed(path_parts):
            normalized_part = self._normalize_for_match(part)
            for keyword, code in rules.items():
                if self._normalize_for_match(keyword) in normalized_part:
                    best_match = (keyword, code)
                    break
            if best_match:
                break

        if not best_match:
            return None

        keyword, code = best_match
        item_name = self._get_archive_item_name(archive_category, code)
        return {
            "archive_item_code": code,
            "archive_item_name": item_name,
            "category": "case_material",
            "confidence": 0.95,
            "reason": f"命中文件夹关键词：{keyword} → {item_name}",
        }

    def _match_archive_by_filename(
        self,
        *,
        filename: str,
        archive_category: str,
    ) -> dict[str, Any] | None:
        """通过文件名匹配归档清单项。"""
        rules = self._ARCHIVE_FILENAME_RULES.get(archive_category, {})
        if not rules:
            return None

        normalized_filename = self._normalize_for_match(filename)

        # 按关键词长度倒序匹配（更具体的关键词优先）
        sorted_rules = sorted(rules.items(), key=lambda x: len(x[0]), reverse=True)
        for keyword, code in sorted_rules:
            if self._normalize_for_match(keyword) in normalized_filename:
                item_name = self._get_archive_item_name(archive_category, code)
                return {
                    "archive_item_code": code,
                    "archive_item_name": item_name,
                    "category": "case_material",
                    "confidence": 0.90,
                    "reason": f"命中文件名关键词：{keyword} → {item_name}",
                }

        return None

    def _match_archive_by_keyword_mapping(
        self,
        *,
        filename: str,
        source_path: str,
        archive_category: str,
    ) -> dict[str, Any] | None:
        """通过 CASE_MATERIAL_KEYWORD_MAPPING 兜底匹配。"""
        from apps.contracts.services.archive.constants import CASE_MATERIAL_KEYWORD_MAPPING

        mapping = CASE_MATERIAL_KEYWORD_MAPPING.get(archive_category, {})
        if not mapping:
            return None

        match_text = self._normalize_for_match(f"{source_path} {filename}")

        for code, keywords in mapping.items():
            for keyword in keywords:
                if self._normalize_for_match(keyword) in match_text:
                    item_name = self._get_archive_item_name(archive_category, code)
                    return {
                        "archive_item_code": code,
                        "archive_item_name": item_name,
                        "category": "case_material",
                        "confidence": 0.80,
                        "reason": f"命中关键词映射：{keyword} → {item_name}",
                    }

        return None

    @staticmethod
    def _extract_path_parts(source_path: str) -> list[str]:
        """从文件路径提取所有目录名（去掉编号前缀）。"""
        from pathlib import Path

        parts: list[str] = []
        p = Path(source_path)
        for part in p.parent.parts:
            # 去掉编号前缀：1- / 2_ / 3. 等
            cleaned = re.sub(r"^[\d]+[\s.\-_]*[\)）]?\s*", "", part).strip()
            if cleaned and cleaned != part or len(cleaned) > 0:
                parts.append(cleaned if cleaned else part)
        return parts

    @staticmethod
    def _get_archive_item_name(archive_category: str, code: str) -> str:
        """根据归档分类和编号获取清单项名称。"""
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST

        checklist = ARCHIVE_CHECKLIST.get(archive_category, [])
        for item in checklist:
            if item.get("code") == code:
                return str(item.get("name") or "")
        return ""

    @staticmethod
    def parse_work_log_from_folder_name(folder_name: str) -> dict[str, str] | None:
        """从常法办案子文件夹名解析律师工作日志信息。

        文件夹名格式：YYYY.MM.DD-事项名
        例如：2025.01.23-知识产权合同 → {date: "2025-01-23", content: "审核知识产权合同"}

        Args:
            folder_name: 文件夹名

        Returns:
            解析结果或 None（不匹配时）
        """
        pattern = r"^(\d{4})[\.\-](\d{2})[\.\-](\d{2})[\s.\-_]+(.+)$"
        match = re.match(pattern, folder_name.strip())
        if not match:
            return None

        year, month, day, task = match.group(1), match.group(2), match.group(3), match.group(4)
        date_str = f"{year}-{month}-{day}"

        # 自动补全"审核"字段
        content = f"审核{task.strip()}"

        return {"date": date_str, "content": content}

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
