"""Batch7 coverage tests for apps.contacts."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contacts.models import CaseContact
from apps.contacts.schemas.contact_schemas import (
    CaseContactIn,
    CaseContactSearchResult,
    CaseContactUpdate,
    __all__,
)


# ── CaseContact model ───────────────────────────────────────────────────────


class TestCaseContact:
    def test_str_method(self) -> None:
        contact = CaseContact.__new__(CaseContact)
        contact.name = "张法官"
        # Mock get_role_display
        contact.get_role_display = lambda: "法官"
        result = str(contact)
        assert "张法官" in result
        assert "法官" in result

    def test_meta_ordering(self) -> None:
        assert CaseContact._meta.ordering == ["created_at"]

    def test_meta_verbose_name(self) -> None:
        assert CaseContact._meta.verbose_name == "案件工作人员"


# ── CaseContactIn schema ────────────────────────────────────────────────────


class TestCaseContactIn:
    def test_basic_creation(self) -> None:
        data = CaseContactIn(
            case_id=1,
            name="张三",
            role="judge",
        )
        assert data.case_id == 1
        assert data.name == "张三"
        assert data.role == "judge"

    def test_optional_fields(self) -> None:
        data = CaseContactIn(
            case_id=1,
            name="张三",
            role="judge",
            phone="13800138000",
            address="广东省广州市",
            stage="first_trial",
            note="备注",
        )
        assert data.phone == "13800138000"
        assert data.address == "广东省广州市"

    def test_optional_authority(self) -> None:
        data = CaseContactIn(case_id=1, name="张三", role="judge")
        assert data.authority_id is None


# ── CaseContactUpdate schema ────────────────────────────────────────────────


class TestCaseContactUpdate:
    def test_all_optional(self) -> None:
        data = CaseContactUpdate()
        assert data.name is None
        assert data.role is None
        assert data.phone is None


# ── CaseContactSearchResult ─────────────────────────────────────────────────


class TestCaseContactSearchResult:
    def test_defaults(self) -> None:
        result = CaseContactSearchResult(name="张三", role="judge")
        assert result.authority_name is None
        assert result.role_display is None
        assert result.occurrence_count == 1
        assert result.case_ids == []


# ── Schema __all__ ──────────────────────────────────────────────────────────


class TestSchemaAll:
    def test_all_exports(self) -> None:
        assert "CaseContactIn" in __all__
        assert "CaseContactOut" in __all__
        assert "CaseContactSearchResult" in __all__
        assert "CaseContactUpdate" in __all__
