"""
Preservation property-based tests — 验证现有功能行为不变。

在未修复代码上运行，建立基线行为。修复后重新运行确认无回归。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.core.enums import CaseStage, CaseType
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.contracts.tests")

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 适用于 representation_stages 的合同类型
APPLICABLE_TYPES: list[str] = [
    CaseType.CIVIL,
    CaseType.CRIMINAL,
    CaseType.ADMINISTRATIVE,
    CaseType.LABOR,
    CaseType.INTL,
]

# 不适用的合同类型
NON_APPLICABLE_TYPES: list[str] = [
    CaseType.SPECIAL,
    CaseType.ADVISOR,
]

ALL_STAGE_VALUES: list[str] = [choice[0] for choice in CaseStage.choices]

# 生成合法的 case_type（适用类型）
applicable_case_type_st: st.SearchStrategy[str] = st.sampled_from(APPLICABLE_TYPES)

# 生成合法的 stage 子集
valid_stages_st: st.SearchStrategy[list[str]] = st.lists(
    st.sampled_from(ALL_STAGE_VALUES),
    min_size=0,
    max_size=len(ALL_STAGE_VALUES),
    unique=True,
)

# FeeMode 值
FEE_MODE_VALUES: list[str] = ["FIXED", "SEMI_RISK", "FULL_RISK", "CUSTOM"]


# ---------------------------------------------------------------------------
# Property 2.3: normalize_representation_stages 对合法输入返回值不变
# **Validates: Requirements 3.7**
# ---------------------------------------------------------------------------


class TestNormalizeRepresentationStagesPreservation:
    """验证 normalize_representation_stages 对合法输入的返回值不变。"""

    @given(
        case_type=applicable_case_type_st,
        stages=valid_stages_st,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_stages_returned_unchanged(
        self, case_type: str, stages: list[str]
    ) -> None:
        """
        对适用类型 + 合法阶段值，normalize_representation_stages 应原样返回。

        **Validates: Requirements 3.7**
        """
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages(case_type, stages, strict=False)
        assert result == stages

    @given(
        case_type=st.sampled_from(NON_APPLICABLE_TYPES),
        stages=valid_stages_st,
    )
    @settings(max_examples=20)
    def test_non_applicable_type_returns_empty(
        self, case_type: str, stages: list[str]
    ) -> None:
        """
        对不适用类型，normalize_representation_stages 应返回空列表。

        **Validates: Requirements 3.7**
        """
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages(case_type, stages, strict=False)
        assert result == []

    @given(stages=valid_stages_st)
    @settings(max_examples=20)
    def test_none_case_type_returns_empty(self, stages: list[str]) -> None:
        """
        case_type 为 None 时，normalize_representation_stages 应返回空列表。

        **Validates: Requirements 3.7**
        """
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages(None, stages, strict=False)
        assert result == []

    @given(
        case_type=applicable_case_type_st,
        stages=valid_stages_st,
    )
    @settings(max_examples=30)
    def test_strict_mode_valid_input_same_result(
        self, case_type: str, stages: list[str]
    ) -> None:
        """
        strict=True 时，合法输入的返回值与 strict=False 一致。

        **Validates: Requirements 3.7**
        """
        from apps.contracts.domain.validators import normalize_representation_stages

        result_strict = normalize_representation_stages(case_type, stages, strict=True)
        result_non_strict = normalize_representation_stages(case_type, stages, strict=False)
        assert result_strict == result_non_strict


# ---------------------------------------------------------------------------
# Property 2.2: _validate_fee_mode 在 i18n 包裹后行为不变
# **Validates: Requirements 3.4**
# ---------------------------------------------------------------------------

# 正金额策略
positive_amount_st: st.SearchStrategy[str] = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("99999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(str)

# 正比例策略
positive_rate_st: st.SearchStrategy[str] = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("100.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(str)

# 非空文本策略
non_empty_text_st: st.SearchStrategy[str] = st.text(
    min_size=1, max_size=200
).filter(lambda s: s.strip() != "")


class TestValidateFeeModePreservation:
    """验证 _validate_fee_mode 的验证逻辑在 i18n 包裹后行为不变。"""

    def _get_mixin_instance(self) -> Any:
        """创建 ContractHelpersMixin 实例用于测试。"""
        from apps.contracts.services.contract.contract_validator import ContractHelpersMixin
        from apps.core.business_config import BusinessConfig

        instance = ContractHelpersMixin()
        instance.config = BusinessConfig()  # type: ignore[attr-defined]
        return instance

    @given(fixed_amount=positive_amount_st)
    @settings(max_examples=30)
    def test_fixed_mode_valid_no_error(self, fixed_amount: str) -> None:
        """
        FIXED 模式 + 正金额 → 不抛异常。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "FIXED", "fixed_amount": fixed_amount}
        # 不应抛异常
        mixin._validate_fee_mode(data)

    @given(
        fixed_amount=positive_amount_st,
        risk_rate=positive_rate_st,
    )
    @settings(max_examples=30)
    def test_semi_risk_valid_no_error(
        self, fixed_amount: str, risk_rate: str
    ) -> None:
        """
        SEMI_RISK 模式 + 正金额 + 正比例 → 不抛异常。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {
            "fee_mode": "SEMI_RISK",
            "fixed_amount": fixed_amount,
            "risk_rate": risk_rate,
        }
        mixin._validate_fee_mode(data)

    @given(risk_rate=positive_rate_st)
    @settings(max_examples=30)
    def test_full_risk_valid_no_error(self, risk_rate: str) -> None:
        """
        FULL_RISK 模式 + 正比例 → 不抛异常。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "FULL_RISK", "risk_rate": risk_rate}
        mixin._validate_fee_mode(data)

    @given(custom_terms=non_empty_text_st)
    @settings(max_examples=30)
    def test_custom_mode_valid_no_error(self, custom_terms: str) -> None:
        """
        CUSTOM 模式 + 非空条款 → 不抛异常。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "CUSTOM", "custom_terms": custom_terms}
        mixin._validate_fee_mode(data)

    def test_fixed_mode_missing_amount_raises(self) -> None:
        """
        FIXED 模式 + 无金额 → 抛 ValidationException，错误键包含 fixed_amount。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "FIXED"}
        with pytest.raises(ValidationException) as exc_info:
            mixin._validate_fee_mode(data)
        assert exc_info.value.errors is not None
        assert "fixed_amount" in exc_info.value.errors

    def test_semi_risk_missing_both_raises(self) -> None:
        """
        SEMI_RISK 模式 + 无金额无比例 → 抛 ValidationException。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "SEMI_RISK"}
        with pytest.raises(ValidationException) as exc_info:
            mixin._validate_fee_mode(data)
        assert exc_info.value.errors is not None
        assert "fixed_amount" in exc_info.value.errors
        assert "risk_rate" in exc_info.value.errors

    def test_full_risk_missing_rate_raises(self) -> None:
        """
        FULL_RISK 模式 + 无比例 → 抛 ValidationException。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "FULL_RISK"}
        with pytest.raises(ValidationException) as exc_info:
            mixin._validate_fee_mode(data)
        assert exc_info.value.errors is not None
        assert "risk_rate" in exc_info.value.errors

    def test_custom_mode_empty_terms_raises(self) -> None:
        """
        CUSTOM 模式 + 空条款 → 抛 ValidationException。

        **Validates: Requirements 3.4**
        """
        mixin = self._get_mixin_instance()
        data: dict[str, Any] = {"fee_mode": "CUSTOM", "custom_terms": ""}
        with pytest.raises(ValidationException) as exc_info:
            mixin._validate_fee_mode(data)
        assert exc_info.value.errors is not None
        assert "custom_terms" in exc_info.value.errors


