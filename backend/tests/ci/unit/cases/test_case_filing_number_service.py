"""CaseFilingNumberService 单元测试。

覆盖参数校验、序列表缺失的迁移提示（OperationalError 归并）、
内部错误兜底与成功编排。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db.utils import OperationalError

from apps.cases.services.number.case_filing_number_service import CaseFilingNumberService
from apps.core.exceptions import ConflictError, ValidationException
from apps.core.models.enums import SimpleCaseType
from apps.testing.factories import CaseFactory


@pytest.mark.django_db
class TestValidationErrors:
    def test_empty_case_type_rejected(self) -> None:
        case = CaseFactory()
        with pytest.raises(ValidationException) as exc_info:
            CaseFilingNumberService().generate_case_filing_number_internal(case.id, "", 2026)
        assert exc_info.value.code == "INVALID_CASE_TYPE"

    @pytest.mark.parametrize("year", [1899, 2101])
    def test_year_out_of_range_rejected(self, year: int) -> None:
        case = CaseFactory()
        with pytest.raises(ValidationException) as exc_info:
            CaseFilingNumberService().generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, year)
        assert exc_info.value.code == "INVALID_YEAR"

    def test_missing_case_rejected(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            CaseFilingNumberService().generate_case_filing_number_internal(99999, SimpleCaseType.CIVIL, 2026)
        assert exc_info.value.code == "CASE_NOT_FOUND"


@pytest.mark.django_db
class TestSequenceErrors:
    def _service_with_error(self, error: Exception) -> CaseFilingNumberService:
        service = CaseFilingNumberService()
        patcher = patch.object(service, "_get_next_case_sequence", side_effect=error)
        patcher.start()
        self._patcher = patcher
        return service

    def test_missing_table_pg_hint(self) -> None:
        case = CaseFactory()
        service = self._service_with_error(OperationalError('relation "cases_casefilingnumbersequence" does not exist'))
        try:
            with pytest.raises(ConflictError) as exc_info:
                service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)
            assert exc_info.value.code == "FILING_NUMBER_MIGRATION_REQUIRED"
        finally:
            self._patcher.stop()

    def test_missing_table_sqlite_hint(self) -> None:
        case = CaseFactory()
        service = self._service_with_error(OperationalError("no such table: cases_casefilingnumbersequence"))
        try:
            with pytest.raises(ConflictError) as exc_info:
                service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)
            assert exc_info.value.code == "FILING_NUMBER_MIGRATION_REQUIRED"
        finally:
            self._patcher.stop()

    def test_other_operational_error_wrapped_as_conflict(self) -> None:
        """非缺表类 OperationalError 由外层兜底 handler 归并为通用 ConflictError。"""
        case = CaseFactory()
        service = self._service_with_error(OperationalError("connection refused"))
        try:
            with pytest.raises(ConflictError) as exc_info:
                service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)
            assert exc_info.value.code == "FILING_NUMBER_GENERATION_FAILED"
        finally:
            self._patcher.stop()

    def test_unexpected_error_wrapped_as_conflict(self) -> None:
        case = CaseFactory()
        service = self._service_with_error(RuntimeError("boom"))
        try:
            with pytest.raises(ConflictError) as exc_info:
                service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)
            assert exc_info.value.code == "FILING_NUMBER_GENERATION_FAILED"
        finally:
            self._patcher.stop()


@pytest.mark.django_db
class TestHappyPath:
    def test_generates_number_with_type_label(self) -> None:
        case = CaseFactory()
        service = CaseFilingNumberService()
        with patch.object(service, "_get_next_case_sequence", return_value=7) as mock_seq:
            result = service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)

        assert result == "2026_民事_AJ_7"
        mock_seq.assert_called_once_with(2026)

    def test_unknown_type_label_kept_verbatim(self) -> None:
        case = CaseFactory()
        service = CaseFilingNumberService()
        with patch.object(service, "_get_next_case_sequence", return_value=1):
            result = service.generate_case_filing_number_internal(case.id, "特殊类型", 2026)
        assert result == "2026_特殊类型_AJ_1"

    def test_real_sequence_increments(self) -> None:
        """真实序列表：连续两次生成，序号递增且写回 next_value。"""
        from apps.cases.models import CaseFilingNumberSequence

        case = CaseFactory()
        service = CaseFilingNumberService()

        first = service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)
        second = service.generate_case_filing_number_internal(case.id, SimpleCaseType.CIVIL, 2026)

        assert first != second
        seq = CaseFilingNumberSequence.objects.get(year=2026)
        assert int(seq.next_value) >= 2


class TestFormatSimpleCaseTypeLabel:
    @pytest.mark.parametrize(
        ("case_type", "label"),
        [
            (SimpleCaseType.CIVIL, "民事"),
            (SimpleCaseType.ADMINISTRATIVE, "行政"),
            (SimpleCaseType.CRIMINAL, "刑事"),
            (SimpleCaseType.EXECUTION, "申请执行"),
            (SimpleCaseType.BANKRUPTCY, "破产"),
            ("custom", "custom"),
        ],
    )
    def test_labels(self, case_type: str, label: str) -> None:
        assert CaseFilingNumberService()._format_simple_case_type_label(case_type) == label
