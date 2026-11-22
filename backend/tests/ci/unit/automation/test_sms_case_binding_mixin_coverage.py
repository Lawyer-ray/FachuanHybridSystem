"""Tests for SMS case binding mixin — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

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
        # 无案件早退，不触达 case_service
        mixin._cs.add_case_number_internal.assert_not_called()

    def test_no_case_numbers(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case=MagicMock(), case_numbers=[])
        mixin._add_case_numbers_to_case(sms)
        mixin._cs.add_case_number_internal.assert_not_called()

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
        # 异常被吞掉，不向上抛
        mixin._add_case_numbers_to_case(sms)
        mixin._cs.add_case_number_internal.assert_called_once()

    def test_all_invalid_numbers(self) -> None:
        mixin = _make_mixin()
        case = MagicMock(id=1)
        sms = SimpleNamespace(id=1, case=case, case_numbers=["2024年1月1日", "2023年12月31号"])
        mixin._add_case_numbers_to_case(sms)
        mixin._cs.add_case_number_internal.assert_not_called()


class TestUnbindOldCaseLog:
    """审计 P05-03：重新绑定只做软解绑，不得删日志 / 删附件。"""

    def test_no_case_log_id(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case_log_id=None, save=MagicMock())
        mixin._unbind_old_case_log(sms)
        # 无 case_log_id 直接早退，不写库也不查库
        sms.save.assert_not_called()

    def test_unbind_keeps_case_log_row(self) -> None:
        mixin = _make_mixin()
        old_log = MagicMock()
        sms = SimpleNamespace(id=1, case_log_id=999, case_log=old_log, save=MagicMock())
        mixin._unbind_old_case_log(sms)
        assert sms.case_log is None
        sms.save.assert_called_once_with(update_fields=["case_log"])
        old_log.delete.assert_not_called()

    def test_exception_during_unbind_is_swallowed(self) -> None:
        mixin = _make_mixin()
        sms = SimpleNamespace(id=1, case_log_id=42, case_log=MagicMock())
        sms.save = MagicMock(side_effect=Exception("db error"))
        # 异常被吞掉，不向上抛（否则重新绑定整体失败）
        mixin._unbind_old_case_log(sms)
        sms.save.assert_called_once()
