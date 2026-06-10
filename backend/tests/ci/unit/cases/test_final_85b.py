"""Coverage boost tests for cases module — chat service, party mutation, material query, template generation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException, BusinessException


# ============================================================================
# case_chat_service.py — CaseChatService
# ============================================================================


class TestCaseChatServiceResolveAccess:
    def test_with_ctx(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        ctx = SimpleNamespace(user="u1", org_access="oa1", perm_open_access=True)
        result = svc._resolve_access(user=None, org_access=None, perm_open_access=False, ctx=ctx)
        assert result == ("u1", "oa1", True)

    def test_without_ctx(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        result = svc._resolve_access(user="u2", org_access="oa2", perm_open_access=False, ctx=None)
        assert result == ("u2", "oa2", False)


class TestCaseChatServiceResolveOwnerAndPlatform:
    def test_resolve_owner_id(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        with patch("apps.core.config.get_config", return_value="owner123"):
            result = svc._resolve_owner_id()
            assert result == "owner123"

    def test_resolve_default_platform_from_factory(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        mock_factory = Mock()
        mock_factory.get_available_platforms.return_value = [ChatPlatform.FEISHU]
        with patch.dict("sys.modules", {"apps.automation.services.chat.factory": Mock(ChatProviderFactory=mock_factory)}):
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU

    def test_resolve_default_platform_fallback(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        with patch.dict("sys.modules", {"apps.automation.services.chat.factory": None}):
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU


class TestCaseChatServiceUnbindChat:
    def test_success(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        svc.repo = Mock()
        svc.repo.unbind_chat.return_value = True
        assert svc.unbind_chat(chat_id=1) is True

    def test_raises_validation_on_system_error(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        svc.repo = Mock()
        svc.repo.unbind_chat.side_effect = RuntimeError("db error")
        with pytest.raises(ValidationException):
            svc.unbind_chat(chat_id=1)


class TestCaseChatServiceCreateChatForCase:
    def test_auto_resolves_platform(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        mock_case = Mock()
        mock_case.id = 1
        svc.repo = Mock()
        svc.repo.get_case.return_value = mock_case
        svc._access_policy = Mock()
        svc.name_builder = Mock()
        svc.name_builder.build.return_value = "chat_name"
        svc.provider_facade = Mock()
        mock_provider = Mock()
        svc.provider_facade.get_provider_for_creation.return_value = mock_provider
        mock_result = Mock()
        mock_result.success = True
        mock_result.chat_id = "c1"
        mock_result.chat_name = "Chat"
        svc.provider_facade.create_chat.return_value = mock_result
        svc.repo.create_binding.return_value = Mock(name="Chat")

        with patch.object(svc, "_resolve_default_platform", return_value=ChatPlatform.FEISHU):
            svc.create_chat_for_case(case_id=1)
            svc.provider_facade.get_provider_for_creation.assert_called_once_with(platform=ChatPlatform.FEISHU)

    def test_raises_when_provider_fails(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        mock_case = Mock()
        mock_case.id = 1
        svc.repo = Mock()
        svc.repo.get_case.return_value = mock_case
        svc._access_policy = Mock()
        svc.name_builder = Mock()
        svc.name_builder.build.return_value = "chat_name"
        svc.provider_facade = Mock()
        mock_provider = Mock()
        svc.provider_facade.get_provider_for_creation.return_value = mock_provider
        mock_result = Mock()
        mock_result.success = False
        mock_result.message = "failed"
        mock_result.error_code = "ERR"
        mock_result.raw_response = {}
        svc.provider_facade.create_chat.return_value = mock_result

        from apps.core.exceptions import ChatCreationException
        with pytest.raises(ChatCreationException):
            svc.create_chat_for_case(case_id=1, platform=ChatPlatform.FEISHU)

    def test_wraps_unexpected_error(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform
        from apps.core.exceptions import ChatCreationException

        svc = CaseChatService()
        mock_case = Mock()
        mock_case.id = 1
        svc.repo = Mock()
        svc.repo.get_case.return_value = mock_case
        svc._access_policy = Mock()
        svc.name_builder = Mock()
        svc.name_builder.build.return_value = "chat_name"
        svc.provider_facade = Mock()
        mock_provider = Mock()
        svc.provider_facade.get_provider_for_creation.return_value = mock_provider
        svc.provider_facade.create_chat.side_effect = RuntimeError("boom")

        with pytest.raises(ChatCreationException):
            svc.create_chat_for_case(case_id=1, platform=ChatPlatform.FEISHU)


class TestCaseChatServiceGetOrCreateChat:
    def test_returns_existing(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        mock_case = Mock()
        mock_case.id = 1
        svc.repo = Mock()
        svc.repo.get_case.return_value = mock_case
        svc._access_policy = Mock()
        existing = Mock()
        svc.repo.get_active_chat.return_value = existing

        result = svc.get_or_create_chat(case_id=1, platform=ChatPlatform.FEISHU)
        assert result is existing


class TestCaseChatServiceSendDocumentNotification:
    def test_raises_on_empty_sms(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        with pytest.raises(ValidationException, match="短信内容不能为空"):
            svc.send_document_notification(case_id=1, sms_content="")

    def test_raises_on_whitespace_sms(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        with pytest.raises(ValidationException, match="短信内容不能为空"):
            svc.send_document_notification(case_id=1, sms_content="   ")


class TestCaseChatServiceBindExistingChat:
    def test_raises_on_empty_chat_id(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        from apps.core.models.enums import ChatPlatform
        with pytest.raises(ValidationException, match="群聊ID不能为空"):
            svc.bind_existing_chat(case_id=1, platform=ChatPlatform.FEISHU, chat_id="")

    def test_raises_on_whitespace_chat_id(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        from apps.core.models.enums import ChatPlatform
        with pytest.raises(ValidationException, match="群聊ID不能为空"):
            svc.bind_existing_chat(case_id=1, platform=ChatPlatform.FEISHU, chat_id="   ")


# ============================================================================
# case_chat_service_adapter.py — CaseChatServiceAdapter
# ============================================================================


class TestCaseChatServiceAdapterSendMessage:
    def test_success(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_service.send_document_notification.return_value = mock_result
        adapter = CaseChatServiceAdapter(service=mock_service)
        result = adapter.send_message_to_case_chat(case_id=1, message="hello")
        assert result is True

    def test_failure_raises_business_exception(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.message = "send failed"
        mock_service.send_document_notification.return_value = mock_result
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(BusinessException):
            adapter.send_message_to_case_chat(case_id=1, message="hello")

    def test_not_found_error_reraised(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_service.send_document_notification.side_effect = NotFoundError(
            message="not found", code="NF", errors={}
        )
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(NotFoundError):
            adapter.send_message_to_case_chat(case_id=1, message="hello")

    def test_unexpected_error_wrapped(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_service.send_document_notification.side_effect = RuntimeError("boom")
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(BusinessException):
            adapter.send_message_to_case_chat(case_id=1, message="hello")


class TestCaseChatServiceAdapterGetCaseChatId:
    def test_returns_chat_id(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        adapter = CaseChatServiceAdapter(service=Mock())
        mock_chat = Mock()
        mock_chat.chat_id = "oc_123"
        with patch("apps.cases.models.CaseChat") as MockModel:
            MockModel.objects.filter.return_value.first.return_value = mock_chat
            result = adapter.get_case_chat_id(case_id=1)
            assert result == "oc_123"

    def test_returns_none_when_no_chat(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        adapter = CaseChatServiceAdapter(service=Mock())
        with patch("apps.cases.models.CaseChat") as MockModel:
            MockModel.objects.filter.return_value.first.return_value = None
            result = adapter.get_case_chat_id(case_id=1)
            assert result is None

    def test_raises_on_db_error(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        adapter = CaseChatServiceAdapter(service=Mock())
        with patch("apps.cases.models.CaseChat") as MockModel:
            MockModel.objects.filter.side_effect = RuntimeError("db error")
            with pytest.raises(BusinessException):
                adapter.get_case_chat_id(case_id=1)


class TestCaseChatServiceAdapterGetOrCreateChat:
    def test_calls_service(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_chat = Mock()
        mock_chat.chat_id = "c1"
        mock_service.get_or_create_chat.return_value = mock_chat
        adapter = CaseChatServiceAdapter(service=mock_service)
        result = adapter.get_or_create_chat(case_id=1)
        assert result is mock_chat

    def test_handles_exception(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_service.get_or_create_chat.side_effect = RuntimeError("boom")
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(BusinessException):
            adapter.get_or_create_chat(case_id=1)


class TestCaseChatServiceAdapterSendDocumentNotification:
    def test_success(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_service.send_document_notification.return_value = mock_result
        adapter = CaseChatServiceAdapter(service=mock_service)
        result = adapter.send_document_notification(case_id=1, sms_content="test")
        assert result.success is True

    def test_handles_exception(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_service.send_document_notification.side_effect = RuntimeError("boom")
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(BusinessException):
            adapter.send_document_notification(case_id=1, sms_content="test")

    def test_not_found_reraised(self):
        from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

        mock_service = Mock()
        mock_service.send_document_notification.side_effect = NotFoundError(
            message="not found", code="NF", errors={}
        )
        adapter = CaseChatServiceAdapter(service=mock_service)
        with pytest.raises(NotFoundError):
            adapter.send_document_notification(case_id=1, sms_content="test")


# ============================================================================
# case_party_mutation_service.py — CasePartyMutationService
# ============================================================================


class TestCasePartyMutationService:
    def test_validate_party_in_contract_scope_raises_on_missing_case(self):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        svc = CasePartyMutationService(client_service=Mock(), contract_service=Mock())
        svc.repo = Mock()
        svc.repo.get_case.return_value = None
        with pytest.raises(NotFoundError):
            svc.validate_party_in_contract_scope(case_id=1, client_id=2)

    def test_validate_party_in_contract_scope_returns_true_when_no_contract(self):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        svc = CasePartyMutationService(client_service=Mock(), contract_service=Mock())
        svc.repo = Mock()
        svc.repo.get_case.return_value = Mock(contract_id=None)
        result = svc.validate_party_in_contract_scope(case_id=1, client_id=2)
        assert result is True


# ============================================================================
# case_material_query_service.py — CaseMaterialQueryService
# ============================================================================


class TestCaseMaterialQueryService:
    def test_safe_name_removes_slashes(self):
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        result = svc._safe_name("张某/李某")
        assert "/" not in result

    def test_safe_name_removes_backslashes(self):
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        result = svc._safe_name("张某\\李某")
        assert "\\" not in result
