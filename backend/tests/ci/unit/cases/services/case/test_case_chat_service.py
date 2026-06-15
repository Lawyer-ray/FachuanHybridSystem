"""Tests for cases.services.chat.case_chat_service.

Covers: __init__, _resolve_access, _require_case_access, _resolve_owner_id,
_resolve_default_platform, create_chat_for_case, get_or_create_chat,
send_document_notification, unbind_chat, bind_existing_chat.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock, AsyncMock

import pytest


class TestCaseChatServiceInit:
    def test_default_init(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService()
        assert svc._send_notification_usecase is None

    def test_custom_deps(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        repo = MagicMock()
        name_builder = MagicMock()
        provider_facade = MagicMock()
        recreate_policy = MagicMock()
        access_policy = MagicMock()
        svc = CaseChatService(
            repo=repo,
            name_builder=name_builder,
            provider_facade=provider_facade,
            recreate_policy=recreate_policy,
            access_policy=access_policy,
        )
        assert svc.repo is repo
        assert svc.name_builder is name_builder
        assert svc.provider_facade is provider_facade
        assert svc._access_policy is access_policy

    def test_access_policy_lazy(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService()
        with patch("apps.cases.services.chat.case_chat_service.CaseAccessPolicy") as MockPolicy:
            policy = svc.access_policy
            assert policy is MockPolicy.return_value
            # Second call should reuse
            assert svc.access_policy is policy


class TestResolveAccess:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(access_policy=MagicMock())

    def test_with_context(self):
        svc = self._make_svc()
        ctx = SimpleNamespace(user="u", org_access="o", perm_open_access=True)
        result = svc._resolve_access(user=None, org_access=None, perm_open_access=False, ctx=ctx)
        assert result == ("u", "o", True)

    def test_without_context(self):
        svc = self._make_svc()
        result = svc._resolve_access(user="u", org_access="o", perm_open_access=True, ctx=None)
        assert result == ("u", "o", True)


class TestRequireCaseAccess:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(access_policy=MagicMock())

    def test_calls_ensure_access(self):
        svc = self._make_svc()
        case = SimpleNamespace(id=1)
        svc._require_case_access(case, user="u", org_access="o", perm_open_access=True, ctx=None)
        svc.access_policy.ensure_access.assert_called_once()


class TestResolveDefaultPlatform:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService()

    def test_returns_first_available(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as MockFactory:
            MockFactory.get_available_platforms.return_value = [ChatPlatform.DINGTALK]
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.DINGTALK

    def test_returns_feishu_when_empty(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as MockFactory:
            MockFactory.get_available_platforms.return_value = []
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU

    def test_returns_feishu_on_exception(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as MockFactory:
            MockFactory.get_available_platforms.side_effect = Exception("import fail")
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU


class TestCreateChatForCase:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(
            repo=MagicMock(),
            name_builder=MagicMock(),
            provider_facade=MagicMock(),
            access_policy=MagicMock(),
        )

    def test_success(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.name_builder.build.return_value = "chat_name"
        create_result = SimpleNamespace(
            success=True, chat_id="oc_123", chat_name="chat_name", message=None, error_code=None, raw_response=None
        )
        svc.provider_facade.get_provider_for_creation.return_value = MagicMock()
        svc.provider_facade.create_chat.return_value = create_result
        svc.repo.create_binding.return_value = SimpleNamespace(name="chat_name")
        result = svc.create_chat_for_case(case_id=1, platform=ChatPlatform.FEISHU)
        assert result.name == "chat_name"

    def test_creation_failure(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.name_builder.build.return_value = "chat_name"
        create_result = SimpleNamespace(
            success=False, chat_id=None, chat_name=None, message="fail",
            error_code="ERR", raw_response=None,
        )
        svc.provider_facade.get_provider_for_creation.return_value = MagicMock()
        svc.provider_facade.create_chat.return_value = create_result
        with pytest.raises(Exception):
            svc.create_chat_for_case(case_id=1, platform=ChatPlatform.FEISHU)


class TestGetOrCreateChat:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(
            repo=MagicMock(),
            name_builder=MagicMock(),
            provider_facade=MagicMock(),
            access_policy=MagicMock(),
        )

    def test_existing_chat_returned(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        existing = SimpleNamespace(chat_id="oc_existing", name="existing_chat")
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.repo.get_active_chat.return_value = existing
        result = svc.get_or_create_chat(case_id=1, platform=ChatPlatform.FEISHU)
        assert result.chat_id == "oc_existing"

    def test_no_existing_creates(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.repo.get_active_chat.return_value = None
        svc.name_builder.build.return_value = "name"
        create_result = SimpleNamespace(
            success=True, chat_id="oc_new", chat_name="name",
            message=None, error_code=None, raw_response=None,
        )
        svc.provider_facade.get_provider_for_creation.return_value = MagicMock()
        svc.provider_facade.create_chat.return_value = create_result
        svc.repo.create_binding.return_value = SimpleNamespace(name="name")
        result = svc.get_or_create_chat(case_id=1, platform=ChatPlatform.FEISHU)
        assert result.name == "name"


class TestSendDocumentNotification:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(
            repo=MagicMock(),
            name_builder=MagicMock(),
            provider_facade=MagicMock(),
            access_policy=MagicMock(),
        )

    def test_empty_content_raises(self):
        svc = self._make_svc()
        with pytest.raises(Exception, match="短信内容不能为空"):
            svc.send_document_notification(case_id=1, sms_content="")

    def test_whitespace_content_raises(self):
        svc = self._make_svc()
        with pytest.raises(Exception, match="短信内容不能为空"):
            svc.send_document_notification(case_id=1, sms_content="   ")


class TestUnbindChat:
    def test_success(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService(repo=MagicMock())
        svc.repo.unbind_chat.return_value = True
        assert svc.unbind_chat(chat_id=1) is True

    def test_system_error(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService(repo=MagicMock())
        svc.repo.unbind_chat.side_effect = Exception("fail")
        with pytest.raises(Exception):
            svc.unbind_chat(chat_id=1)


class TestBindExistingChat:
    def _make_svc(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        return CaseChatService(
            repo=MagicMock(),
            name_builder=MagicMock(),
            provider_facade=MagicMock(),
            access_policy=MagicMock(),
        )

    def test_empty_chat_id_raises(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        with pytest.raises(Exception, match="群聊ID不能为空"):
            svc.bind_existing_chat(
                case_id=1, platform=ChatPlatform.FEISHU, chat_id=""
            )

    def test_whitespace_chat_id_raises(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        with pytest.raises(Exception, match="群聊ID不能为空"):
            svc.bind_existing_chat(
                case_id=1, platform=ChatPlatform.FEISHU, chat_id="   "
            )

    def test_success(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.provider_facade.try_get_chat_name.return_value = "chat_name"
        svc.repo.create_binding.return_value = SimpleNamespace(name="chat_name")
        result = svc.bind_existing_chat(
            case_id=1, platform=ChatPlatform.FEISHU, chat_id="oc_123", chat_name="my_chat"
        )
        assert result.name == "chat_name"

    def test_no_name_fetched_from_provider(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.provider_facade.try_get_chat_name.return_value = "fetched_name"
        svc.repo.create_binding.return_value = SimpleNamespace(name="fetched_name")
        result = svc.bind_existing_chat(
            case_id=1, platform=ChatPlatform.FEISHU, chat_id="oc_123"
        )
        assert result.name == "fetched_name"

    def test_provider_no_name_uses_builder(self):
        svc = self._make_svc()
        from apps.core.models.enums import ChatPlatform
        svc.repo.get_case.return_value = SimpleNamespace(id=1)
        svc.provider_facade.try_get_chat_name.return_value = None
        svc.name_builder.build.return_value = "built_name"
        svc.repo.create_binding.return_value = SimpleNamespace(name="built_name")
        result = svc.bind_existing_chat(
            case_id=1, platform=ChatPlatform.FEISHU, chat_id="oc_123"
        )
        assert result.name == "built_name"
