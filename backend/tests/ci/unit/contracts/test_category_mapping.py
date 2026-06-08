"""测试归档分类映射

覆盖: apps/contracts/services/archive/category_mapping.py
"""

from __future__ import annotations

import pytest

from apps.contracts.services.archive.category_mapping import (
    ArchiveCategory,
    get_archive_category,
)


class TestGetArchiveCategory:
    """测试合同类型到归档分类的映射"""

    def test_advisor_returns_non_litigation(self) -> None:
        assert get_archive_category("advisor") == ArchiveCategory.NON_LITIGATION

    def test_special_returns_non_litigation(self) -> None:
        assert get_archive_category("special") == ArchiveCategory.NON_LITIGATION

    def test_civil_returns_litigation(self) -> None:
        assert get_archive_category("civil") == ArchiveCategory.LITIGATION

    def test_intl_returns_litigation(self) -> None:
        assert get_archive_category("intl") == ArchiveCategory.LITIGATION

    def test_labor_returns_litigation(self) -> None:
        assert get_archive_category("labor") == ArchiveCategory.LITIGATION

    def test_administrative_returns_litigation(self) -> None:
        assert get_archive_category("administrative") == ArchiveCategory.LITIGATION

    def test_criminal_returns_criminal(self) -> None:
        assert get_archive_category("criminal") == ArchiveCategory.CRIMINAL

    def test_unknown_type_defaults_to_litigation(self) -> None:
        assert get_archive_category("unknown_type") == ArchiveCategory.LITIGATION

    def test_empty_string_defaults_to_litigation(self) -> None:
        assert get_archive_category("") == ArchiveCategory.LITIGATION


class TestArchiveCategory:
    """测试归档分类枚举"""

    def test_values(self) -> None:
        assert ArchiveCategory.NON_LITIGATION == "non_litigation"
        assert ArchiveCategory.LITIGATION == "litigation"
        assert ArchiveCategory.CRIMINAL == "criminal"

    def test_labels(self) -> None:
        assert ArchiveCategory.NON_LITIGATION.label == "法律顾问及非诉事务"
        assert ArchiveCategory.LITIGATION.label == "诉讼/仲裁"
        assert ArchiveCategory.CRIMINAL.label == "刑事案件"
