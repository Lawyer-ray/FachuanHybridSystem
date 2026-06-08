"""Coverage tests for apps/cases 0% files.

Covers:
- apps/cases/domain/validators.py  (is_applicable, normalize_stages)
- apps/cases/dependencies.py       (create_message_content, get_chat_provider_factory)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.domain.validators import APPLICABLE_TYPES, is_applicable, normalize_stages


# ── is_applicable ───────────────────────────────────────────────────────────


class TestIsApplicable:
    """is_applicable() 纯逻辑测试。"""

    def test_civil_type_is_applicable(self) -> None:
        assert is_applicable("civil") is True

    def test_criminal_type_is_applicable(self) -> None:
        assert is_applicable("criminal") is True

    def test_administrative_type_is_applicable(self) -> None:
        assert is_applicable("administrative") is True

    def test_labor_type_is_applicable(self) -> None:
        assert is_applicable("labor") is True

    def test_intl_type_is_applicable(self) -> None:
        assert is_applicable("intl") is True

    def test_none_is_not_applicable(self) -> None:
        assert is_applicable(None) is False

    def test_empty_string_is_not_applicable(self) -> None:
        assert is_applicable("") is False

    def test_unknown_type_is_not_applicable(self) -> None:
        assert is_applicable("bankruptcy") is False

    def test_special_type_is_not_applicable(self) -> None:
        """special 和 advisor 不在 APPLICABLE_TYPES 中。"""
        assert is_applicable("special") is False
        assert is_applicable("advisor") is False

    def test_applicable_types_contains_expected(self) -> None:
        assert "civil" in APPLICABLE_TYPES
        assert "criminal" in APPLICABLE_TYPES
        assert "administrative" in APPLICABLE_TYPES
        assert "labor" in APPLICABLE_TYPES
        assert "intl" in APPLICABLE_TYPES
        assert len(APPLICABLE_TYPES) == 5


# ── normalize_stages ────────────────────────────────────────────────────────


class TestNormalizeStages:
    """normalize_stages() 纯逻辑测试。"""

    def test_none_case_type_returns_empty(self) -> None:
        rep, cur = normalize_stages(None, ["first_trial"], "first_trial")
        assert rep == []
        assert cur is None

    def test_non_applicable_type_returns_empty(self) -> None:
        rep, cur = normalize_stages("bankruptcy", ["first_trial"], "first_trial")
        assert rep == []
        assert cur is None

    def test_non_applicable_strict_with_stages_raises(self) -> None:
        with pytest.raises(ValueError, match="stages_not_applicable"):
            normalize_stages("bankruptcy", ["first_trial"], None, strict=True)

    def test_non_applicable_strict_without_stages_ok(self) -> None:
        rep, cur = normalize_stages("bankruptcy", None, None, strict=True)
        assert rep == []
        assert cur is None

    def test_valid_stages_returned(self) -> None:
        rep, cur = normalize_stages("civil", ["first_trial", "second_trial"], "first_trial")
        assert rep == ["first_trial", "second_trial"]
        assert cur == "first_trial"

    def test_invalid_rep_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_rep"):
            normalize_stages("civil", ["first_trial", "bogus_stage"], None)

    def test_invalid_cur_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_cur"):
            normalize_stages("civil", ["first_trial"], "bogus_stage")

    def test_cur_not_in_rep_raises(self) -> None:
        with pytest.raises(ValueError, match="cur_not_in_rep"):
            normalize_stages("civil", ["first_trial"], "second_trial")

    def test_none_stages_returns_empty(self) -> None:
        rep, cur = normalize_stages("civil", None, None)
        assert rep == []
        assert cur is None

    def test_empty_rep_cur_none(self) -> None:
        rep, cur = normalize_stages("civil", [], None)
        assert rep == []
        assert cur is None

    def test_cur_without_rep_allowed(self) -> None:
        """current_stage 可以不在 rep 中，当 rep 为空时不会校验。"""
        rep, cur = normalize_stages("civil", [], "first_trial")
        assert rep == []
        assert cur == "first_trial"

    def test_enforcement_stage_valid(self) -> None:
        rep, cur = normalize_stages("civil", ["enforcement"], "enforcement")
        assert rep == ["enforcement"]
        assert cur == "enforcement"


# ── dependencies.py ─────────────────────────────────────────────────────────


class TestDependencies:
    """cases/dependencies.py 中的工厂函数。"""

    def test_get_chat_provider_factory_returns_class(self) -> None:
        from apps.cases.dependencies import get_chat_provider_factory

        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_cls:
            result = get_chat_provider_factory()
            assert result is mock_cls

    def test_create_message_content_basic(self) -> None:
        from apps.cases.dependencies import create_message_content

        with patch("apps.automation.services.chat.base.MessageContent") as mock_cls:
            mock_cls.return_value = "msg_obj"
            result = create_message_content(title="t", text="body")
            mock_cls.assert_called_once_with(title="t", text="body", file_path=None)
            assert result == "msg_obj"

    def test_create_message_content_with_file(self) -> None:
        from apps.cases.dependencies import create_message_content

        with patch("apps.automation.services.chat.base.MessageContent") as mock_cls:
            mock_cls.return_value = "msg_obj"
            result = create_message_content(title="t", text="body", file_path="/tmp/f.pdf")
            mock_cls.assert_called_once_with(title="t", text="body", file_path="/tmp/f.pdf")

    def test_get_enhanced_context_builder(self) -> None:
        from apps.cases.dependencies import get_enhanced_context_builder

        with patch("apps.documents.services.placeholders.EnhancedContextBuilder") as mock_cls:
            mock_cls.return_value = "builder"
            result = get_enhanced_context_builder()
            assert result == "builder"
            mock_cls.assert_called_once()


# ── re-export compatibility ─────────────────────────────────────────────────


class TestReExportCompatibility:
    """确保 re-export 文件正确透传。"""

    def test_cases_exceptions_re_exports(self) -> None:
        from apps.cases.exceptions import (
            ChatCreationException,
            ConfigurationException,
            OwnerConfigException,
            OwnerNotFoundException,
        )
        assert ChatCreationException is not None
        assert ConfigurationException is not None
        assert OwnerConfigException is not None
        assert OwnerNotFoundException is not None

    def test_cases_validators_re_exports(self) -> None:
        from apps.cases import validators

        assert hasattr(validators, "is_applicable")
        assert hasattr(validators, "normalize_stages")
        assert hasattr(validators, "APPLICABLE_TYPES")

    def test_case_service_compatibility(self) -> None:
        from apps.cases.services.case.case_service import CaseService

        assert CaseService is not None

    def test_caselog_facade_service(self) -> None:
        from apps.cases.services.caselog_service import CaseLogFacadeService, CaseLogService

        assert issubclass(CaseLogFacadeService, CaseLogService)

    def test_folder_binding_facade_service(self) -> None:
        from apps.cases.services.folder_binding_service import CaseFolderBindingFacadeService, CaseFolderBindingService

        assert issubclass(CaseFolderBindingFacadeService, CaseFolderBindingService)

    def test_case_search_service_adapter_re_export(self) -> None:
        from apps.cases.services.case_search_service_adapter import CaseSearchServiceAdapter

        assert CaseSearchServiceAdapter is not None

    def test_chat_wiring_gets_service(self) -> None:
        from apps.cases.services.chat.wiring import get_system_config_service

        with patch("apps.cases.services.chat.wiring.ServiceLocator") as mock_sl:
            mock_sl.get_system_config_service.return_value = "svc"
            result = get_system_config_service()
            assert result == "svc"

    def test_data_wiring_gets_service(self) -> None:
        from apps.cases.services.data.wiring import get_cause_court_query_service

        with patch("apps.cases.services.data.wiring.ServiceLocator") as mock_sl:
            mock_sl.get_cause_court_query_service.return_value = "svc"
            result = get_cause_court_query_service()
            assert result == "svc"

    def test_material_composition_re_export(self) -> None:
        from apps.cases.services.material.composition import build_case_material_service

        assert callable(build_case_material_service)
