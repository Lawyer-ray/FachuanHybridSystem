"""强制执行申请书 - 申请执行事项规则引擎服务."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from apps.cases.models import Case, CaseNumber
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.finance.services.calculator.interest_calculator import InterestCalculator
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

from . import execution_request_clause_extractor as clause_extractor
from . import execution_request_interest as interest_mod
from . import execution_request_llm_fallback as llm_mod
from . import execution_request_parser as parser_mod
from . import execution_request_text_generator as text_gen
from .execution_request_models import (
    ExecutionComputation,
    FeeItem,
    InterestSegment,
    OverdueInterestRule,
    ParsedAmounts,
    ParsedInterestParams,
)
from .execution_request_utils import (
    format_amount,
    normalize_date_inclusion,
    normalize_text,
    normalize_year_days,
    safe_decimal,
    to_docx_hard_breaks,
)

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class ExecutionRequestService(BasePlaceholderService):
    """申请执行事项规则引擎（纯规则，不依赖 LLM）."""

    name: str = "enforcement_execution_request_service"
    display_name: str = "诉讼文书-强制执行申请书申请执行事项"
    description: str = "生成强制执行申请书模板中的申请执行事项"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST]

    DEDUCTION_KEY_TO_COMPONENT: ClassVar[dict[str, str]] = interest_mod.DEDUCTION_KEY_TO_COMPONENT
    DEDUCTION_KEY_TO_LABEL: ClassVar[dict[str, str]] = interest_mod.DEDUCTION_KEY_TO_LABEL
    OLLAMA_FALLBACK_MODEL: ClassVar[str] = llm_mod.OLLAMA_FALLBACK_MODEL
    OLLAMA_MAX_TEXT_CHARS: ClassVar[int] = llm_mod.OLLAMA_MAX_TEXT_CHARS

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
            return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: to_docx_hard_breaks(manual_text)}

        result = self._build_execution_request(case=case, case_number=case_number)
        return {LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: to_docx_hard_breaks(result.preview_text)}

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

        normalized_text = normalize_text(main_text)
        amounts = parser_mod.parse_confirmed_amounts(normalized_text)
        params = interest_mod.parse_interest_params(normalized_text)
        principal_fallback_to_target = False
        if amounts.principal is None:
            inferred_principal = interest_mod.infer_principal_from_interest_base(params)
            if inferred_principal is not None:
                amounts.principal = inferred_principal
                if "货款" in normalized_text:
                    amounts.principal_label = "货款本金"
                elif "借款" not in normalized_text:
                    amounts.principal_label = "款项本金"
            else:
                target_amount = safe_decimal(case.target_amount)
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

        paid = paid_amount if paid_amount is not None else safe_decimal(case_number.execution_paid_amount)
        paid = max(paid, Decimal("0"))
        use_order = (
            bool(case_number.execution_use_deduction_order) if use_deduction_order is None else use_deduction_order
        )
        calc_year_days = normalize_year_days(
            year_days if year_days is not None else case_number.execution_year_days
        )
        calc_date_inclusion = normalize_date_inclusion(
            date_inclusion if date_inclusion is not None else case_number.execution_date_inclusion
        )
        calc_cutoff = cutoff_date or case_number.execution_cutoff_date or case.specified_date or date.today()

        deduction_order = interest_mod.parse_deduction_order(normalized_text)
        amounts, principal_paid, deduction_applied = interest_mod.apply_paid_amount(
            amounts=amounts,
            paid_amount=paid,
            deduction_order=deduction_order if use_order else [],
        )

        has_double_interest_clause = clause_extractor.has_double_interest_clause(normalized_text)
        interest_segments = clause_extractor.parse_interest_segments(normalized_text)
        has_segmented_interest = len(interest_segments) >= 2
        if has_segmented_interest and params.start_date is None:
            params.start_date = min(segment.start_date for segment in interest_segments)
        overdue_interest_rules = clause_extractor.parse_overdue_interest_rules(normalized_text)
        has_multiple_overdue_interest_rules = len(overdue_interest_rules) >= 2
        joint_liability_text = clause_extractor.extract_joint_liability_text(normalized_text)
        supplementary_liability_text = clause_extractor.extract_supplementary_liability_text(normalized_text)
        priority_execution_texts = clause_extractor.extract_priority_execution_texts(normalized_text)
        manual_review_clauses = clause_extractor.extract_manual_review_clauses(
            normalized_text,
            recognized_texts=[
                joint_liability_text,
                supplementary_liability_text,
                *priority_execution_texts,
            ],
        )
        llm_fallback_enabled = True if enable_llm_fallback is None else bool(enable_llm_fallback)
        llm_fallback_used = False
        if llm_fallback_enabled and llm_mod.should_try_llm_fallback(
            text=normalized_text,
            amounts=amounts,
            params=params,
            principal_fallback_to_target=principal_fallback_to_target,
        ):
            llm_data = llm_mod.extract_with_ollama_fallback(normalized_text)
            if llm_data:
                llm_fallback_used = llm_mod.merge_llm_fallback(
                    amounts=amounts,
                    params=params,
                    llm_data=llm_data,
                    principal_fallback_to_target=principal_fallback_to_target,
                )
                if llm_data.get("has_double_interest_clause") is True:
                    has_double_interest_clause = True
                if llm_fallback_used:
                    warnings.append("规则置信度不足，已使用本地Ollama兜底解析。")

        interest_base = interest_mod.resolve_interest_base(
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
                    rule_interest = interest_mod.calculate_interest_with_segments(
                        calculator=self.calculator,
                        segments=rule_segments,
                        params=rule_params,
                        cutoff_date=calc_cutoff,
                        year_days=calc_year_days,
                        date_inclusion=calc_date_inclusion,
                        warnings=warnings,
                    )
                else:
                    rule_base = interest_mod.resolve_interest_base(
                        case=case,
                        amounts=amounts,
                        params=rule_params,
                        principal_paid=principal_paid,
                    )
                    rule_interest = interest_mod.calculate_interest(
                        calculator=self.calculator,
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
                        "interest_base": format_amount(rule_base),
                        "interest_segmented": len(rule_segments) >= 2,
                        "interest_segments": [
                            {
                                "base_amount": format_amount(segment.base_amount),
                                "start_date": segment.start_date.isoformat(),
                                "end_date": segment.end_date.isoformat() if segment.end_date else "",
                            }
                            for segment in rule_segments
                        ],
                        "overdue_interest": format_amount(rule_interest),
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
            custom_interest_summary = f"{overdue_label}按判决确定的分项规则计算，截至{cutoff_text}{overdue_label}为{format_amount(overdue_interest)}元"
        elif has_segmented_interest:
            interest_base = interest_segments[0].base_amount
            original_segmented_interest_expression = clause_extractor.extract_original_segmented_interest_expression(
                main_text=main_text,
                overdue_label=params.overdue_item_label,
            )
            overdue_interest = interest_mod.calculate_interest_with_segments(
                calculator=self.calculator,
                segments=interest_segments,
                params=params,
                cutoff_date=calc_cutoff,
                year_days=calc_year_days,
                date_inclusion=calc_date_inclusion,
                warnings=warnings,
            )
        else:
            overdue_interest = interest_mod.calculate_interest(
                calculator=self.calculator,
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
            llm_data = llm_mod.extract_with_ollama_fallback(normalized_text)
            if llm_data:
                llm_fallback_used = llm_mod.merge_llm_fallback(
                    amounts=amounts,
                    params=params,
                    llm_data=llm_data,
                    principal_fallback_to_target=principal_fallback_to_target,
                )
                if llm_data.get("has_double_interest_clause") is True:
                    has_double_interest_clause = True
                interest_base = interest_mod.resolve_interest_base(
                    case=case, amounts=amounts, params=params, principal_paid=principal_paid
                )
                if has_segmented_interest:
                    interest_base = interest_segments[0].base_amount
                    overdue_interest = interest_mod.calculate_interest_with_segments(
                        calculator=self.calculator,
                        segments=interest_segments,
                        params=params,
                        cutoff_date=calc_cutoff,
                        year_days=calc_year_days,
                        date_inclusion=calc_date_inclusion,
                        warnings=warnings,
                    )
                else:
                    overdue_interest = interest_mod.calculate_interest(
                        calculator=self.calculator,
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
            warnings.append(f"{fee.label}{format_amount(fee.amount)}元已排除：{fee.reason}")

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

        preview_text = text_gen.generate_request_text(
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
            "principal": format_amount(amounts.principal),
            "confirmed_interest": format_amount(amounts.confirmed_interest),
            "litigation_fee": format_amount(amounts.litigation_fee),
            "preservation_fee": format_amount(amounts.preservation_fee),
            "announcement_fee": format_amount(amounts.announcement_fee),
            "attorney_fee": format_amount(amounts.attorney_fee),
            "guarantee_fee": format_amount(amounts.guarantee_fee),
            "paid_amount": format_amount(paid),
            "deduction_order": [self.DEDUCTION_KEY_TO_LABEL.get(k, k) for k in deduction_order],
            "deduction_applied": [
                {
                    "component": self.DEDUCTION_KEY_TO_LABEL.get(item["key"], item["key"]),
                    "amount": format_amount(item["amount"]),
                }
                for item in deduction_applied
            ],
            "interest_start_date": params.start_date.isoformat() if params.start_date else "",
            "interest_rate_description": params.rate_description,
            "overdue_interest_label": params.overdue_item_label,
            "interest_base": format_amount(interest_base),
            "interest_segmented": has_segmented_interest,
            "interest_segments": [
                {
                    "base_amount": format_amount(segment.base_amount),
                    "start_date": segment.start_date.isoformat(),
                    "end_date": segment.end_date.isoformat() if segment.end_date else "",
                }
                for segment in interest_segments
            ],
            "interest_cap": format_amount(params.interest_cap),
            "cutoff_date": calc_cutoff.isoformat(),
            "year_days": calc_year_days,
            "date_inclusion": calc_date_inclusion,
            "has_multiple_overdue_interest_rules": has_multiple_overdue_interest_rules,
            "overdue_interest_rules": overdue_interest_rule_details,
            "overdue_interest": format_amount(overdue_interest),
            "total": format_amount(total),
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
                    "amount": format_amount(fee.amount),
                    "reason": fee.reason,
                }
                for fee in amounts.excluded_fees
            ],
        }

        return ExecutionComputation(preview_text=preview_text, warnings=warnings, structured_params=structured)

    def _format_case_number(self, case_number: CaseNumber) -> str:
        number = (case_number.number or "").strip()
        document_name = (case_number.document_name or "").strip()
        if document_name and not document_name.startswith("《"):
            document_name = f"《{document_name}》"
        return f"{number}{document_name}"
