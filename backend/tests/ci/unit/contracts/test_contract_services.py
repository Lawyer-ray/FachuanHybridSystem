"""合同验证器、访问策略与分类映射单元测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.contracts.services.archive.category_mapping import ArchiveCategory, get_archive_category
from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
from apps.contracts.services.contract.domain.validator import ContractValidator
from apps.contracts.services.contract.integrations.file_hash_utils import (
    compute_file_hash,
    compute_file_hash_from_bytes,
)
from apps.core.exceptions import PermissionDenied, ValidationException


# ── get_archive_category ───────────────────────────────────────────────────

def test_archive_category_civil() -> None:
    """民事 → 诉讼/仲裁。"""
    assert get_archive_category("civil") == ArchiveCategory.LITIGATION


def test_archive_category_criminal() -> None:
    """刑事 → 刑事案件。"""
    assert get_archive_category("criminal") == ArchiveCategory.CRIMINAL


def test_archive_category_advisor() -> None:
    """法律顾问 → 非诉事务。"""
    assert get_archive_category("advisor") == ArchiveCategory.NON_LITIGATION


def test_archive_category_special() -> None:
    """特别 → 非诉事务。"""
    assert get_archive_category("special") == ArchiveCategory.NON_LITIGATION


def test_archive_category_unknown_defaults_litigation() -> None:
    """未知类型默认 → 诉讼/仲裁。"""
    assert get_archive_category("unknown_type") == ArchiveCategory.LITIGATION


def test_archive_category_intl() -> None:
    """国际 → 诉讼/仲裁。"""
    assert get_archive_category("intl") == ArchiveCategory.LITIGATION


def test_archive_category_labor() -> None:
    """劳动 → 诉讼/仲裁。"""
    assert get_archive_category("labor") == ArchiveCategory.LITIGATION


def test_archive_category_administrative() -> None:
    """行政 → 诉讼/仲裁。"""
    assert get_archive_category("administrative") == ArchiveCategory.LITIGATION


# ── ContractValidator ──────────────────────────────────────────────────────

class TestContractValidator:

    def _make_validator(self, stages=None) -> ContractValidator:
        mock_config = MagicMock()
        mock_config.get_stages_for_case_type.return_value = stages or [
            ("first_instance", "一审"),
            ("second_instance", "二审"),
        ]
        return ContractValidator(config=mock_config)

    def test_validate_fee_mode_fixed_valid(self) -> None:
        """固定收费有效。"""
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "FIXED", "fixed_amount": 10000})

    def test_validate_fee_mode_fixed_no_amount(self) -> None:
        """固定收费无金额抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException, match="收费模式验证失败"):
            v.validate_fee_mode({"fee_mode": "FIXED"})

    def test_validate_fee_mode_fixed_zero_amount(self) -> None:
        """固定收费金额为 0 抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "FIXED", "fixed_amount": 0})

    def test_validate_fee_mode_semi_risk_valid(self) -> None:
        """半风险收费有效。"""
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "SEMI_RISK", "fixed_amount": 5000, "risk_rate": 10})

    def test_validate_fee_mode_semi_risk_missing_rate(self) -> None:
        """半风险收费缺少比例抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "SEMI_RISK", "fixed_amount": 5000})

    def test_validate_fee_mode_semi_risk_missing_amount(self) -> None:
        """半风险收费缺少金额抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "SEMI_RISK", "risk_rate": 10})

    def test_validate_fee_mode_full_risk_valid(self) -> None:
        """全风险收费有效。"""
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "FULL_RISK", "risk_rate": 15})

    def test_validate_fee_mode_full_risk_missing_rate(self) -> None:
        """全风险收费缺少比例抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "FULL_RISK"})

    def test_validate_fee_mode_custom_valid(self) -> None:
        """自定义收费有效。"""
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": "按小时收费"})

    def test_validate_fee_mode_custom_empty_terms(self) -> None:
        """自定义收费条款为空抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": ""})

    def test_validate_fee_mode_none(self) -> None:
        """无 fee_mode 不抛出异常。"""
        v = self._make_validator()
        v.validate_fee_mode({})

    def test_validate_stages_valid(self) -> None:
        """有效阶段不抛出异常。"""
        v = self._make_validator()
        result = v.validate_stages(["first_instance"], "civil")
        assert result == ["first_instance"]

    def test_validate_stages_empty(self) -> None:
        """空阶段列表返回空。"""
        v = self._make_validator()
        assert v.validate_stages([], "civil") == []

    def test_validate_stages_invalid(self) -> None:
        """无效阶段抛出异常。"""
        v = self._make_validator()
        with pytest.raises(ValidationException, match="无效的代理阶段"):
            v.validate_stages(["nonexistent"], "civil")


# ── ContractAccessPolicy ──────────────────────────────────────────────────

class TestContractAccessPolicy:

    def _policy(self) -> ContractAccessPolicy:
        return ContractAccessPolicy(contract_access_repo=MagicMock())

    def _user(self, **kwargs) -> SimpleNamespace:
        defaults = {"id": 1, "is_authenticated": True, "is_admin": False}
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_has_access_open_perm(self) -> None:
        """开放权限直接通过。"""
        p = self._policy()
        assert p.has_access(1, None, None, perm_open_access=True) is True

    def test_has_access_unauthenticated(self) -> None:
        """未认证用户无权限。"""
        p = self._policy()
        assert p.has_access(1, self._user(is_authenticated=False), None) is False

    def test_has_access_none_user(self) -> None:
        """None 用户无权限。"""
        p = self._policy()
        assert p.has_access(1, None, None) is False

    def test_has_access_admin(self) -> None:
        """管理员直接通过。"""
        p = self._policy()
        assert p.has_access(1, self._user(is_admin=True), None) is True

    def test_ensure_access_raises(self) -> None:
        """无权限时抛出 PermissionDenied。"""
        p = self._policy()
        with pytest.raises(PermissionDenied):
            p.ensure_access(contract_id=1, user=None, org_access=None)

    def test_ensure_access_passes(self) -> None:
        """有权限时不抛出异常。"""
        p = self._policy()
        p.ensure_access(contract_id=1, user=None, org_access=None, perm_open_access=True)

    def test_can_create_contract_authenticated(self) -> None:
        """认证用户可创建合同。"""
        p = self._policy()
        assert p.can_create_contract(self._user()) is True

    def test_can_create_contract_none(self) -> None:
        """None 用户不可创建合同。"""
        p = self._policy()
        assert p.can_create_contract(None) is False

    def test_filter_queryset_open_perm(self) -> None:
        """开放权限返回原始 qs。"""
        p = self._policy()
        qs = MagicMock()
        result = p.filter_queryset(qs, None, None, perm_open_access=True)
        assert result == qs

    def test_filter_queryset_admin(self) -> None:
        """管理员返回原始 qs。"""
        p = self._policy()
        qs = MagicMock()
        result = p.filter_queryset(qs, self._user(is_admin=True), None)
        assert result == qs

    def test_filter_queryset_unauthenticated(self) -> None:
        """未认证返回 none。"""
        p = self._policy()
        qs = MagicMock()
        p.filter_queryset(qs, self._user(is_authenticated=False), None)
        qs.none.assert_called_once()


# ── file_hash_utils ────────────────────────────────────────────────────────

def test_compute_file_hash_from_bytes_basic() -> None:
    """基本 bytes 哈希计算。"""
    result = compute_file_hash_from_bytes(b"hello world")
    assert len(result) == 64  # SHA-256 hex digest


def test_compute_file_hash_from_bytes_empty() -> None:
    """空 bytes 哈希计算。"""
    result = compute_file_hash_from_bytes(b"")
    assert len(result) == 64


def test_compute_file_hash_from_bytes_consistent() -> None:
    """相同内容产生相同哈希。"""
    data = b"test data for hashing"
    assert compute_file_hash_from_bytes(data) == compute_file_hash_from_bytes(data)


def test_compute_file_hash_from_bytes_different() -> None:
    """不同内容产生不同哈希。"""
    assert compute_file_hash_from_bytes(b"abc") != compute_file_hash_from_bytes(b"def")


def test_compute_file_hash_nonexistent_file() -> None:
    """不存在的文件返回空字符串。"""
    from pathlib import Path
    result = compute_file_hash(Path("/nonexistent/file.txt"))
    assert result == ""


def test_compute_file_hash_real_file(tmp_path) -> None:
    """真实文件哈希计算。"""
    test_file = tmp_path / "test.txt"
    test_file.write_bytes(b"hello world")
    result = compute_file_hash(test_file)
    assert len(result) == 64
    # 与 bytes 版本一致
    assert result == compute_file_hash_from_bytes(b"hello world")
