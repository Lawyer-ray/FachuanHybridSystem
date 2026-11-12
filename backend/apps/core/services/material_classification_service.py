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
        "case_material",
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
    # "合同"/"协议"出现在这些上下文中时，是案由/描述而非合同本身，应跳过
    _CONTRACT_FALSE_POSITIVE_PATTERNS = (
        "合同纠纷",
        "协议纠纷",
        "合同争议",
        "协议争议",
    )
    # 诉讼/刑事文书关键词 — 命中时不应归为合同正本，应归为 archive_document
    # （后续由归档分类器匹配到 case_material + archive_item_code）
    _LITIGATION_DOCUMENT_KEYWORDS = (
        "起诉状",
        "起诉书",
        "上诉状",
        "上诉书",
        "答辩状",
        "答辩书",
        "执行申请书",
        "强制执行申请书",
        "判决书",
        "裁定书",
        "调解书",
        "代理词",
        "辩护词",
        "辩护意见",
        "庭审笔录",
        "开庭笔录",
        "传票",
        "出庭通知",
        "阅卷笔录",
        "会见笔录",
        "谈话笔录",
        "财产保全",
        "限制高消费",
        "限高令",
        "终本裁定",
        "不予立案",
        "受理通知",
        "举证通知",
        "应诉通知",
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

    # 文件夹名关键词 — 文件所在文件夹属于"合同发票"区域时启用合同域细分分类
    # 支持多种文件夹命名方式：
    # - 组合词（包含式匹配）：合同发票、合同及发票，如 "1-合同发票"
    # - 单独文件夹（剥离数字前缀后整名相等）：合同、合同正本、发票、补充协议、监督卡
    #   如 "1-合同"、"2-补充协议"、"3-发票"、"4-监督卡"
    # 必须按"文件夹名"逐段匹配，禁止对整个路径做子串匹配——
    # 绑定根目录名通常含案由（如"…买卖合同纠纷一案"），整路径子串匹配裸"合同"
    # 会把一审等诉讼子目录下的全部文件误判进合同发票区域（2026-10-20 合同 8 事故）。
    _CONTRACT_INVOICE_COMBO_KEYWORDS: tuple[str, ...] = ("合同发票", "合同及发票")
    _CONTRACT_INVOICE_EXACT_KEYWORDS: tuple[str, ...] = ("合同", "合同正本", "发票", "补充协议", "监督卡")
    _FOLDER_NAME_PREFIX_RE = re.compile(r"^\s*\d+[.\-、_]+\s*")

    def _is_contract_invoice_folder(self, source_path: str) -> bool:
        """判断文件是否位于"合同发票"区域文件夹。

        只匹配文件夹名分段：末段无尾斜杠时视为文件名不参与判定；
        单词关键词须在剥离数字前缀后整名相等，组合词允许包含式命中。
        """
        raw = (source_path or "").replace("\\", "/")
        segments = [seg for seg in raw.split("/") if seg]
        if segments and not raw.endswith("/"):
            segments = segments[:-1]

        for segment in segments:
            folder_name = self._FOLDER_NAME_PREFIX_RE.sub("", segment).strip()
            if not folder_name:
                continue
            if any(kw in folder_name for kw in self._CONTRACT_INVOICE_COMBO_KEYWORDS):
                return True
            if folder_name in self._CONTRACT_INVOICE_EXACT_KEYWORDS:
                return True
        return False

    def classify_contract_material(
        self,
        *,
        filename: str,
        text_excerpt: str,
        source_path: str = "",
        enable_ai: bool = True,
    ) -> dict[str, Any]:
        # ── 最高优先级：文件夹路径分类 ──
        # 位于"合同发票"文件夹 → 合同/发票区域；否则一律为案件材料
        if self._is_contract_invoice_folder(source_path):
            # 在"合同发票"文件夹内，仅区分合同正本 / 补充协议 / 发票 / 监督卡
            rule_suggestion = self._classify_contract_by_filename(filename)
            if rule_suggestion is not None:
                return rule_suggestion
            # 未命中关键词，默认合同正本
            return {
                "category": "contract_original",
                "confidence": 0.5,
                "reason": "位于合同发票文件夹，默认为合同正本",
            }

        # 不在"合同发票"文件夹 → 一律案件材料
        return {
            "category": "case_material",
            "confidence": 0.95,
            "reason": "非合同发票文件夹，归为案件材料",
        }

    def _classify_contract_by_filename(self, filename: str) -> dict[str, Any] | None:
        """在"合同发票"文件夹内，根据文件名区分合同正本/补充协议/发票/监督卡。

        此方法仅由 classify_contract_material 在确认文件位于"合同发票"文件夹后调用，
        因此不需要处理诉讼文书排除逻辑。
        """
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

        # 检查"合同"/"协议"关键词，但排除"合同纠纷"等案由描述
        for keyword in self._CONTRACT_KEYWORDS:
            if keyword in normalized:
                # 排除"合同纠纷"/"协议纠纷"等案由描述中的误匹配
                if any(fp in normalized for fp in self._CONTRACT_FALSE_POSITIVE_PATTERNS):
                    continue
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
        default: dict[str, Any] = {
            "category": "unknown",
            "side": "unknown",
            "type_name_hint": "",
            "suggested_supervising_authority_id": None,
            "suggested_party_ids": [],
            "confidence": 0.0,
            "reason": "未命中关键词规则，请手动确认",
        }

        # 优先级：文件所在父文件夹名 > 扫描子文件夹名
        folder_hint = parent_folder_hint or _extract_subfolder_hint(scan_subfolder)

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

        payload = _extract_json(content)
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
        filename_match_text = _normalize_for_match(filename)
        path_match_text = _normalize_for_match(source_path)
        match_text = _normalize_for_match(f"{source_path} {filename}")
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
            hit_keyword = next((keyword for keyword in keywords if _normalize_for_match(keyword) in match_text), "")
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
            suggested_party_ids = _extract_party_ids_by_side(side=normalized_side, context=context)
        elif normalized_category == "non_party":
            suggested_supervising_authority_id = _extract_primary_supervising_authority_id(context)

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
            if _normalize_for_match(hint) in match_text:
                opponent_hits += 1

        for name in context.get("opponent_party_names") or []:
            normalized_name = _normalize_for_match(str(name))
            if normalized_name and normalized_name in match_text:
                opponent_hits += 1

        for hint in self._CASE_OUR_HINTS:
            if _normalize_for_match(hint) in match_text:
                our_hits += 1

        for name in context.get("our_party_names") or []:
            normalized_name = _normalize_for_match(str(name))
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

    def _complete(self, *, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover
        try:
            response = get_llm_service().complete(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=300,
            )
            return str(getattr(response, "content", "") or "")
        except Exception:
            logger.exception("material_classification_failed")
            return ""

    async def _acomplete(self, *, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover
        """Async version of _complete — uses async LLM client to avoid blocking the event loop."""
        try:
            response = await get_llm_service().achat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            return str(getattr(response, "content", "") or "")
        except Exception:
            logger.exception("material_classification_async_failed")
            return ""

    # 归档分类已统一由 apps.contracts.services.contract.integrations.archive_classifier
    # 提供（含跳过规则与证据文件夹特判）。此处曾有一份无调用方的副本，2026-11 删除。

    def parse_work_log_from_folder_name(self, folder_name: str) -> dict[str, str] | None:
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

    def _to_confidence(self, value: Any) -> float:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return 0.0
        if val < 0:
            return 0.0
        if val > 1:
            return 1.0
        return val


# ↓↓ 由 MaterialClassificationService 下沉的模块级纯函数（四层架构静态方法棘轮）
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


# ↓↓ 由 MaterialClassificationService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _extract_primary_supervising_authority_id(context: dict[str, Any]) -> int | None:
    primary = context.get("primary_supervising_authority_id")
    if primary is None:
        return None
    try:
        value = int(primary)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


# ↓↓ 由 MaterialClassificationService 下沉的模块级纯函数（四层架构静态方法棘轮）
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


# ↓↓ 由 MaterialClassificationService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _normalize_for_match(text: str) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""
    value = value.replace("\\", "/")
    value = re.sub(r"\s+", "", value)
    return value


# ↓↓ 由 MaterialClassificationService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _extract_json(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None

    for candidate in (text, *re.findall(r"\{[\s\S]*\}", text)):
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            continue

    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    for block in fenced:
        try:
            loaded = json.loads(block)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            continue

    return None
