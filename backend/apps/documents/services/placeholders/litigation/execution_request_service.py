"""强制执行申请书 - 申请执行事项规则引擎服务."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, ClassVar

from apps.cases.models import Case, CaseNumber
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.finance.services.calculator.interest_calculator import InterestCalculator
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)

AMOUNT_PATTERN = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
AMOUNT_WITH_UNIT_PATTERN = rf"{AMOUNT_PATTERN}\s*(万)?\s*元?"
VALID_DATE_INCLUSION = {"both", "start_only", "end_only", "neither"}
VALID_YEAR_DAYS = {0, 360, 365}

FULLWIDTH_TRANSLATION = str.maketrans({
    "０": "0",
    "１": "1",
    "２": "2",
    "３": "3",
    "４": "4",
    "５": "5",
    "６": "6",
    "７": "7",
    "８": "8",
    "９": "9",
    "．": ".",
    "，": ",",
    "％": "%",
    "：": ":",
    "（": "(",
    "）": ")",
    "　": " ",
})


@dataclass
class FeeItem:
    key: str
    label: str
    amount: Decimal
    include: bool
    reason: str = ""


@dataclass
class ParsedAmounts:
    principal: Decimal | None = None
    principal_label: str = "借款本金"
    confirmed_interest: Decimal = Decimal("0")
    attorney_fee: Decimal = Decimal("0")
    guarantee_fee: Decimal = Decimal("0")
    litigation_fee: Decimal = Decimal("0")
    preservation_fee: Decimal = Decimal("0")
    announcement_fee: Decimal = Decimal("0")
    excluded_fees: list[FeeItem] = field(default_factory=list)


@dataclass
class ParsedInterestParams:
    start_date: date | None = None
    rate_type: str = "1y"
    multiplier: Decimal | None = None
    custom_rate_unit: str | None = None
    custom_rate_value: Decimal | None = None
    interest_cap: Decimal | None = None
    rate_description: str = ""
    base_mode: str = "fallback_target"
    base_amount: Decimal | None = None


@dataclass
class ExecutionComputation:
    preview_text: str
    warnings: list[str]
    structured_params: dict[str, Any]


@PlaceholderRegistry.register
class ExecutionRequestService(BasePlaceholderService):
    """申请执行事项规则引擎（纯规则，不依赖 LLM）."""

    name: str = "enforcement_execution_request_service"
    display_name: str = "诉讼文书-强制执行申请书申请执行事项"
    description: str = "生成强制执行申请书模板中的申请执行事项"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST]

    DEDUCTION_KEY_TO_COMPONENT: ClassVar[dict[str, str]] = {
        "litigation_fee": "litigation_fee",
        "preservation_fee": "preservation_fee",
        "announcement_fee": "announcement_fee",
        "attorney_fee": "attorney_fee",
        "guarantee_fee": "guarantee_fee",
        "interest": "confirmed_interest",
        "principal": "principal",
    }
    DEDUCTION_KEY_TO_LABEL: ClassVar[dict[str, str]] = {
        "litigation_fee": "受理费",
        "preservation_fee": "财产保全费",
        "announcement_fee": "公告费",
        "attorney_fee": "律师代理费",
        "guarantee_fee": "财产保全担保费",
        "interest": "利息",
        "principal": "本金",
    }
    OLLAMA_FALLBACK_MODEL: ClassVar[str] = "qwen3.5:0.8b"
    OLLAMA_MAX_TEXT_CHARS: ClassVar[int] = 12000

    def __init__(self) -> None:
        self.calculator = InterestCalculator()

    def generate(self, context_data: dict[str, Any]) -> dict[str, str]:
        case_id = context_data.get("case_id")
        if case_id is None:
            case_obj = context_data.get("case")
            case_id = getattr(case_obj, "id", None)
        if not case_id:
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: ""}

        case = Case.objects.filter(id=case_id).first()
        if case is None:
            logger.warning("案件不存在: case_id=%s", case_id)
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: ""}

        case_number = self._select_primary_case_number(case_id)
        if case_number is None:
            logger.warning("案件没有案号信息: case_id=%s", case_id)
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: ""}

        manual_text = (case_number.execution_manual_text or "").strip()
        if manual_text:
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: manual_text}

        result = self._build_execution_request(case=case, case_number=case_number)
        return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: result.preview_text}

    def preview_for_case_number(
        self,
        *,
        case: Case,
        case_number: CaseNumber,
        cutoff_date: date | None = None,
        paid_amount: Decimal | None = None,
        use_deduction_order: bool | None = None,
        year_days: int | None = None,
        date_inclusion: str | None = None,
        enable_llm_fallback: bool | None = None,
    ) -> dict[str, Any]:
        result = self._build_execution_request(
            case=case,
            case_number=case_number,
            cutoff_date=cutoff_date,
            paid_amount=paid_amount,
            use_deduction_order=use_deduction_order,
            year_days=year_days,
            date_inclusion=date_inclusion,
            enable_llm_fallback=enable_llm_fallback,
        )
        return {
            "preview_text": result.preview_text,
            "structured_params": result.structured_params,
            "warnings": result.warnings,
        }

    def _select_primary_case_number(self, case_id: int) -> CaseNumber | None:
        case_numbers = list(CaseNumber.objects.filter(case_id=case_id).order_by("id"))
        if not case_numbers:
            return None

        for cn in case_numbers:
            if cn.is_active and ((cn.document_content or "").strip() or (cn.execution_manual_text or "").strip()):
                return cn

        for cn in case_numbers:
            if (cn.document_content or "").strip() or (cn.execution_manual_text or "").strip():
                return cn

        return case_numbers[0]

    def _build_execution_request(
        self,
        *,
        case: Case,
        case_number: CaseNumber,
        cutoff_date: date | None = None,
        paid_amount: Decimal | None = None,
        use_deduction_order: bool | None = None,
        year_days: int | None = None,
        date_inclusion: str | None = None,
        enable_llm_fallback: bool | None = None,
    ) -> ExecutionComputation:
        warnings: list[str] = []
        main_text = (case_number.document_content or "").strip()
        if not main_text:
            return ExecutionComputation(
                preview_text="",
                warnings=["执行依据主文为空，无法解析申请执行事项。"],
                structured_params={},
            )

        normalized_text = self._normalize_text(main_text)
        amounts = self._parse_confirmed_amounts(normalized_text)
        principal_fallback_to_target = False
        if amounts.principal is None:
            target_amount = self._safe_decimal(case.target_amount)
            if target_amount > 0:
                amounts.principal = target_amount
                if "货款" in normalized_text:
                    amounts.principal_label = "货款本金"
                warnings.append("未从文书解析到本金，已回退使用案件“涉案金额”。")
                principal_fallback_to_target = True
            else:
                warnings.append("未能确定本金，申请执行事项未生成。")
                return ExecutionComputation(preview_text="", warnings=warnings, structured_params={})

        paid = paid_amount if paid_amount is not None else self._safe_decimal(case_number.execution_paid_amount)
        paid = max(paid, Decimal("0"))
        use_order = bool(case_number.execution_use_deduction_order) if use_deduction_order is None else use_deduction_order
        calc_year_days = self._normalize_year_days(year_days if year_days is not None else case_number.execution_year_days)
        calc_date_inclusion = self._normalize_date_inclusion(
            date_inclusion if date_inclusion is not None else case_number.execution_date_inclusion
        )
        calc_cutoff = cutoff_date or case_number.execution_cutoff_date or case.specified_date or date.today()

        deduction_order = self._parse_deduction_order(normalized_text)
        amounts, principal_paid, deduction_applied = self._apply_paid_amount(
            amounts=amounts,
            paid_amount=paid,
            deduction_order=deduction_order if use_order else [],
        )

        params = self._parse_interest_params(normalized_text)
        has_double_interest_clause = self._has_double_interest_clause(normalized_text)
        llm_fallback_enabled = True if enable_llm_fallback is None else bool(enable_llm_fallback)
        llm_fallback_used = False
        if llm_fallback_enabled and self._should_try_llm_fallback(
            text=normalized_text,
            amounts=amounts,
            params=params,
            principal_fallback_to_target=principal_fallback_to_target,
        ):
            llm_data = self._extract_with_ollama_fallback(normalized_text)
            if llm_data:
                llm_fallback_used = self._merge_llm_fallback(
                    amounts=amounts,
                    params=params,
                    llm_data=llm_data,
                    principal_fallback_to_target=principal_fallback_to_target,
                )
                if llm_data.get("has_double_interest_clause") is True:
                    has_double_interest_clause = True
                if llm_fallback_used:
                    warnings.append("规则置信度不足，已使用本地Ollama兜底解析。")

        interest_base = self._resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=principal_paid)
        overdue_interest = self._calculate_interest(
            principal=interest_base,
            params=params,
            cutoff_date=calc_cutoff,
            year_days=calc_year_days,
            date_inclusion=calc_date_inclusion,
            warnings=warnings,
        )
        if (
            overdue_interest <= 0
            and params.start_date is not None
            and (params.multiplier is not None or params.custom_rate_value is not None)
            and calc_cutoff >= params.start_date
            and not llm_fallback_used
            and llm_fallback_enabled
        ):
            llm_data = self._extract_with_ollama_fallback(normalized_text)
            if llm_data:
                llm_fallback_used = self._merge_llm_fallback(
                    amounts=amounts,
                    params=params,
                    llm_data=llm_data,
                    principal_fallback_to_target=principal_fallback_to_target,
                )
                if llm_data.get("has_double_interest_clause") is True:
                    has_double_interest_clause = True
                interest_base = self._resolve_interest_base(
                    case=case, amounts=amounts, params=params, principal_paid=principal_paid
                )
                overdue_interest = self._calculate_interest(
                    principal=interest_base,
                    params=params,
                    cutoff_date=calc_cutoff,
                    year_days=calc_year_days,
                    date_inclusion=calc_date_inclusion,
                    warnings=warnings,
                )
                if llm_fallback_used:
                    warnings.append("规则利息解析失败，已使用本地Ollama兜底修正。")

        for fee in amounts.excluded_fees:
            warnings.append(
                f"{fee.label}{self._format_amount(fee.amount)}元已排除：{fee.reason}"
            )

        total = (
            (amounts.principal or Decimal("0"))
            + amounts.confirmed_interest
            + overdue_interest
            + amounts.litigation_fee
            + amounts.preservation_fee
            + amounts.announcement_fee
            + amounts.attorney_fee
            + amounts.guarantee_fee
        )

        preview_text = self._generate_request_text(
            full_case_number=self._format_case_number(case_number),
            amounts=amounts,
            params=params,
            overdue_interest=overdue_interest,
            interest_base=interest_base,
            cutoff_date=calc_cutoff,
            total=total,
            has_double_interest_clause=has_double_interest_clause,
        )

        structured = {
            "case_number": case_number.number,
            "document_name": case_number.document_name or "",
            "principal_label": amounts.principal_label,
            "principal": self._format_amount(amounts.principal),
            "confirmed_interest": self._format_amount(amounts.confirmed_interest),
            "litigation_fee": self._format_amount(amounts.litigation_fee),
            "preservation_fee": self._format_amount(amounts.preservation_fee),
            "announcement_fee": self._format_amount(amounts.announcement_fee),
            "attorney_fee": self._format_amount(amounts.attorney_fee),
            "guarantee_fee": self._format_amount(amounts.guarantee_fee),
            "paid_amount": self._format_amount(paid),
            "deduction_order": [self.DEDUCTION_KEY_TO_LABEL.get(k, k) for k in deduction_order],
            "deduction_applied": [
                {
                    "component": self.DEDUCTION_KEY_TO_LABEL.get(item["key"], item["key"]),
                    "amount": self._format_amount(item["amount"]),
                }
                for item in deduction_applied
            ],
            "interest_start_date": params.start_date.isoformat() if params.start_date else "",
            "interest_rate_description": params.rate_description,
            "interest_base": self._format_amount(interest_base),
            "interest_cap": self._format_amount(params.interest_cap),
            "cutoff_date": calc_cutoff.isoformat(),
            "year_days": calc_year_days,
            "date_inclusion": calc_date_inclusion,
            "overdue_interest": self._format_amount(overdue_interest),
            "total": self._format_amount(total),
            "has_double_interest_clause": has_double_interest_clause,
            "llm_fallback_enabled": llm_fallback_enabled,
            "llm_fallback_used": llm_fallback_used,
            "excluded_fees": [
                {
                    "label": fee.label,
                    "amount": self._format_amount(fee.amount),
                    "reason": fee.reason,
                }
                for fee in amounts.excluded_fees
            ],
        }

        return ExecutionComputation(preview_text=preview_text, warnings=warnings, structured_params=structured)

    def _should_try_llm_fallback(
        self,
        *,
        text: str,
        amounts: ParsedAmounts,
        params: ParsedInterestParams,
        principal_fallback_to_target: bool,
    ) -> bool:
        if principal_fallback_to_target:
            return True

        principal = amounts.principal or Decimal("0")
        if re.search(r"[0-9]+\s*万\s*元", text) and principal < Decimal("10000"):
            return True

        if "受理费" in text and amounts.litigation_fee <= 0 and "负担" in text and any(k in text for k in ("预交", "已交")):
            return True
        if any(k in text for k in ("保全费", "财产保全费")) and amounts.preservation_fee <= 0 and (
            "负担" in text and any(k in text for k in ("预交", "已缴", "迳付"))
        ):
            return True

        if params.start_date and params.multiplier is None and params.custom_rate_value is None:
            return True
        return False

    def _merge_llm_fallback(
        self,
        *,
        amounts: ParsedAmounts,
        params: ParsedInterestParams,
        llm_data: dict[str, Any],
        principal_fallback_to_target: bool,
    ) -> bool:
        changed = False

        llm_principal = llm_data.get("principal_amount")
        if isinstance(llm_principal, Decimal) and llm_principal > 0:
            current_principal = amounts.principal or Decimal("0")
            if principal_fallback_to_target or current_principal <= 0 or (
                current_principal < Decimal("10000") and llm_principal >= Decimal("10000")
            ):
                amounts.principal = llm_principal
                principal_desc = str(llm_data.get("principal_label") or "").strip()
                if "货" in principal_desc:
                    amounts.principal_label = "货款本金"
                elif principal_desc:
                    amounts.principal_label = "借款本金"
                changed = True

        for field_name, key in (
            ("litigation_fee", "litigation_fee"),
            ("preservation_fee", "preservation_fee"),
            ("announcement_fee", "announcement_fee"),
            ("attorney_fee", "attorney_fee"),
            ("guarantee_fee", "guarantee_fee"),
        ):
            current = getattr(amounts, field_name)
            llm_value = llm_data.get(key)
            if current <= 0 and isinstance(llm_value, Decimal) and llm_value > 0:
                setattr(amounts, field_name, llm_value)
                changed = True

        llm_start_date = llm_data.get("interest_start_date")
        if params.start_date is None and isinstance(llm_start_date, date):
            params.start_date = llm_start_date
            changed = True

        llm_lpr_multiplier = llm_data.get("lpr_multiplier")
        if (
            params.multiplier is None
            and params.custom_rate_value is None
            and isinstance(llm_lpr_multiplier, Decimal)
            and llm_lpr_multiplier > 0
        ):
            params.multiplier = llm_lpr_multiplier
            params.rate_type = "1y"
            params.rate_description = (
                f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{self._format_amount(llm_lpr_multiplier)}倍"
            )
            changed = True

        llm_fixed_rate = llm_data.get("fixed_rate_percent")
        if (
            params.multiplier is None
            and params.custom_rate_value is None
            and isinstance(llm_fixed_rate, Decimal)
            and llm_fixed_rate > 0
        ):
            params.custom_rate_unit = "percent"
            params.custom_rate_value = llm_fixed_rate
            params.rate_description = f"年利率{self._format_amount(llm_fixed_rate)}%"
            changed = True

        llm_interest_base = llm_data.get("interest_base_amount")
        if isinstance(llm_interest_base, Decimal) and llm_interest_base > 0:
            if params.base_amount is None or (
                params.base_amount < Decimal("10000") and llm_interest_base >= Decimal("10000")
            ):
                params.base_mode = "fixed_amount"
                params.base_amount = llm_interest_base
                changed = True

        return changed

    def _extract_with_ollama_fallback(self, main_text: str) -> dict[str, Any] | None:
        prompt = (
            "你是法律文书金额与利率解析助手。仅输出 JSON，不要输出其他文字。\n"
            "要求：所有金额统一换算为“元”（例如“52万元”=520000）；利率倍数用数字表示。\n"
            "只返回以下 JSON 字段：\n"
            "{\n"
            '  "principal_amount_yuan": number|null,\n'
            '  "principal_label": "借款本金|货款本金|本金|",\n'
            '  "interest_start_date": "YYYY-MM-DD"|null,\n'
            '  "interest_base_amount_yuan": number|null,\n'
            '  "lpr_multiplier": number|null,\n'
            '  "fixed_rate_percent": number|null,\n'
            '  "litigation_fee": number|null,\n'
            '  "preservation_fee": number|null,\n'
            '  "announcement_fee": number|null,\n'
            '  "attorney_fee": number|null,\n'
            '  "guarantee_fee": number|null,\n'
            '  "has_double_interest_clause": true|false\n'
            "}\n"
            "文书如下：\n"
            f"{main_text[:self.OLLAMA_MAX_TEXT_CHARS]}"
        )

        try:
            from apps.core.services.wiring import get_llm_service

            response = get_llm_service().complete(
                prompt=prompt,
                backend="ollama",
                model=self.OLLAMA_FALLBACK_MODEL,
                temperature=0.1,
                max_tokens=500,
                fallback=False,
                timeout=8.0,
                num_predict=500,
            )
            content = str(getattr(response, "content", "") or "")
        except Exception:
            logger.exception("execution_request_ollama_fallback_failed")
            return None

        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            return None

        parsed: dict[str, Any] = {
            "principal_amount": self._safe_decimal(payload.get("principal_amount_yuan")),
            "principal_label": str(payload.get("principal_label") or "").strip(),
            "interest_base_amount": self._safe_decimal(payload.get("interest_base_amount_yuan")),
            "lpr_multiplier": self._safe_decimal(payload.get("lpr_multiplier")),
            "fixed_rate_percent": self._safe_decimal(payload.get("fixed_rate_percent")),
            "litigation_fee": self._safe_decimal(payload.get("litigation_fee")),
            "preservation_fee": self._safe_decimal(payload.get("preservation_fee")),
            "announcement_fee": self._safe_decimal(payload.get("announcement_fee")),
            "attorney_fee": self._safe_decimal(payload.get("attorney_fee")),
            "guarantee_fee": self._safe_decimal(payload.get("guarantee_fee")),
            "has_double_interest_clause": self._parse_bool(payload.get("has_double_interest_clause")),
        }

        start_date_value = payload.get("interest_start_date")
        parsed["interest_start_date"] = self._parse_iso_date(start_date_value)
        return parsed

    def _extract_json_object(self, content: str) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None

        candidates = [text]
        candidates.extend(re.findall(r"\{[\s\S]*\}", text))
        fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        candidates.extend(fenced)

        for candidate in candidates:
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                continue
        return None

    def _parse_iso_date(self, value: Any) -> date | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            year, month, day = text.split("-")
            return date(int(year), int(month), int(day))
        except Exception:
            return None

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "是"}:
            return True
        if text in {"false", "0", "no", "n", "否"}:
            return False
        return False

    def _parse_confirmed_amounts(self, main_text: str) -> ParsedAmounts:
        amounts = ParsedAmounts()

        principal_patterns = [
            re.compile(
                rf"(?:偿还|支付|归还|尚欠(?:原告|申请人)?|尚欠)\s*(借款|货款)(?:本金)?\s*{AMOUNT_WITH_UNIT_PATTERN}"
            ),
            re.compile(rf"(借款|货款)本金\s*{AMOUNT_WITH_UNIT_PATTERN}"),
        ]
        for pattern in principal_patterns:
            match = pattern.search(main_text)
            if not match:
                continue
            kind = match.group(1)
            amount_value = self._parse_amount_value(match.group(2), match.group(3))
            if amount_value is None:
                continue
            amounts.principal = amount_value
            amounts.principal_label = "货款本金" if "货款" in kind else "借款本金"
            break

        for interest_match in re.finditer(rf"利息\s*{AMOUNT_WITH_UNIT_PATTERN}", main_text):
            prefix = main_text[max(0, interest_match.start() - 6):interest_match.start()]
            if "逾期" in prefix:
                continue
            amount_value = self._parse_amount_value(interest_match.group(1), interest_match.group(2))
            if amount_value is not None:
                amounts.confirmed_interest = amount_value
                break

        fee_items = self._parse_fee_items(main_text)
        for fee in fee_items:
            if not fee.include:
                amounts.excluded_fees.append(fee)
                continue
            if fee.key == "litigation_fee":
                amounts.litigation_fee += fee.amount
            elif fee.key == "preservation_fee":
                amounts.preservation_fee += fee.amount
            elif fee.key == "announcement_fee":
                amounts.announcement_fee += fee.amount
            elif fee.key == "attorney_fee":
                amounts.attorney_fee += fee.amount
            elif fee.key == "guarantee_fee":
                amounts.guarantee_fee += fee.amount

        return amounts

    def _parse_fee_items(self, main_text: str) -> list[FeeItem]:
        patterns: list[tuple[str, str, re.Pattern[str]]] = [
            ("litigation_fee", "受理费", re.compile(rf"受理费(?:减半收取)?(?:\s*(?:为|计))?\s*{AMOUNT_WITH_UNIT_PATTERN}")),
            (
                "preservation_fee",
                "财产保全费",
                re.compile(rf"(?:诉前)?(?:财产保全申请费|财产保全费|保全费)\s*{AMOUNT_WITH_UNIT_PATTERN}"),
            ),
            ("announcement_fee", "公告费", re.compile(rf"公告费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
            ("attorney_fee", "律师代理费", re.compile(rf"(?:律师代理费|律师费)\s*{AMOUNT_WITH_UNIT_PATTERN}")),
            ("guarantee_fee", "财产保全担保费", re.compile(rf"财产保全担保费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
        ]
        fee_items: list[FeeItem] = []

        for key, label, pattern in patterns:
            for match in pattern.finditer(main_text):
                amount_value = self._parse_amount_value(match.group(1), match.group(2))
                if amount_value is None:
                    continue
                sentence = self._extract_sentence(main_text, match.start(), match.end())
                include, reason = self._should_include_fee(sentence=sentence, key=key)
                fee_items.append(
                    FeeItem(
                        key=key,
                        label=label,
                        amount=amount_value,
                        include=include,
                        reason=reason,
                    )
                )

        return fee_items

    def _should_include_fee(self, *, sentence: str, key: str) -> tuple[bool, str]:
        # 律师费/担保费通常为“应向原告支付的款项构成部分”，默认纳入
        if key in {"attorney_fee", "guarantee_fee"}:
            return True, ""

        compact = sentence.replace(" ", "")
        pay_to_applicant_markers = (
            "支付给原告",
            "支付给申请人",
            "支付至原告",
            "支付至申请人",
            "返还给原告",
            "返还给申请人",
            "返还至原告",
            "返还至申请人",
            "直接支付给原告",
            "直接支付给申请人",
            "迳付原告",
            "迳付申请人",
            "迳付予原告",
            "迳付予申请人",
            "向原告支付",
            "向申请人支付",
        )
        court_markers = ("向本院缴纳", "向法院缴纳", "缴纳至本院", "本院退回", "法院退回", "交至本院")

        if any(marker in compact for marker in pay_to_applicant_markers):
            return True, ""
        if ("向原告" in compact or "向申请人" in compact) and "支付" in compact:
            return True, ""
        if any(marker in compact for marker in court_markers):
            return False, "向法院缴纳/法院退回"
        prepaid_markers = ("原告已预交", "原告已缴纳", "原告已交", "申请人已预交", "申请人已缴纳", "申请人已交")
        burden_by_respondent = any(marker in compact for marker in ("由被告", "由两被告", "由各被告"))
        if (
            burden_by_respondent
            and "负担" in compact
            and "原告负担" not in compact
            and "申请人负担" not in compact
            and any(marker in compact for marker in prepaid_markers)
        ):
            return True, ""
        return False, "未明确支付给申请人/原告"

    def _parse_interest_params(self, main_text: str) -> ParsedInterestParams:
        params = ParsedInterestParams()
        clause = self._extract_interest_clause(main_text)

        lpr_pattern = re.compile(
            r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)\s*倍"
        )
        lpr_markup_pattern = re.compile(
            r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?上浮\s*([0-9]+(?:\.[0-9]+)?)\s*%"
        )
        fixed_pattern = re.compile(r"(?:(?:按|起按|按照)\s*)?年利率\s*([0-9]+(?:\.[0-9]+)?)\s*%")
        daily_permille_pattern = re.compile(r"日利率\s*千分之\s*([0-9]+(?:\.[0-9]+)?)")
        daily_permyriad_pattern = re.compile(r"日利率\s*万分之\s*([0-9]+(?:\.[0-9]+)?)")
        daily_percent_pattern = re.compile(r"日利率\s*([0-9]+(?:\.[0-9]+)?)\s*%")

        rate_text = clause or main_text
        lpr_match = lpr_pattern.search(rate_text)
        lpr_markup_match = lpr_markup_pattern.search(rate_text)
        fixed_match = fixed_pattern.search(rate_text)
        permille_match = daily_permille_pattern.search(rate_text)
        permyriad_match = daily_permyriad_pattern.search(rate_text)
        daily_percent_match = daily_percent_pattern.search(rate_text)

        if lpr_match:
            multiplier = self._parse_multiplier_value(lpr_match.group(1))
            if multiplier is not None:
                params.multiplier = multiplier
                params.rate_type = "1y"
                params.rate_description = (
                    f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{self._format_amount(multiplier)}倍"
                )
        elif lpr_markup_match:
            markup_percent = self._parse_decimal(lpr_markup_match.group(1))
            if markup_percent is not None:
                multiplier = Decimal("1") + (markup_percent / Decimal("100"))
                params.multiplier = multiplier
                params.rate_type = "1y"
                params.rate_description = (
                    f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{self._format_amount(multiplier)}倍"
                )
        elif fixed_match:
            annual_rate = self._parse_decimal(fixed_match.group(1))
            if annual_rate is not None:
                params.custom_rate_unit = "percent"
                params.custom_rate_value = annual_rate
                params.rate_description = f"年利率{self._format_amount(annual_rate)}%"
        elif permille_match:
            unit_rate = self._parse_decimal(permille_match.group(1))
            if unit_rate is not None:
                params.custom_rate_unit = "permille"
                params.custom_rate_value = unit_rate
                params.rate_description = f"日利率千分之{self._format_amount(unit_rate)}"
        elif permyriad_match:
            unit_rate = self._parse_decimal(permyriad_match.group(1))
            if unit_rate is not None:
                params.custom_rate_unit = "permyriad"
                params.custom_rate_value = unit_rate
                params.rate_description = f"日利率万分之{self._format_amount(unit_rate)}"
        elif daily_percent_match:
            # 日利率 x% => 转换为万分之(x * 100)
            percent_rate = self._parse_decimal(daily_percent_match.group(1))
            if percent_rate is not None:
                params.custom_rate_unit = "permyriad"
                params.custom_rate_value = (percent_rate * Decimal("100")).quantize(Decimal("0.0001"))
                params.rate_description = f"日利率{self._format_amount(percent_rate)}%"

        date_match = re.search(r"(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|开始|计)?", rate_text)
        if date_match:
            params.start_date = self._build_date(date_match.group(1), date_match.group(2), date_match.group(3))

        cap_patterns = [
            re.compile(rf"以\s*不超过\s*{AMOUNT_PATTERN}\s*元\s*为限"),
            re.compile(rf"利息总额[^。；\n]{{0,40}}?不超过\s*{AMOUNT_PATTERN}\s*元"),
        ]
        for cap_pattern in cap_patterns:
            cap_match = cap_pattern.search(main_text)
            if cap_match:
                cap_amount = self._parse_decimal(cap_match.group(1))
                if cap_amount is not None:
                    params.interest_cap = cap_amount
                    break

        params.base_mode, params.base_amount = self._parse_interest_base_rule(rate_text=rate_text, full_text=main_text)
        return params

    def _parse_interest_base_rule(self, *, rate_text: str, full_text: str) -> tuple[str, Decimal | None]:
        base_match = re.search(r"以\s*([^，,；。\n]{1,60}?)\s*为(?:本金|基数)", rate_text)
        if base_match:
            base_text = base_match.group(1)
            amount_match = re.search(AMOUNT_WITH_UNIT_PATTERN, base_text)
            if amount_match:
                amount_value = self._parse_amount_value(amount_match.group(1), amount_match.group(2))
                if amount_value is not None:
                    if any(k in base_text for k in ("剩余", "未付", "未偿还")):
                        return "fixed_amount_remaining", amount_value
                    return "fixed_amount", amount_value
            if any(k in base_text for k in ("借款", "货款", "本金")):
                return "remaining_principal", None
            if any(k in base_text for k in ("未付款项", "未支付", "上述款项", "剩余款项")):
                return "remaining_total", None

        compact_text = full_text.replace(" ", "")
        if any(k in compact_text for k in ("未偿还的借款为基数", "未偿还借款为基数", "剩余借款为基数", "未偿还货款为基数")):
            return "remaining_principal", None
        if any(k in compact_text for k in ("剩余未付款项为基数", "未支付的上述款项为基数", "未付款项为基数", "上述款项为基数")):
            return "remaining_total", None
        return "fallback_target", None

    def _resolve_interest_base(
        self,
        *,
        case: Case,
        amounts: ParsedAmounts,
        params: ParsedInterestParams,
        principal_paid: Decimal,
    ) -> Decimal:
        principal = amounts.principal or Decimal("0")
        target_amount = self._safe_decimal(case.target_amount)

        if params.base_mode == "fixed_amount" and params.base_amount is not None:
            # 本金已发生扣减时，固定基数也应同步按已还本金扣减
            base = max(params.base_amount - principal_paid, Decimal("0"))
        elif params.base_mode == "fixed_amount_remaining" and params.base_amount is not None:
            base = max(params.base_amount - principal_paid, Decimal("0"))
        elif params.base_mode == "remaining_principal":
            base = principal
        elif params.base_mode == "remaining_total":
            base = principal + amounts.confirmed_interest
        else:
            base = target_amount if target_amount > 0 else (principal + amounts.confirmed_interest)

        if base <= 0:
            if target_amount > 0:
                return target_amount
            return max(principal, Decimal("0"))
        return base

    def _parse_deduction_order(self, main_text: str) -> list[str]:
        patterns = [
            re.compile(r"按\s*([^。；\n]{2,120}?)\s*顺序(?:优先)?(?:进行)?抵扣"),
            re.compile(r"按\s*([^。；\n]{2,120}?)\s*抵扣顺序"),
            re.compile(r"按顺序(?:优先)?(?:进行)?抵扣\s*([^。；\n]{2,120})"),
        ]
        for pattern in patterns:
            match = pattern.search(main_text)
            if not match:
                continue
            segment = match.group(1)
            tokens = [t.strip() for t in re.split(r"[、，,]", segment) if t.strip()]
            mapped: list[str] = []
            for token in tokens:
                key = self._map_deduction_token(token)
                if key and key not in mapped:
                    mapped.append(key)
            if mapped:
                return mapped
        return []

    def _map_deduction_token(self, token: str) -> str | None:
        if "受理费" in token:
            return "litigation_fee"
        if "保全" in token and "担保" not in token:
            return "preservation_fee"
        if "公告费" in token:
            return "announcement_fee"
        if "律师" in token:
            return "attorney_fee"
        if "担保" in token:
            return "guarantee_fee"
        if "利息" in token or "逾期付款利息" in token or "逾期利息" in token:
            return "interest"
        if any(k in token for k in ("借款", "货款", "本金", "未付款", "剩余未付款")):
            return "principal"
        return None

    def _apply_paid_amount(
        self,
        *,
        amounts: ParsedAmounts,
        paid_amount: Decimal,
        deduction_order: list[str],
    ) -> tuple[ParsedAmounts, Decimal, list[dict[str, Any]]]:
        principal = amounts.principal or Decimal("0")
        components: dict[str, Decimal] = {
            "principal": principal,
            "confirmed_interest": amounts.confirmed_interest,
            "litigation_fee": amounts.litigation_fee,
            "preservation_fee": amounts.preservation_fee,
            "announcement_fee": amounts.announcement_fee,
            "attorney_fee": amounts.attorney_fee,
            "guarantee_fee": amounts.guarantee_fee,
        }
        remain_paid = max(paid_amount, Decimal("0"))
        applied: list[dict[str, Any]] = []

        if deduction_order:
            for key in deduction_order:
                component_name = self.DEDUCTION_KEY_TO_COMPONENT.get(key)
                if not component_name:
                    continue
                available = components.get(component_name, Decimal("0"))
                if available <= 0 or remain_paid <= 0:
                    continue
                current_deduct = min(available, remain_paid)
                components[component_name] = available - current_deduct
                remain_paid -= current_deduct
                applied.append({"key": key, "amount": current_deduct})

        if remain_paid > 0 and components["principal"] > 0:
            extra_deduct = min(components["principal"], remain_paid)
            components["principal"] -= extra_deduct
            remain_paid -= extra_deduct
            applied.append({"key": "principal", "amount": extra_deduct})

        principal_paid = principal - components["principal"]

        amounts.principal = components["principal"]
        amounts.confirmed_interest = components["confirmed_interest"]
        amounts.litigation_fee = components["litigation_fee"]
        amounts.preservation_fee = components["preservation_fee"]
        amounts.announcement_fee = components["announcement_fee"]
        amounts.attorney_fee = components["attorney_fee"]
        amounts.guarantee_fee = components["guarantee_fee"]
        return amounts, principal_paid, applied

    def _calculate_interest(
        self,
        *,
        principal: Decimal,
        params: ParsedInterestParams,
        cutoff_date: date,
        year_days: int,
        date_inclusion: str,
        warnings: list[str],
    ) -> Decimal:
        if principal <= 0:
            return Decimal("0")
        if params.start_date is None:
            return Decimal("0")
        if params.multiplier is None and params.custom_rate_value is None:
            return Decimal("0")
        if cutoff_date < params.start_date:
            warnings.append("截止日早于利息起算日，逾期利息按 0 计算。")
            return Decimal("0")

        try:
            if params.custom_rate_value is not None:
                result = self.calculator.calculate(
                    start_date=params.start_date,
                    end_date=cutoff_date,
                    principal=principal,
                    custom_rate_unit=params.custom_rate_unit,
                    custom_rate_value=params.custom_rate_value,
                    year_days=year_days,
                    date_inclusion=date_inclusion,
                )
            else:
                result = self.calculator.calculate(
                    start_date=params.start_date,
                    end_date=cutoff_date,
                    principal=principal,
                    rate_type=params.rate_type,
                    multiplier=params.multiplier or Decimal("1"),
                    year_days=year_days,
                    date_inclusion=date_inclusion,
                )
        except Exception as exc:
            logger.error("利息计算失败: %s", exc, exc_info=True)
            warnings.append("利息计算失败，已按 0 处理。")
            return Decimal("0")

        interest = result.total_interest
        if params.interest_cap is not None and interest > params.interest_cap:
            warnings.append(
                f"利息触发上限，已按 {self._format_amount(params.interest_cap)} 元截断。"
            )
            interest = params.interest_cap
        return interest

    def _generate_request_text(
        self,
        *,
        full_case_number: str,
        amounts: ParsedAmounts,
        params: ParsedInterestParams,
        overdue_interest: Decimal,
        interest_base: Decimal,
        cutoff_date: date,
        total: Decimal,
        has_double_interest_clause: bool,
    ) -> str:
        principal = amounts.principal or Decimal("0")
        item_segments = [
            f"申请强制执行{full_case_number}，被申请人向申请人支付{amounts.principal_label}{self._format_amount(principal)}元"
        ]
        if amounts.confirmed_interest > 0:
            item_segments.append(f"利息{self._format_amount(amounts.confirmed_interest)}元")

        if params.start_date and (params.multiplier is not None or params.custom_rate_value is not None):
            start_date_text = f"{params.start_date.year}年{params.start_date.month}月{params.start_date.day}日"
            cutoff_text = f"{cutoff_date.year}年{cutoff_date.month}月{cutoff_date.day}日"
            rate_desc = params.rate_description or "约定利率"
            item_segments.append(
                f"利息自{start_date_text}起以{self._format_amount(interest_base)}元为本金，按{rate_desc}计算至实际清偿之日，截至{cutoff_text}利息为{self._format_amount(overdue_interest)}元"
            )

        fee_desc = self._build_fee_desc(amounts)
        if fee_desc:
            item_segments.append(fee_desc)

        first_item = "，".join(item_segments) + "；"
        lines = [f"1.{first_item}", f"以上合计：{self._format_amount(total)}元"]

        index = 2
        if has_double_interest_clause:
            lines.append(f"{index}.被申请人加倍支付迟延履行期间的债务利息；")
            index += 1
        lines.append(f"{index}.由被申请人承担本案执行费用。")

        return "\n".join(lines)

    def _build_fee_desc(self, amounts: ParsedAmounts) -> str:
        parts: list[str] = []
        if amounts.litigation_fee > 0:
            parts.append(f"受理费{self._format_amount(amounts.litigation_fee)}元")
        if amounts.preservation_fee > 0:
            parts.append(f"财产保全费{self._format_amount(amounts.preservation_fee)}元")
        if amounts.announcement_fee > 0:
            parts.append(f"公告费{self._format_amount(amounts.announcement_fee)}元")
        if amounts.attorney_fee > 0:
            parts.append(f"律师代理费{self._format_amount(amounts.attorney_fee)}元")
        if amounts.guarantee_fee > 0:
            parts.append(f"财产保全担保费{self._format_amount(amounts.guarantee_fee)}元")
        return "、".join(parts)

    def _has_double_interest_clause(self, main_text: str) -> bool:
        return bool(re.search(r"加倍支付\s*迟\s*延履行期间(?:的)?债务利息", main_text))

    def _extract_interest_clause(self, main_text: str) -> str:
        patterns = [
            re.compile(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,120}"),
            re.compile(r"年利率[^。；\n]{0,120}"),
            re.compile(r"日利率[^。；\n]{0,120}"),
        ]
        for pattern in patterns:
            match = pattern.search(main_text)
            if match:
                return self._extract_sentence(main_text, match.start(), match.end())
        return main_text

    def _extract_sentence(self, text: str, start: int, end: int) -> str:
        delimiters = ("。", "；", "\n")
        left = 0
        right = len(text)

        for delim in delimiters:
            pos = text.rfind(delim, 0, start)
            if pos >= 0:
                left = max(left, pos + 1)

        right_candidates: list[int] = []
        for delim in delimiters:
            pos = text.find(delim, end)
            if pos >= 0:
                right_candidates.append(pos)
        if right_candidates:
            right = min(right_candidates)

        return text[left:right].strip()

    def _format_case_number(self, case_number: CaseNumber) -> str:
        number = (case_number.number or "").strip()
        document_name = (case_number.document_name or "").strip()
        if document_name and not document_name.startswith("《"):
            document_name = f"《{document_name}》"
        return f"{number}{document_name}"

    def _normalize_year_days(self, value: int | None) -> int:
        if value in VALID_YEAR_DAYS:
            return int(value)
        return 360

    def _normalize_date_inclusion(self, value: str | None) -> str:
        if value in VALID_DATE_INCLUSION:
            return str(value)
        return "both"

    def _normalize_text(self, text: str) -> str:
        normalized = text.translate(FULLWIDTH_TRANSLATION)
        normalized = re.sub(r"\u00a0", " ", normalized)
        normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
        normalized = re.sub(r"\n+", "\n", normalized)
        return normalized

    def _build_date(self, year: str, month: str, day: str) -> date | None:
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    def _parse_decimal(self, raw: str | None) -> Decimal | None:
        if raw is None:
            return None
        clean = raw.replace(",", "").strip()
        if not clean:
            return None
        try:
            return Decimal(clean)
        except (InvalidOperation, ValueError):
            return None

    def _parse_amount_value(self, raw_amount: str | None, unit_marker: str | None = None) -> Decimal | None:
        amount = self._parse_decimal(raw_amount)
        if amount is None:
            return None
        if unit_marker and "万" in unit_marker:
            return amount * Decimal("10000")
        return amount

    def _parse_multiplier_value(self, raw: str | None) -> Decimal | None:
        value = self._parse_decimal(raw)
        if value is not None:
            return value
        if raw is None:
            return None

        clean = raw.strip()
        digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if clean == "十":
            return Decimal("10")
        if clean in digits:
            return Decimal(str(digits[clean]))

        if "十" in clean:
            left, right = clean.split("十", 1)
            if left:
                if left not in digits:
                    return None
                tens = digits[left]
            else:
                tens = 1
            ones = 0
            if right:
                if right not in digits:
                    return None
                ones = digits[right]
            return Decimal(str(tens * 10 + ones))
        return None

    def _safe_decimal(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def _format_amount(self, amount: Decimal | None) -> str:
        if amount is None:
            return "0"
        quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if quantized == quantized.to_integral_value():
            return str(int(quantized))
        return format(quantized.normalize(), "f")