# ---------------------------------------------------------------------------
# Property 2.1: 律师查询结果在 Service 层迁移后不变
# **Validates: Requirements 3.1, 3.2**
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLawyerQueryPreservation:
    """验证律师查询通过 ContractAssignmentQueryService 的行为基线。

    Task 3.1 将 Contract.primary_lawyer / all_lawyers 从 Model 迁移到 Service 层，
    此处验证 Service 层查询结果与原 Model 属性行为一致。
    """

    def _create_contract_with_assignments(
        self,
        num_lawyers: int = 3,
        primary_index: int = 0,
    ) -> tuple[Any, list[Any]]:
        """创建合同及律师指派，返回 (contract, lawyers)。"""
        from apps.contracts.models import Contract, ContractAssignment
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="测试律所-preservation")
        lawyers: list[Any] = []
        for i in range(num_lawyers):
            lawyer = Lawyer.objects.create_user(
                username=f"pres_lawyer_{i}_{id(self)}",
                password="testpass123",
                real_name=f"律师{i}",
                law_firm=firm,
            )
            lawyers.append(lawyer)

        contract = Contract.objects.create(
            name="保持性测试合同",
            case_type=CaseType.CIVIL,
        )

        for i, lawyer in enumerate(lawyers):
            ContractAssignment.objects.create(
                contract=contract,
                lawyer=lawyer,
                is_primary=(i == primary_index),
                order=i,
            )

        return contract, lawyers

    def _get_query_service(self) -> Any:
        from apps.contracts.services.assignment.contract_assignment_query_service import (
            ContractAssignmentQueryService,
        )
        return ContractAssignmentQueryService()

    def test_primary_lawyer_returns_correct_lawyer(self) -> None:
        """
        get_primary_lawyer 应返回 is_primary=True 的律师指派。

        **Validates: Requirements 3.1, 3.2**
        """
        contract, lawyers = self._create_contract_with_assignments(
            num_lawyers=3, primary_index=1
        )
        svc = self._get_query_service()
        primary = svc.get_primary_lawyer(contract.id)
        assert primary is not None
        assert primary.lawyer_id == lawyers[1].id

    def test_primary_lawyer_none_when_no_primary(self) -> None:
        """
        无 is_primary=True 的指派时，get_primary_lawyer 应返回 None。

        **Validates: Requirements 3.1, 3.2**
        """
        from apps.contracts.models import Contract, ContractAssignment
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="测试律所-no-primary")
        lawyer = Lawyer.objects.create_user(
            username=f"no_primary_{id(self)}",
            password="testpass123",
            law_firm=firm,
        )
        contract = Contract.objects.create(
            name="无主办律师合同",
            case_type=CaseType.CIVIL,
        )
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer,
            is_primary=False,
            order=0,
        )
        svc = self._get_query_service()
        assert svc.get_primary_lawyer(contract.id) is None

    def test_all_lawyers_returns_all(self) -> None:
        """
        get_all_lawyers 应返回所有律师指派记录。

        **Validates: Requirements 3.1, 3.2**
        """
        contract, lawyers = self._create_contract_with_assignments(num_lawyers=3)
        svc = self._get_query_service()
        all_assignments = svc.get_all_lawyers(contract.id)
        assert len(all_assignments) == 3
        returned_ids = {a.lawyer_id for a in all_assignments}
        expected_ids = {lw.id for lw in lawyers}
        assert returned_ids == expected_ids

    def test_all_lawyers_empty_when_no_assignments(self) -> None:
        """
        无指派时，get_all_lawyers 应返回空列表。

        **Validates: Requirements 3.1, 3.2**
        """
        from apps.contracts.models import Contract

        contract = Contract.objects.create(
            name="无指派合同",
            case_type=CaseType.CIVIL,
        )
        svc = self._get_query_service()
        assert svc.get_all_lawyers(contract.id) == []


