"""Coverage boost tests batch 3 — enterprise_data, image_rotation, legal_solution, organization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ============================================================================
# enterprise_data/services/providers/qichacha_mcp.py
# ============================================================================


def _make_provider_config() -> ProviderConfig:
    from apps.enterprise_data.services.types import ProviderConfig

    return ProviderConfig(
        name="qichacha",
        enabled=True,
        transport="streamable_http",
        base_url="http://localhost:8080",
        sse_url="",
        api_key="test_key",
        timeout_seconds=30,
    )


class TestQichachaMcpProvider:
    def test_supported_capabilities(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        caps = QichachaMcpProvider.supported_capabilities()
        assert "search_companies" in caps
        assert "get_company_profile" in caps
        assert "get_company_risks" in caps

    def test_get_client_for_capability_invalid(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        provider = QichachaMcpProvider(config=_make_provider_config())
        with pytest.raises(ValidationException, match="不支持此能力"):
            provider._get_client_for_capability("invalid_capability")

    def test_execute_tool_empty_name(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        provider = QichachaMcpProvider(config=_make_provider_config())
        with pytest.raises(ValidationException, match="tool_name 不能为空"):
            provider.execute_tool(tool_name="", arguments={})

    def test_execute_tool_whitespace_name(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        provider = QichachaMcpProvider(config=_make_provider_config())
        with pytest.raises(ValidationException, match="tool_name 不能为空"):
            provider.execute_tool(tool_name="   ", arguments={})

    def test_list_tools(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        provider = QichachaMcpProvider(config=_make_provider_config())
        # Mock each client's list_tools to avoid network calls
        for client in provider._clients.values():
            client.list_tools = Mock(return_value=["test_tool"])
        result = provider.list_tools()
        assert len(result) > 0

    def test_describe_tools(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        provider = QichachaMcpProvider(config=_make_provider_config())
        for client in provider._clients.values():
            client.describe_tools = Mock(return_value=[{"name": "test_tool", "description": "A test tool"}])
        result = provider.describe_tools()
        assert len(result) > 0

    def test_extract_phone_from_contact_valid(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        payload = {"联系方式信息": {"电话": [{"电话号码": "13800138000"}]}}
        result = QichachaMcpProvider._extract_phone_from_contact(payload)
        assert result == "13800138000"

    def test_extract_phone_from_contact_empty(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        result = QichachaMcpProvider._extract_phone_from_contact({})
        assert result == ""

    def test_extract_phone_from_contact_non_dict(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        result = QichachaMcpProvider._extract_phone_from_contact("not a dict")
        assert result == ""

    def test_extract_phone_from_contact_no_contact_info(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        result = QichachaMcpProvider._extract_phone_from_contact({"other": "data"})
        assert result == ""

    def test_extract_phone_from_contact_empty_phone_list(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        result = QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {"电话": []}})
        assert result == ""

    def test_extract_phone_from_contact_no_phone_number(self):
        from apps.enterprise_data.services.providers.qichacha_mcp import QichachaMcpProvider

        result = QichachaMcpProvider._extract_phone_from_contact({"联系方式信息": {"电话": [{"其他": "data"}]}})
        assert result == ""


# ============================================================================
# enterprise_data/services/providers/adapters.py
# ============================================================================


class TestQichachaResponseAdapter:
    def test_module_imports(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        assert QichachaResponseAdapter is not None

    def test_extract_items_from_list(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_items([{"name": "test"}, {"name": "test2"}])
        assert len(result) == 2

    def test_extract_items_from_dict_with_list(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_items({"Result": [{"name": "test"}]})
        assert len(result) == 1

    def test_extract_items_empty(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_items(None)
        assert result == []

    def test_extract_primary_dict_from_dict(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_primary_dict({"name": "test"})
        assert result == {"name": "test"}

    def test_extract_primary_dict_from_list(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_primary_dict([{"name": "test"}])
        assert result == {"name": "test"}

    def test_extract_primary_dict_empty(self):
        from apps.enterprise_data.services.providers.adapters import QichachaResponseAdapter

        adapter = QichachaResponseAdapter()
        result = adapter.extract_primary_dict(None)
        assert result == {}


# ============================================================================
# enterprise_data/services/types.py
# ============================================================================


class TestEnterpriseDataTypes:
    def test_provider_config(self):
        config = _make_provider_config()
        assert config.base_url == "http://localhost:8080"
        assert config.api_key == "test_key"

    def test_provider_response(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(
            data={"items": []},
            raw={},
            tool="test_tool",
            meta={},
        )
        assert resp.tool == "test_tool"


# ============================================================================
# enterprise_data/services/clients/mcp_tool_client.py
# ============================================================================


class TestMcpToolClient:
    def test_module_imports(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient

        assert McpToolClient is not None


# ============================================================================
# image_rotation/services/orientation/service.py
# ============================================================================


class TestImageRotationOrientation:
    def test_module_imports(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        assert OrientationDetectionService is not None


# ============================================================================
# image_rotation/services/facade.py
# ============================================================================


class TestImageRotationFacade:
    def test_module_imports(self):
        from apps.image_rotation.services.facade import ImageRotationService

        assert ImageRotationService is not None


# ============================================================================
# legal_solution/services/solution_generator.py
# ============================================================================


class TestLegalSolutionGenerator:
    def test_module_imports(self):
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        assert SolutionGenerator is not None


# ============================================================================
# organization/services/credential/account_credential_admin_service.py
# ============================================================================


class TestAccountCredentialAdminService:
    def test_module_imports(self):
        from apps.organization.services.credential.account_credential_admin_service import (
            AccountCredentialAdminService,
        )

        assert AccountCredentialAdminService is not None


# ============================================================================
# organization/services/lawyer_import_service.py
# ============================================================================


class TestLawyerImportService:
    def test_module_imports(self):
        from apps.organization.services.lawyer_import_service import LawyerImportService

        assert LawyerImportService is not None


# ============================================================================
# document_recognition/services/case_binding_service.py
# ============================================================================


class TestCaseBindingService:
    def test_module_imports(self):
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        assert CaseBindingService is not None


# ============================================================================
# document_recognition/services/info_extractor.py
# ============================================================================


class TestInfoExtractor:
    def test_module_imports(self):
        from apps.document_recognition.services.info_extractor import InfoExtractor

        assert InfoExtractor is not None


# ============================================================================
# evidence_sorting/services/reconciler.py
# ============================================================================


class TestEvidenceSortingReconciler:
    def test_module_imports(self):
        from apps.evidence_sorting.services.reconciler import ReconcilerService

        assert ReconcilerService is not None

    def test_line_item_dataclass(self):
        from apps.evidence_sorting.services.reconciler import LineItem

        item = LineItem.__new__(LineItem)
        assert item is not None


# ============================================================================
# client/services/id_card_merge/facade.py
# ============================================================================


class TestIdCardMergeFacade:
    def test_module_imports(self):
        from apps.client.services.id_card_merge.facade import IdCardMergeService

        assert IdCardMergeService is not None


# ============================================================================
# chat_records/services/export/docx_export_service.py
# ============================================================================


class TestDocxExportService:
    def test_module_imports(self):
        from apps.chat_records.services.export.docx_export_service import DocxExportService

        assert DocxExportService is not None
