"""Tests for SMS case binding mixin — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from apps.automation.services.sms._sms_case_binding_mixin import SMSCaseBindingMixin


def _make_mixin() -> SMSCaseBindingMixin:
    class Concrete(SMSCaseBindingMixin):
        @property
        def case_service(self) -> Any:
            return self._cs

        @property
        def lawyer_service(self) -> Any:
            return self._ls

    m = Concrete()
    m._cs = MagicMock()
    m._ls = MagicMock()
    return m


class TestFilterValidCaseNumbers:
    def test_filters_date_format(self) -> None:
        mixin = _make_mixin()
        nums = ["2024年1月1日", "2024年12月31号", "（2024）粤0106民初123号"]
        result = mixin._filter_valid_case_numbers(nums)
        assert "2024年1月1日" not in result
        assert "2024年12月31号" not in result
        assert "（2024）粤0106民初123号" in result

    def test_all_valid(self) -> None:
        mixin = _make_mixin()
        nums = ["（2024）粤0106民初123号", "（2023）粤01民终456号"]
        result = mixin._filter_valid_case_numbers(nums)
        assert len(result) == 2

    def test_empty_list(self) -> None:
        mixin = _make_mixin()
        assert mixin._filter_valid_case_numbers([]) == []

    def test_mixed_valid_invalid(self) -> None:
        mixin = _make_mixin()
        nums = ["2024年6月15日", "（2024）粤0106民初123号", "2023年12月31号"]
        result = mixin._filter_valid_case_numbers(nums)
        assert len(result) == 1

    def test_non_date_with_year_month_not_filtered(self) -> None:
        mixin = _make_mixin()
        nums = ["2024年1月"]
        result = mixin._filter_valid_case_numbers(nums)
        assert len(result) == 1


class TestAddCaseNumbersToCase:
    def test_no_case(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case=None, case_numbers=["2024-CA-123"])
        mixin._add_case_numbers_to_case(sms)

    def test_no_case_numbers(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case=MagicMock(), case_numbers=[])
        mixin._add_case_numbers_to_case(sms)

    def test_valid_numbers_added(self) -> None:
        mixin = _make_mixin()
        case = MagicMock(id=1)
        sms = SimpleNamespace(id=1, case=case, case_numbers=["（2024）粤0106民初123号"])
        mixin._cs.add_case_number_internal.return_value = True
        mixin._ls.get_admin_lawyer.return_value = SimpleNamespace(id=10)
        mixin._add_case_numbers_to_case(sms)
        mixin._cs.add_case_number_internal.assert_called_once()

    def test_exception_handled(self) -> None:
        mixin = _make_mixin()
        case = MagicMock(id=1)
        sms = SimpleNamespace(id=1, case=case, case_numbers=["（2024）粤0106民初123号"])
        mixin._cs.add_case_number_internal.side_effect = Exception("db error")
        mixin._ls.get_admin_lawyer.return_value = SimpleNamespace(id=10)
        mixin._add_case_numbers_to_case(sms)

    def test_all_invalid_numbers(self) -> None:
        mixin = _make_mixin()
        case = MagicMock(id=1)
        sms = SimpleNamespace(id=1, case=case, case_numbers=["2024年1月1日", "2023年12月31号"])
        mixin._add_case_numbers_to_case(sms)
        mixin._cs.add_case_number_internal.assert_not_called()


class TestCleanupOldCaseLog:
    def test_no_case_log_id(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case_log_id=None)
        mixin._cleanup_old_case_log(sms)

    def test_log_not_found(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case_log_id=999, case_log=None, save=MagicMock())
        with patch("apps.cases.models.CaseLog") as mock_log:
            mock_log.objects.filter.return_value.first.return_value = None
            mixin._cleanup_old_case_log(sms)
        assert sms.case_log is None
        sms.save.assert_called_once()

    def test_log_found_with_attachments(self) -> None:
        mixin = _make_mixin()
        att1 = MagicMock()
        att1.file = MagicMock()
        att2 = MagicMock()
        att2.file = None
        old_log = MagicMock()
        old_log.id = 42
        mock_attachments = MagicMock()
        mock_attachments.count.return_value = 2
        mock_attachments.__iter__ = MagicMock(return_value=iter([att1, att2]))
        sms = SimpleNamespace(id=1, case_log_id=42, case_log=None, save=MagicMock())
        with (
            patch("apps.cases.models.CaseLog") as mock_log,
            patch("apps.cases.models.CaseLogAttachment") as mock_att,
        ):
            mock_log.objects.filter.return_value.first.return_value = old_log
            mock_att.objects.filter.return_value = mock_attachments
            mixin._cleanup_old_case_log(sms)
        att1.file.delete.assert_called_once_with(save=False)
        # att2.file is None, so file.delete should never have been called on it
        old_log.delete.assert_called_once()
        sms.save.assert_called_once()

    def test_exception_during_cleanup(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case_log_id=42)
        with patch("apps.cases.models.CaseLog") as mock_log:
            mock_log.objects.filter.side_effect = Exception("db error")
            mixin._cleanup_old_case_log(sms)
