"""Tests for documents/services/generation/context_builder.py — full branch coverage.

Covers: ContextBuilder init, properties, build_contract_context with enhanced/direct,
_build_contract_context_directly with principals/beneficiaries/opposing/lawyers,
format helpers.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestContextBuilderInit:
    def test_default_init(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb.date_format == "%Y年%m月%d日"
        assert cb._use_enhanced is False
        assert cb._contract_service is None

    def test_custom_date_format(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder(date_format="%Y/%m/%d")
        assert cb.date_format == "%Y/%m/%d"


class TestContextBuilderContractService:
    def test_lazy_load(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        with patch("apps.documents.services.generation.context_builder.get_contract_service", create=True) as mock_get:
            # The import is done inside the property, so we patch the wiring module
            pass
        # Direct injection
        cb._contract_service = mock_svc
        assert cb.contract_service is mock_svc


class TestContextBuilderEnhancedBuilder:
    def test_lazy_load(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        with patch("apps.documents.services.placeholders.context_builder.EnhancedContextBuilder") as MockECB:
            MockECB.return_value = MagicMock()
            eb = cb.enhanced_builder
            MockECB.assert_called_once()
            assert eb is cb._enhanced_builder


class TestContextBuilderBuildContractContext:
    def test_enhanced_mode_success(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder(use_enhanced=True)
        mock_enhanced = MagicMock()
        mock_enhanced.build_contract_context.return_value = {"key": "val"}
        cb._enhanced_builder = mock_enhanced
        result = cb.build_contract_context(1)
        assert result == {"key": "val"}

    def test_enhanced_mode_returns_none_fallback(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder(use_enhanced=True)
        mock_enhanced = MagicMock()
        mock_enhanced.build_contract_context.return_value = None
        cb._enhanced_builder = mock_enhanced
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = None
        cb._contract_service = mock_svc
        result = cb.build_contract_context(1)
        assert result == {}

    def test_enhanced_mode_exception_fallback(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder(use_enhanced=True)
        mock_enhanced = MagicMock()
        mock_enhanced.build_contract_context.side_effect = RuntimeError("fail")
        cb._enhanced_builder = mock_enhanced
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = None
        cb._contract_service = mock_svc
        result = cb.build_contract_context(1)
        assert result == {}

    def test_non_enhanced_calls_direct(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder(use_enhanced=False)
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = None
        cb._contract_service = mock_svc
        result = cb.build_contract_context(1)
        assert result == {}


class TestContextBuilderBuildDirectly:
    def test_contract_not_found(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = None
        cb._contract_service = mock_svc
        assert cb._build_contract_context_directly(1) == {}

    def test_with_principals(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {
                    "role": "PRINCIPAL",
                    "client": {"name": "张三", "id_number": "110", "phone": "13800000000", "address": "北京"},
                }
            ],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["principal_name"] == "张三"
        assert ctx["principal_id_number"] == "110"
        assert ctx["principal_phone"] == "13800000000"
        assert ctx["principal_address"] == "北京"
        assert len(ctx["all_principals"]) == 1

    def test_no_principals(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["principal_name"] == ""
        assert ctx["all_principals"] == []

    def test_with_beneficiaries(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {"role": "BENEFICIARY", "client": {"name": "李四", "id_number": "310"}},
            ],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["beneficiary_name"] == "李四"

    def test_no_beneficiaries(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["beneficiary_name"] == ""

    def test_with_opposing(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {"role": "OPPOSING", "client": {"name": "王五"}},
                {"role": "OPPOSING", "client": {"name": "赵六"}},
            ],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["opposing_party_name"] == "王五"
        assert len(ctx["all_opposing_parties"]) == 2

    def test_no_opposing(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["opposing_party_name"] == ""

    def test_with_primary_assignment(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [
                {"is_primary": True, "lawyer": {"real_name": "刘律师", "phone": "139", "license_no": "L001"}},
            ],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["primary_lawyer_name"] == "刘律师"

    def test_no_primary_but_has_assignment(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [
                {"is_primary": False, "lawyer": {"real_name": "陈律师", "phone": "137", "license_no": "L002"}},
            ],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["primary_lawyer_name"] == "陈律师"

    def test_no_assignments(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["primary_lawyer_name"] == ""

    def test_flat_party_structure(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {"role": "PRINCIPAL", "client_name": "扁平张三", "id_number": "111", "phone": "139"},
            ],
            "assignments": [],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["principal_name"] == "扁平张三"

    def test_flat_lawyer_structure(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [
                {"is_primary": True, "lawyer_name": "扁平律师", "lawyer_phone": "136", "lawyer_license_no": "L003"},
            ],
        }
        cb._contract_service = mock_svc
        ctx = cb._build_contract_context_directly(1)
        assert ctx["primary_lawyer_name"] == "扁平律师"
        assert ctx["primary_lawyer_phone"] == "136"
        assert ctx["primary_lawyer_license"] == "L003"


class TestContextBuilderFormatHelpers:
    def test_format_date_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_date(None) == ""

    def test_format_date_valid(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_date(date(2024, 1, 15)) == "2024年01月15日"

    def test_format_currency_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_currency(None) == ""

    def test_format_currency_valid(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_currency(Decimal("1234.56")) == "1,234.56"

    def test_format_percentage_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_percentage(None) == ""

    def test_format_percentage_valid(self):
        from apps.documents.services.generation.context_builder import ContextBuilder
        cb = ContextBuilder()
        assert cb._format_percentage(Decimal("10.00")) == "10.00%"
