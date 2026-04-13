"""强制执行申请书 - 申请执行事项规则引擎服务."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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

FULLWIDTH_TRANSLATION = str.maketrans(
    {
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
    }
)


@dataclass
class FeeItem:
    key: str
    label: str
    amount: Decimal
    include: bool
    reason: str = ""
    sentence: str = ""


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
    overdue_item_label: str = "利息"
    base_mode: str = "fallback_target"
    base_amount: Decimal | None = None


@dataclass
class InterestSegment:
    base_amount: Decimal
    start_date: date
    end_date: date | None = None


@dataclass
class OverdueInterestRule:
    params: ParsedInterestParams
    segments: list[InterestSegment] = field(default_factory=list)
    source_text: str = ""


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
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: self._to_docx_hard_breaks(manual_text)}

        result = self._build_execution_request(case=case, case_number=case_number)
        return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: self._to_docx_hard_breaks(result.preview_text)}

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
        params = self._parse_interest_params(normalized_text)
        principal_fallback_to_target = False
        if amounts.principal is None:
            inferred_principal = self._infer_principal_from_interest_base(params)
            if inferred_principal is not None:
                amounts.principal = inferred_principal
                if "货款" in normalized_text:
                    amounts.principal_label = "货款本金"
                elif "借款" not in normalized_text:
                    amounts.principal_label = "款项本金"
            else:
                target_amount = self._safe_decimal(case.target_amount)
                if target_amount > 0:
                    amounts.principal = target_amount
                    if "货款" in normalized_text:
                        amounts.principal_label = "货款本金"
                    warnings.append("未从文书解析到本金，已回退使用案件“涉案金额”。")
                    principal_fallback_to_target = True
                else:
                    has_fee_only_items = any(
                        value > 0
                        for value in (
                            amounts.litigation_fee,
                            amounts.preservation_fee,
                            amounts.announcement_fee,
                            amounts.attorney_fee,
                            amounts.guarantee_fee,
                        )
                    )
                    if not has_fee_only_items and amounts.confirmed_interest <= 0:
                        warnings.append("未能确定本金，申请执行事项未生成。")
                        return ExecutionComputation(preview_text="", warnings=warnings, structured_params={})

        paid = paid_amount if paid_amount is not None else self._safe_decimal(case_number.execution_paid_amount)
        paid = max(paid, Decimal("0"))
        use_order = (
            bool(case_number.execution_use_deduction_order) if use_deduction_order is None else use_deduction_order
        )
        calc_year_days = self._normalize_year_days(
            year_days if year_days is not None else case_number.execution_year_days
        )
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

        has_double_interest_clause = self._has_double_interest_clause(normalized_text)
        interest_segments = self._parse_interest_segments(normalized_text)
        has_segmented_interest = len(interest_segments) >= 2
        if has_segmented_interest and params.start_date is None:
            params.start_date = min(segment.start_date for segment in interest_segments)
        overdue_interest_rules = self._parse_overdue_interest_rules(normalized_text)
        has_multiple_overdue_interest_rules = len(overdue_interest_rules) >= 2
        joint_liability_text = self._extract_joint_liability_text(normalized_text)
        supplementary_liability_text = self._extract_supplementary_liability_text(normalized_text)
        priority_execution_texts = self._extract_priority_execution_texts(normalized_text)
        manual_review_clauses = self._extract_manual_review_clauses(
            normalized_text,
            recognized_texts=[
                joint_liability_text,
                supplementary_liability_text,
                *priority_execution_texts,
            ],
        )
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

        interest_base = self._resolve_interest_base(
            case=case, amounts=amounts, params=params, principal_paid=principal_paid
        )
        custom_interest_summary = ""
        original_segmented_interest_expression = ""
        overdue_interest_rule_details: list[dict[str, Any]] = []
        if has_multiple_overdue_interest_rules:
            overdue_interest = Decimal("0")
            primary_base = interest_base
            primary_params = params
            primary_segments: list[InterestSegment] = []

            for index, rule in enumerate(overdue_interest_rules):
                rule_params = rule.params
                rule_segments = sorted(rule.segments, key=lambda s: (s.start_date, s.end_date or date.max))
                if rule_segments and rule_params.start_date is None:
                    rule_params.start_date = min(segment.start_date for segment in rule_segments)

                if rule_segments:
                    rule_base = rule_segments[0].base_amount
                    rule_interest = self._calculate_interest_with_segments(
                        segments=rule_segments,
                        params=rule_params,
                        cutoff_date=calc_cutoff,
                        year_days=calc_year_days,
                        date_inclusion=calc_date_inclusion,
                        warnings=warnings,
                    )
                else:
                    rule_base = self._resolve_interest_base(
                        case=case,
                        amounts=amounts,
                        params=rule_params,
                        principal_paid=principal_paid,
                    )
                    rule_interest = self._calculate_interest(
                        principal=rule_base,
                        params=rule_params,
                        cutoff_date=calc_cutoff,
                        year_days=calc_year_days,
                        date_inclusion=calc_date_inclusion,
                        warnings=warnings,
                    )

                overdue_interest += rule_interest
                overdue_interest_rule_details.append(
                    {
                        "index": index + 1,
                        "source_text": rule.source_text,
                        "interest_start_date": rule_params.start_date.isoformat() if rule_params.start_date else "",
                        "interest_rate_description": rule_params.rate_description,
                        "interest_base": self._format_amount(rule_base),
                        "interest_segmented": len(rule_segments) >= 2,
                        "interest_segments": [
                            {
                                "base_amount": self._format_amount(segment.base_amount),
                                "start_date": segment.start_date.isoformat(),
                                "end_date": segment.end_date.isoformat() if segment.end_date else "",
                            }
                            for segment in rule_segments
                        ],
                        "overdue_interest": self._format_amount(rule_interest),
                    }
                )
                if index == 0:
                    primary_base = rule_base
                    primary_params = rule_params
                    primary_segments = rule_segments

            params = primary_params
            interest_base = primary_base
            interest_segments = primary_segments
            has_segmented_interest = any(item["interest_segmented"] for item in overdue_interest_rule_details)
            cutoff_text = f"{calc_cutoff.year}年{calc_cutoff.month}月{calc_cutoff.day}日"
            overdue_label = params.overdue_item_label or "利息"
            if overdue_label == "利息":
                overdue_label = "逾期利息"
            custom_interest_summary = f"{overdue_label}按判决确定的分项规则计算，截至{cutoff_text}{overdue_label}为{self._format_amount(overdue_interest)}元"
        elif has_segmented_interest:
            interest_base = interest_segments[0].base_amount
            original_segmented_interest_expression = self._extract_original_segmented_interest_expression(
                main_text=main_text,
                overdue_label=params.overdue_item_label,
            )
            overdue_interest = self._calculate_interest_with_segments(
                segments=interest_segments,
                params=params,
                cutoff_date=calc_cutoff,
                year_days=calc_year_days,
                date_inclusion=calc_date_inclusion,
                warnings=warnings,
            )
        else:
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
            and not has_multiple_overdue_interest_rules
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
                if has_segmented_interest:
                    interest_base = interest_segments[0].base_amount
                    overdue_interest = self._calculate_interest_with_segments(
                        segments=interest_segments,
                        params=params,
                        cutoff_date=calc_cutoff,
                        year_days=calc_year_days,
                        date_inclusion=calc_date_inclusion,
                        warnings=warnings,
                    )
                else:
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
            warnings.append(f"{fee.label}{self._format_amount(fee.amount)}元已排除：{fee.reason}")

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
            interest_segments=interest_segments if has_segmented_interest else [],
            custom_interest_summary=custom_interest_summary,
            joint_liability_text=joint_liability_text,
            supplementary_liability_text=supplementary_liability_text,
            priority_execution_texts=priority_execution_texts,
            manual_review_clauses=manual_review_clauses,
            original_segmented_interest_expression=original_segmented_interest_expression,
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
            "overdue_interest_label": params.overdue_item_label,
            "interest_base": self._format_amount(interest_base),
            "interest_segmented": has_segmented_interest,
            "interest_segments": [
                {
                    "base_amount": self._format_amount(segment.base_amount),
                    "start_date": segment.start_date.isoformat(),
                    "end_date": segment.end_date.isoformat() if segment.end_date else "",
                }
                for segment in interest_segments
            ],
            "interest_cap": self._format_amount(params.interest_cap),
            "cutoff_date": calc_cutoff.isoformat(),
            "year_days": calc_year_days,
            "date_inclusion": calc_date_inclusion,
            "has_multiple_overdue_interest_rules": has_multiple_overdue_interest_rules,
            "overdue_interest_rules": overdue_interest_rule_details,
            "overdue_interest": self._format_amount(overdue_interest),
            "total": self._format_amount(total),
            "has_double_interest_clause": has_double_interest_clause,
            "has_joint_liability_clause": bool(joint_liability_text),
            "joint_liability_text": joint_liability_text,
            "has_supplementary_liability_clause": bool(supplementary_liability_text),
            "supplementary_liability_text": supplementary_liability_text,
            "has_priority_execution_clauses": bool(priority_execution_texts),
            "priority_execution_clauses": priority_execution_texts,
            "has_manual_review_clauses": bool(manual_review_clauses),
            "manual_review_clauses": manual_review_clauses,
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

        if amounts.litigation_fee <= 0 and self._has_fee_prepaid_context(text, fee_keywords=("受理费",)):
            return True
        if amounts.preservation_fee <= 0 and self._has_fee_prepaid_context(
            text,
            fee_keywords=("保全费", "财产保全费", "财产保全申请费"),
        ):
            return True

        if params.start_date and params.multiplier is None and params.custom_rate_value is None:
            return True
        return False

    def _has_fee_prepaid_context(self, text: str, *, fee_keywords: tuple[str, ...]) -> bool:
        prepaid_markers = ("预交", "已缴", "已交", "先行垫付")
        for sentence in re.split(r"[。；\n]", text):
            compact = sentence.replace(" ", "").strip()
            if not compact:
                continue
            if not any(keyword in compact for keyword in fee_keywords):
                continue
            if "负担" not in compact:
                continue
            if any(marker in compact for marker in prepaid_markers):
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
            if (
                principal_fallback_to_target
                or current_principal <= 0
                or (current_principal < Decimal("10000") and llm_principal >= Decimal("10000"))
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
            f"{main_text[: self.OLLAMA_MAX_TEXT_CHARS]}"
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
                rf"(?:偿还|支付|归还|清偿|尚欠(?:原告|申请人)?|尚欠)\s*((?:借款|货款)(?:本金)?)\s*{AMOUNT_WITH_UNIT_PATTERN}"
            ),
            re.compile(rf"((?:借款|货款)本金)\s*{AMOUNT_WITH_UNIT_PATTERN}"),
            re.compile(
                rf"(?:偿还|支付|给付|返还|清偿|尚欠(?:原告|申请人)?|尚欠)\s*"
                rf"(广告费|广告发布费|服务费|技术服务费|工程款|佣金|居间费|租金|货物款|材料款|采购款|合同款|设备款|推广费|管理费|设计费|咨询费|回购价款|回购基本价款)"
                rf"\s*{AMOUNT_WITH_UNIT_PATTERN}"
            ),
        ]
        principal_matches: list[tuple[int, int, Decimal, str]] = []
        for pattern in principal_patterns:
            for match in pattern.finditer(main_text):
                start, end = match.span()
                if any(not (end <= s or start >= e) for s, e, _, _ in principal_matches):
                    continue
                suffix = main_text[end : end + 12]
                # “以…为基数/为本金”属于计息基数，不应重复记入待执行本金
                if "为基数" in suffix or "为本金" in suffix:
                    continue
                kind = match.group(1)
                amount_value = self._parse_amount_value(match.group(2), match.group(3))
                if amount_value is None:
                    continue
                principal_matches.append((start, end, amount_value, kind))

        if principal_matches:
            amounts.principal = sum((item[2] for item in principal_matches), Decimal("0"))
            kinds = {item[3] for item in principal_matches}
            if len(kinds) == 1:
                amounts.principal_label = next(iter(kinds))
            else:
                amounts.principal_label = "款项本金"

        confirmed_interest = Decimal("0")
        confirmed_interest_pattern = re.compile(rf"(利息|罚息|复利)\s*(?:为|计为|计)?\s*{AMOUNT_WITH_UNIT_PATTERN}")
        for interest_match in confirmed_interest_pattern.finditer(main_text):
            label = interest_match.group(1)
            prefix = main_text[max(0, interest_match.start() - 6) : interest_match.start()]
            suffix = main_text[interest_match.end() : interest_match.end() + 10]
            if "为基数" in suffix:
                continue
            if "欠付" in prefix and label == "利息":
                continue
            if "逾期" in prefix and label == "利息":
                continue
            amount_value = self._parse_amount_value(interest_match.group(2), interest_match.group(3))
            if amount_value is not None:
                confirmed_interest += amount_value
        amounts.confirmed_interest = confirmed_interest

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
            (
                "litigation_fee",
                "受理费",
                re.compile(rf"受理费(?:减半收取)?(?:\s*(?:为|计))?\s*{AMOUNT_WITH_UNIT_PATTERN}"),
            ),
            (
                "preservation_fee",
                "财产保全费",
                re.compile(rf"(?:诉前)?(?:财产保全申请费|保全申请费|财产保全费|保全费)\s*{AMOUNT_WITH_UNIT_PATTERN}"),
            ),
            ("announcement_fee", "公告费", re.compile(rf"公告费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
            ("attorney_fee", "律师代理费", re.compile(rf"(?:律师代理费|律师费)\s*{AMOUNT_WITH_UNIT_PATTERN}")),
            ("guarantee_fee", "财产保全担保费", re.compile(rf"(?:财产保全)?担保费\s*{AMOUNT_WITH_UNIT_PATTERN}")),
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
                        sentence=sentence,
                    )
                )

        self._apply_split_burden_adjustment(fee_items)
        return fee_items

    def _apply_split_burden_adjustment(self, fee_items: list[FeeItem]) -> None:
        """
        处理“原告负担X + 被告负担Y并迳付原告”的费用分摊句式，避免把全部费用计入执行事项。
        仅在同一句内已纳入的费用存在多项且可校验出被告负担金额时触发。
        """
        sentence_groups: dict[str, list[int]] = {}
        for idx, item in enumerate(fee_items):
            if not item.include:
                continue
            sentence = (item.sentence or "").strip()
            if not sentence:
                continue
            sentence_groups.setdefault(sentence, []).append(idx)

        for sentence, indices in sentence_groups.items():
            if "迳付" not in sentence and "支付给原告" not in sentence and "支付给申请人" not in sentence:
                continue

            defendant_burden = self._extract_party_burden_amount(sentence, parties=("被告", "被申请人"))
            if defendant_burden is None or defendant_burden <= 0:
                continue

            key_totals: dict[str, Decimal] = {}
            for idx in indices:
                key = fee_items[idx].key
                key_totals[key] = key_totals.get(key, Decimal("0")) + fee_items[idx].amount
            original_total = sum(key_totals.values(), Decimal("0"))
            if original_total <= 0 or defendant_burden >= original_total:
                continue

            plaintiff_burden = self._extract_party_burden_amount(sentence, parties=("原告", "申请人"))
            if plaintiff_burden is None or plaintiff_burden <= 0:
                continue

            if len(indices) == 1:
                fee_items[indices[0]].amount = defendant_burden
                continue

            adjusted = dict(key_totals)
            remaining_plaintiff = plaintiff_burden
            for key in ("litigation_fee", "preservation_fee", "announcement_fee"):
                if remaining_plaintiff <= 0:
                    break
                available = adjusted.get(key, Decimal("0"))
                if available <= 0:
                    continue
                deduct = min(available, remaining_plaintiff)
                adjusted[key] = available - deduct
                remaining_plaintiff -= deduct

            adjusted_total = sum(adjusted.values(), Decimal("0"))
            if abs(adjusted_total - defendant_burden) > Decimal("0.05"):
                continue

            for key, new_total in adjusted.items():
                key_indices = [i for i in indices if fee_items[i].key == key]
                if not key_indices:
                    continue
                if len(key_indices) == 1:
                    fee_items[key_indices[0]].amount = max(new_total, Decimal("0"))
                    continue

                old_total = sum((fee_items[i].amount for i in key_indices), Decimal("0"))
                if old_total <= 0:
                    continue
                assigned = Decimal("0")
                for i in key_indices[:-1]:
                    scaled = (fee_items[i].amount * new_total / old_total).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    fee_items[i].amount = max(scaled, Decimal("0"))
                    assigned += fee_items[i].amount
                fee_items[key_indices[-1]].amount = max(new_total - assigned, Decimal("0"))

    def _extract_party_burden_amount(self, sentence: str, *, parties: tuple[str, ...]) -> Decimal | None:
        party_pattern = "|".join(re.escape(p) for p in parties if p)
        if not party_pattern:
            return None
        pattern = re.compile(rf"(?:由)?(?:{party_pattern})[^。；\n]{{0,50}}?(?:负担|承担)\s*{AMOUNT_WITH_UNIT_PATTERN}")
        match = pattern.search(sentence)
        if not match:
            return None
        return self._parse_amount_value(match.group(1), match.group(2))

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
            "迳付给原告",
            "迳付给申请人",
            "向原告支付",
            "向申请人支付",
        )
        court_markers = ("向本院缴纳", "向法院缴纳", "缴纳至本院", "本院退回", "法院退回", "交至本院")

        if any(marker in compact for marker in pay_to_applicant_markers):
            return True, ""
        if ("向原告" in compact or "向申请人" in compact) and any(k in compact for k in ("支付", "返还", "迳付")):
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
        params.overdue_item_label = self._detect_overdue_item_label(main_text)

        lpr_pattern = re.compile(
            r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)\s*倍"
        )
        lpr_markup_pattern = re.compile(
            r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；\n]{0,24}?上浮\s*([0-9]+(?:\.[0-9]+)?)\s*%"
        )
        fixed_pattern = re.compile(r"(?:(?:按|起按|按照)\s*)?(年利率|年化率|年化利率)\s*([0-9]+(?:\.[0-9]+)?)\s*%")
        unit_rate_pattern = r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)"
        daily_permille_pattern = re.compile(rf"(?:日利率|每日)\s*千分之\s*{unit_rate_pattern}")
        daily_permyriad_pattern = re.compile(rf"(?:日利率|每日)\s*万分之\s*{unit_rate_pattern}")
        daily_percent_pattern = re.compile(r"(?:日利率|每日)\s*([0-9]+(?:\.[0-9]+)?)\s*%")

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
        elif re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", rate_text):
            params.multiplier = Decimal("1")
            params.rate_type = "1y"
            params.rate_description = "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
        elif fixed_match:
            annual_rate = self._parse_decimal(fixed_match.group(2))
            if annual_rate is not None:
                params.custom_rate_unit = "percent"
                params.custom_rate_value = annual_rate
                params.rate_description = f"{fixed_match.group(1)}{self._format_amount(annual_rate)}%"
        elif permille_match:
            unit_rate = self._parse_multiplier_value(permille_match.group(1))
            if unit_rate is not None:
                params.custom_rate_unit = "permille"
                params.custom_rate_value = unit_rate
                params.rate_description = f"日利率千分之{self._format_amount(unit_rate)}"
        elif permyriad_match:
            unit_rate = self._parse_multiplier_value(permyriad_match.group(1))
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
                percent_text = format(percent_rate.normalize(), "f")
                params.rate_description = f"日利率{percent_text}%"

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

    def _detect_overdue_item_label(self, main_text: str) -> str:
        compact = (main_text or "").replace(" ", "")
        if "逾期付款违约金" in compact:
            return "逾期付款违约金"
        if "违约金" in compact and any(
            marker in compact
            for marker in (
                "计算方法",
                "计算至",
                "计至",
                "清偿之日",
                "付清之日",
                "履行之日",
                "万分之",
                "千分之",
                "年利率",
                "日利率",
                "LPR",
                "利率",
            )
        ):
            return "违约金"
        if "逾期付款损失" in compact:
            return "逾期付款损失"
        if "逾期付款利息" in compact:
            return "逾期付款利息"
        if "逾期利息" in compact:
            return "逾期利息"
        return "利息"

    def _infer_principal_from_interest_base(self, params: ParsedInterestParams) -> Decimal | None:
        if params.base_mode in {"fixed_amount", "fixed_amount_remaining"} and params.base_amount is not None:
            if params.base_amount > 0:
                return params.base_amount
        return None

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
        if any(
            k in compact_text for k in ("未偿还的借款为基数", "未偿还借款为基数", "剩余借款为基数", "未偿还货款为基数")
        ):
            return "remaining_principal", None
        if any(
            k in compact_text
            for k in ("剩余未付款项为基数", "未支付的上述款项为基数", "未付款项为基数", "上述款项为基数")
        ):
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
            warnings.append(f"利息触发上限，已按 {self._format_amount(params.interest_cap)} 元截断。")
            interest = params.interest_cap
        return interest

    def _calculate_interest_with_segments(
        self,
        *,
        segments: list[InterestSegment],
        params: ParsedInterestParams,
        cutoff_date: date,
        year_days: int,
        date_inclusion: str,
        warnings: list[str],
    ) -> Decimal:
        if not segments:
            return Decimal("0")
        if params.multiplier is None and params.custom_rate_value is None:
            return Decimal("0")

        from apps.finance.services.lpr.rate_service import PrincipalPeriod

        principal_periods: list[PrincipalPeriod] = []
        for segment in sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max)):
            seg_end = segment.end_date or cutoff_date
            if seg_end > cutoff_date:
                seg_end = cutoff_date
            if seg_end < segment.start_date:
                continue
            principal_periods.append(
                PrincipalPeriod(
                    start_date=segment.start_date,
                    end_date=seg_end,
                    principal=segment.base_amount,
                )
            )

        if not principal_periods:
            return Decimal("0")

        try:
            result = self.calculator.calculate_with_principal_changes(
                principal_periods=principal_periods,
                rate_type=params.rate_type,
                year_days=year_days,
                multiplier=params.multiplier or Decimal("1"),
                date_inclusion=date_inclusion,
                custom_rate_unit=params.custom_rate_unit,
                custom_rate_value=params.custom_rate_value,
            )
        except Exception as exc:
            logger.error("分段利息计算失败: %s", exc, exc_info=True)
            warnings.append("分段利息计算失败，已按 0 处理。")
            return Decimal("0")

        interest = result.total_interest
        if params.interest_cap is not None and interest > params.interest_cap:
            warnings.append(f"利息触发上限，已按 {self._format_amount(params.interest_cap)} 元截断。")
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
        interest_segments: list[InterestSegment] | None = None,
        custom_interest_summary: str = "",
        joint_liability_text: str = "",
        supplementary_liability_text: str = "",
        priority_execution_texts: list[str] | None = None,
        manual_review_clauses: list[str] | None = None,
        original_segmented_interest_expression: str = "",
    ) -> str:
        segments = interest_segments or []
        priority_texts = priority_execution_texts or []
        review_clauses = manual_review_clauses or []
        principal = amounts.principal or Decimal("0")
        overdue_label = params.overdue_item_label or "利息"
        fee_desc = self._build_fee_desc(amounts)
        fee_as_primary_item = False

        if principal > 0:
            item_segments = [
                f"申请强制执行{full_case_number}，被申请人向申请人支付{amounts.principal_label}{self._format_amount(principal)}元"
            ]
        elif fee_desc:
            item_segments = [f"申请强制执行{full_case_number}，被申请人向申请人支付{fee_desc}"]
            fee_as_primary_item = True
        else:
            item_segments = [f"申请强制执行{full_case_number}，被申请人向申请人支付款项"]

        if amounts.confirmed_interest > 0:
            item_segments.append(f"利息{self._format_amount(amounts.confirmed_interest)}元")

        if custom_interest_summary:
            item_segments.append(custom_interest_summary)
        elif (segments or params.start_date) and (
            params.multiplier is not None or params.custom_rate_value is not None
        ):
            cutoff_text = f"{cutoff_date.year}年{cutoff_date.month}月{cutoff_date.day}日"
            rate_desc = params.rate_description or "约定利率"
            if len(segments) >= 2:
                original_segmented_text = (original_segmented_interest_expression or "").strip().rstrip("。；")
                if original_segmented_text:
                    item_segments.append(
                        f"{original_segmented_text}，暂计至{cutoff_text}{overdue_label}为{self._format_amount(overdue_interest)}元"
                    )
                else:
                    segment_desc = self._build_interest_segment_desc(segments)
                    item_segments.append(
                        f"{overdue_label}按分段基数计算（{segment_desc}），按{rate_desc}计至实际清偿之日，截至{cutoff_text}{overdue_label}为{self._format_amount(overdue_interest)}元"
                    )
            else:
                start_date_text = f"{params.start_date.year}年{params.start_date.month}月{params.start_date.day}日"
                item_segments.append(
                    f"{overdue_label}自{start_date_text}起以{self._format_amount(interest_base)}元为基数，按{rate_desc}计算至实际清偿之日，截至{cutoff_text}{overdue_label}为{self._format_amount(overdue_interest)}元"
                )

        if fee_desc and not fee_as_primary_item:
            item_segments.append(fee_desc)

        first_item = "，".join(item_segments) + "。"
        lines = [first_item, f"以上合计：{self._format_amount(total)}元。"]

        if has_double_interest_clause:
            lines.append("被申请人加倍支付迟延履行期间的债务利息。")
        if joint_liability_text:
            line = joint_liability_text.rstrip("。；")
            if line:
                lines.append(f"{line}。")
        if supplementary_liability_text:
            line = supplementary_liability_text.rstrip("。；")
            if line:
                lines.append(f"{line}。")
        for text in priority_texts:
            line = str(text or "").strip().rstrip("。；")
            if line:
                lines.append(f"{line}。")
        for text in review_clauses:
            line = str(text or "").strip().rstrip("。；")
            if line:
                lines.append(f"【人工核对】{line}。")
        lines.append("由被申请人承担本案执行费用。")

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

    def _build_interest_segment_desc(self, segments: list[InterestSegment]) -> str:
        desc_parts: list[str] = []
        ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
        for segment in ordered_segments:
            start_text = f"{segment.start_date.year}年{segment.start_date.month}月{segment.start_date.day}日"
            if segment.end_date:
                end_text = f"{segment.end_date.year}年{segment.end_date.month}月{segment.end_date.day}日止"
            else:
                end_text = "实际清偿之日止"
            desc_parts.append(f"以{self._format_amount(segment.base_amount)}元为基数，自{start_text}起至{end_text}")
        return "；".join(desc_parts)

    def _has_double_interest_clause(self, main_text: str) -> bool:
        return bool(re.search(r"加倍支付\s*迟\s*延履行期间(?:的)?债务利息", main_text))

    def _extract_supplementary_liability_text(self, main_text: str) -> str:
        for sentence in re.split(r"[。；\n]", main_text):
            text = sentence.strip()
            if not text:
                continue
            text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
            if not text:
                continue
            if "责任" in text:
                if (
                    "补充" in text
                    and any(keyword in text for keyword in ("补充赔偿责任", "补充清偿责任", "承担补充责任", "补充责任"))
                    and any(keyword in text for keyword in ("不能清偿", "未出资", "未出资本息", "清偿部分", "上述债务"))
                ):
                    return text
                if (
                    any(
                        keyword in text
                        for keyword in ("财产不足清偿部分", "财产不足以清偿部分", "不能清偿部分", "不足清偿部分")
                    )
                    and "承担" in text
                    and "清偿责任" in text
                ):
                    return text
        return ""

    def _extract_joint_liability_text(self, main_text: str) -> str:
        for sentence in re.split(r"[。；\n]", main_text):
            text = sentence.strip()
            if not text:
                continue
            text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
            if not text:
                continue
            if "连带" not in text or "责任" not in text:
                continue
            if "承担" not in text:
                continue
            if any(k in text for k in ("债务", "清偿", "本判决第一项", "判决第一项")):
                return text
        return ""

    def _extract_priority_execution_texts(self, main_text: str) -> list[str]:
        results: list[str] = []
        for sentence in re.split(r"[。；\n]", main_text):
            text = sentence.strip()
            if not text:
                continue
            text = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", text)
            if not text:
                continue
            if "优先受偿权" not in text:
                continue
            if not any(keyword in text for keyword in ("折价", "拍卖", "变卖", "土地", "股权", "不动产", "抵押顺位")):
                continue
            if text not in results:
                results.append(text)
        return results

    def _extract_manual_review_clauses(self, main_text: str, *, recognized_texts: list[str]) -> list[str]:
        clauses = self._extract_numbered_clauses(main_text)
        if not clauses:
            return []

        recognized_compact = {
            re.sub(r"\s+", "", str(text or "")) for text in recognized_texts if str(text or "").strip()
        }
        disposal_keywords = ("折价", "拍卖", "变卖")
        asset_keywords = ("土地", "不动产", "股权", "应收账款", "机器设备", "房产", "车辆")

        results: list[str] = []
        for clause in clauses:
            text = clause.strip()
            if not text:
                continue
            compact = re.sub(r"\s+", "", text)
            is_priority_like = "优先受偿权" in text or (
                any(keyword in text for keyword in disposal_keywords)
                and any(keyword in text for keyword in asset_keywords)
            )
            if not is_priority_like:
                continue
            if any(keyword in text for keyword in ("受理费", "保全费", "公告费", "律师费", "担保费", "抵扣")):
                continue
            if any(rc and rc in compact for rc in recognized_compact):
                continue
            if text not in results:
                results.append(text.rstrip("。；"))
        return results

    def _extract_numbered_clauses(self, main_text: str) -> list[str]:
        marker_pattern = re.compile(r"(?:^|(?<=[。；\n]))\s*([一二三四五六七八九十\d]+[、.])")
        markers = list(marker_pattern.finditer(main_text))
        if not markers:
            return []

        clauses: list[str] = []
        for index, marker in enumerate(markers):
            start = marker.start(1)
            end = markers[index + 1].start(1) if index + 1 < len(markers) else len(main_text)
            clause = main_text[start:end].strip()
            if clause:
                clauses.append(clause)
        return clauses

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

    def _extract_original_segmented_interest_expression(self, *, main_text: str, overdue_label: str) -> str:
        label = (overdue_label or "").strip()
        if not label:
            return ""

        pattern = re.compile(rf"({re.escape(label)}\s*[（(][^（）()]{{10,4000}}[）)])")
        for match in pattern.finditer(main_text):
            text = match.group(1).strip()
            base_count = text.count("为基数") + text.count("为本金")
            if base_count < 2:
                continue
            if not any(keyword in text for keyword in ("计算至", "计至", "付清之日", "清偿之日", "履行之日")):
                continue
            return text
        return ""

    def _parse_overdue_interest_rules(self, main_text: str) -> list[OverdueInterestRule]:
        rules: list[OverdueInterestRule] = []
        candidates: list[str] = []
        seen: set[str] = set()

        parenthesized_pattern = re.compile(r"逾期利息[^。；\n]{0,30}?[（(]([^（）()]{6,1000})[）)]")
        for match in parenthesized_pattern.finditer(main_text):
            clause = match.group(1).strip()
            if not clause:
                continue
            key = clause.replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            candidates.append(clause)

        # 兼容“并支付利息、罚息、复利（...）”等未直接出现“逾期利息（”前缀的复杂写法
        if not candidates:
            generic_parenthesized_pattern = re.compile(r"[（(]([^（）()]{6,1000})[）)]")
            for match in generic_parenthesized_pattern.finditer(main_text):
                clause = match.group(1).strip()
                if not clause:
                    continue
                has_interest_keywords = any(keyword in clause for keyword in ("逾期利息", "罚息", "复利"))
                has_base_and_rate = "为基数" in clause and (
                    "年利率" in clause or bool(re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", clause))
                )
                if not (has_interest_keywords or has_base_and_rate):
                    continue
                if not any(keyword in clause for keyword in ("计算至", "清偿之日", "偿还之日", "付清之日", "履行之日")):
                    continue
                key = clause.replace(" ", "")
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(clause)

        if not candidates:
            for sentence in re.split(r"[。；\n]", main_text):
                text = sentence.strip()
                if not text or "逾期利息" not in text:
                    continue
                key = text.replace(" ", "")
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(text)

        for clause in candidates:
            dual_phase_rules = self._parse_dual_phase_overdue_interest_rules(clause)
            if dual_phase_rules:
                rules.extend(dual_phase_rules)
                continue
            params = self._parse_interest_params(clause)
            segments = self._parse_interest_segments(clause)
            if segments and params.start_date is None:
                params.start_date = min(segment.start_date for segment in segments)
            if params.multiplier is None and params.custom_rate_value is None:
                continue
            if params.start_date is None and not segments:
                continue
            rules.append(OverdueInterestRule(params=params, segments=segments, source_text=clause))

        return rules

    def _parse_dual_phase_overdue_interest_rules(self, clause: str) -> list[OverdueInterestRule]:
        compact = clause.replace(" ", "")
        if not any(token in compact for token in ("年利率", "年化率", "年化利率")):
            return []
        if not re.search(r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)", clause):
            return []
        if "为基数" not in clause:
            return []

        chunks = [chunk.strip() for chunk in re.split(r"[；;]", clause) if "为基数" in chunk]
        if not chunks:
            return []

        fixed_pattern_a = re.compile(
            r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?"
            r"[^。；;\n]{0,80}?(?:按|按照)\s*(?P<rate_label>年利率|年化率|年化利率)\s*(?P<rate>[0-9]+(?:\.[0-9]+)?)\s*%\s*计算至\s*"
            r"(?P<ey>\d{4})\s*年\s*(?P<em>\d{1,2})\s*月\s*(?P<ed>\d{1,2})\s*日"
        )
        fixed_pattern_b = re.compile(
            r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?\s*至\s*"
            r"(?P<ey>\d{4})\s*年\s*(?P<em>\d{1,2})\s*月\s*(?P<ed>\d{1,2})\s*日"
            r"[^。；;\n]{0,40}?(?:按|按照)\s*(?P<rate_label>年利率|年化率|年化利率)\s*(?P<rate>[0-9]+(?:\.[0-9]+)?)\s*%\s*计算"
        )
        lpr_core_pattern = re.compile(
            r"(?:LPR|贷款市场报价利率|一年期贷款市场报价利率)[^。；;\n]{0,40}?"
            r"(?P<mult>[0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)\s*倍"
        )
        date_from_pattern = re.compile(
            r"(?:从|自)\s*(?P<sy>\d{4})\s*年\s*(?P<sm>\d{1,2})\s*月\s*(?P<sd>\d{1,2})\s*日(?:起)?"
        )
        base_pattern = re.compile(rf"以[^，,；;。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为基数")

        fixed_groups: dict[tuple[str, Decimal], list[InterestSegment]] = {}
        lpr_groups: dict[Decimal, list[InterestSegment]] = {}

        for chunk in chunks:
            base_match = base_pattern.search(chunk)
            if not base_match:
                continue
            base_amount = self._parse_amount_value(base_match.group(1), base_match.group(2))
            if base_amount is None:
                continue

            fixed_match = fixed_pattern_a.search(chunk) or fixed_pattern_b.search(chunk)
            if fixed_match:
                start_date = self._build_date(fixed_match.group("sy"), fixed_match.group("sm"), fixed_match.group("sd"))
                end_date = self._build_date(fixed_match.group("ey"), fixed_match.group("em"), fixed_match.group("ed"))
                fixed_rate = self._parse_decimal(fixed_match.group("rate"))
                fixed_rate_label = str(fixed_match.group("rate_label") or "年利率")
                if start_date and end_date and fixed_rate is not None and end_date >= start_date:
                    fixed_groups.setdefault((fixed_rate_label, fixed_rate), []).append(
                        InterestSegment(base_amount=base_amount, start_date=start_date, end_date=end_date)
                    )

            lpr_match = lpr_core_pattern.search(chunk)
            if lpr_match:
                multiplier = self._parse_multiplier_value(lpr_match.group("mult"))
                prefix = chunk[: lpr_match.start()]
                date_matches = list(date_from_pattern.finditer(prefix))
                start_date = None
                if date_matches:
                    nearest = date_matches[-1]
                    start_date = self._build_date(nearest.group("sy"), nearest.group("sm"), nearest.group("sd"))
                if start_date and multiplier is not None:
                    lpr_groups.setdefault(multiplier, []).append(
                        InterestSegment(base_amount=base_amount, start_date=start_date, end_date=None)
                    )

        if not fixed_groups or not lpr_groups:
            return []

        rules: list[OverdueInterestRule] = []
        for (fixed_rate_label, fixed_rate), segments in sorted(fixed_groups.items(), key=lambda item: item[0][1]):
            ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
            params = ParsedInterestParams(
                start_date=ordered_segments[0].start_date,
                custom_rate_unit="percent",
                custom_rate_value=fixed_rate,
                rate_description=f"{fixed_rate_label}{self._format_amount(fixed_rate)}%",
            )
            rules.append(OverdueInterestRule(params=params, segments=ordered_segments, source_text=clause))

        for multiplier, segments in sorted(lpr_groups.items(), key=lambda item: item[0]):
            ordered_segments = sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))
            if multiplier == Decimal("1"):
                desc = "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
            else:
                desc = f"全国银行间同业拆借中心公布的一年期贷款市场报价利率的{self._format_amount(multiplier)}倍"
            params = ParsedInterestParams(
                start_date=ordered_segments[0].start_date,
                rate_type="1y",
                multiplier=multiplier,
                rate_description=desc,
            )
            rules.append(OverdueInterestRule(params=params, segments=ordered_segments, source_text=clause))

        return rules

    def _parse_interest_segments(self, main_text: str) -> list[InterestSegment]:
        segment_pattern = re.compile(
            rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)\s*"
            r"(?:，|,)?\s*(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
            r"[^，,；。\n]{0,120}?计算至\s*"
            r"(?:(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:止)?|实际(?:清偿|付清|履行|还清)(?:之日)?(?:止)?)"
        )
        segment_start_only_pattern = re.compile(
            rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)\s*"
            r"(?:，|,)?\s*(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
        )

        segments: list[InterestSegment] = []

        for match in segment_pattern.finditer(main_text):
            base_amount = self._parse_amount_value(match.group(1), match.group(2))
            start_date = self._build_date(match.group(3), match.group(4), match.group(5))
            end_date: date | None = None
            if match.group(6) and match.group(7) and match.group(8):
                end_date = self._build_date(match.group(6), match.group(7), match.group(8))
            if base_amount is None or start_date is None:
                continue
            if match.group(6) and end_date is None:
                continue
            candidate = InterestSegment(base_amount=base_amount, start_date=start_date, end_date=end_date)
            if any(
                seg.base_amount == candidate.base_amount
                and seg.start_date == candidate.start_date
                and seg.end_date == candidate.end_date
                for seg in segments
            ):
                continue
            segments.append(candidate)

        # 兼容“分段起算 + 统一尾句计算至…”的写法，例如：
        # 以A元为基数，自X日起算；以B元为基数，自Y日起算，均按LPR计算至实际清偿之日止
        if len(segments) < 2:
            shared_end_date = self._extract_shared_segment_end_date(main_text)
            for match in segment_start_only_pattern.finditer(main_text):
                base_amount = self._parse_amount_value(match.group(1), match.group(2))
                start_date = self._build_date(match.group(3), match.group(4), match.group(5))
                if base_amount is None or start_date is None:
                    continue
                candidate = InterestSegment(base_amount=base_amount, start_date=start_date, end_date=shared_end_date)
                if any(
                    seg.base_amount == candidate.base_amount
                    and seg.start_date == candidate.start_date
                    and seg.end_date == candidate.end_date
                    for seg in segments
                ):
                    continue
                segments.append(candidate)

        # 兼容“日期在前 + 多基数在后”的写法，例如：
        # 自2025年6月13日起的罚息以A元为基数、复利以B元为基数，均按...计算至清偿之日止
        if len(segments) < 2:
            date_first_pattern = re.compile(
                r"(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:起|起算|开始|计)?"
            )
            base_pattern = re.compile(rf"以[^，,；。\n]{{0,30}}?{AMOUNT_WITH_UNIT_PATTERN}\s*为(?:基数|本金)")
            for sentence in re.split(r"[。；\n]", main_text):
                sentence = sentence.strip()
                if not sentence:
                    continue
                date_match = date_first_pattern.search(sentence)
                if not date_match:
                    continue
                if "为基数" not in sentence and "为本金" not in sentence:
                    continue
                start_date = self._build_date(date_match.group(1), date_match.group(2), date_match.group(3))
                if start_date is None:
                    continue
                sentence_end_date = self._extract_shared_segment_end_date(sentence)
                for match in base_pattern.finditer(sentence):
                    base_amount = self._parse_amount_value(match.group(1), match.group(2))
                    if base_amount is None:
                        continue
                    candidate = InterestSegment(
                        base_amount=base_amount, start_date=start_date, end_date=sentence_end_date
                    )
                    if any(
                        seg.base_amount == candidate.base_amount
                        and seg.start_date == candidate.start_date
                        and seg.end_date == candidate.end_date
                        for seg in segments
                    ):
                        continue
                    segments.append(candidate)

        return sorted(segments, key=lambda s: (s.start_date, s.end_date or date.max))

    def _extract_shared_segment_end_date(self, main_text: str) -> date | None:
        shared_date_match = re.search(
            r"(?:均|并|分别)?[^。；\n]{0,80}?计算至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:止)?",
            main_text,
        )
        if shared_date_match:
            return self._build_date(shared_date_match.group(1), shared_date_match.group(2), shared_date_match.group(3))

        shared_actual_match = re.search(
            r"(?:均|并|分别)?[^。；\n]{0,80}?计算至\s*实际(?:清偿|付清|履行|还清)(?:之日)?(?:止)?",
            main_text,
        )
        if shared_actual_match:
            return None

        return None

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

    def _to_docx_hard_breaks(self, text: str) -> str:
        if not text:
            return ""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.replace("\n", "\a")

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