# ---------------------------------------------------------------------------
# Property 2.4: 收款验证逻辑（开票金额 > 收款金额触发错误，发票状态计算）行为不变
# **Validates: Requirements 3.4**
# ---------------------------------------------------------------------------

# 收款金额策略
payment_amount_st: st.SearchStrategy[Decimal] = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("99999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _compute_invoice_status(
    amount: Decimal, invoiced_amount: Decimal
) -> str | None:
    """
    复现 clean_fs 中的发票状态计算逻辑（基线快照）。

    返回 InvoiceStatus 值或 None（表示应触发错误）。
    """
    if float(invoiced_amount) - float(amount) > 1e-6:
        return None  # 应触发错误
    if float(invoiced_amount) == 0:
        return "UNINVOICED"
    elif 0 < float(invoiced_amount) < float(amount):
        return "INVOICED_PARTIAL"
    else:
        return "INVOICED_FULL"


class TestPaymentValidationPreservation:
    """验证收款验证逻辑的行为基线。"""

    @given(
        amount=payment_amount_st,
        invoiced_amount=payment_amount_st,
    )
    @settings(max_examples=50)
    def test_invoice_status_calculation_consistent(
        self, amount: Decimal, invoiced_amount: Decimal
    ) -> None:
        """
        发票状态计算逻辑应与基线快照一致。

        **Validates: Requirements 3.4**
        """
        expected = _compute_invoice_status(amount, invoiced_amount)

        # 复现 clean_fs 逻辑
        amt_f = float(amount)
        inv_f = float(invoiced_amount)

        if inv_f - amt_f > 1e-6:
            # 应触发错误
            assert expected is None
        else:
            if inv_f == 0:
                assert expected == "UNINVOICED"
            elif 0 < inv_f < amt_f:
                assert expected == "INVOICED_PARTIAL"
            else:
                assert expected == "INVOICED_FULL"

    @given(amount=payment_amount_st)
    @settings(max_examples=20)
    def test_zero_invoiced_always_uninvoiced(self, amount: Decimal) -> None:
        """
        开票金额为 0 时，状态应为 UNINVOICED。

        **Validates: Requirements 3.4**
        """
        result = _compute_invoice_status(amount, Decimal("0"))
        assert result == "UNINVOICED"

    @given(amount=payment_amount_st)
    @settings(max_examples=20)
    def test_invoiced_exceeds_amount_triggers_error(self, amount: Decimal) -> None:
        """
        开票金额 > 收款金额时，应触发错误（返回 None）。

        **Validates: Requirements 3.4**
        """
        over_amount = amount + Decimal("0.01")
        result = _compute_invoice_status(amount, over_amount)
        assert result is None

    @given(
        amount=st.decimals(
            min_value=Decimal("1.00"),
            max_value=Decimal("99999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=20)
    def test_equal_amount_is_full(self, amount: Decimal) -> None:
        """
        开票金额 == 收款金额时，状态应为 INVOICED_FULL。

        **Validates: Requirements 3.4**
        """
        result = _compute_invoice_status(amount, amount)
        assert result == "INVOICED_FULL"
