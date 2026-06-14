"""Tests for core.exceptions: chat exceptions and error_catalog."""
from __future__ import annotations

from apps.core.exceptions.chat import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    MessageSendException,
    OwnerConfigException,
    OwnerNetworkException,
    OwnerNotFoundException,
    OwnerPermissionException,
    OwnerRetryException,
    OwnerSettingException,
    OwnerTimeoutException,
    OwnerValidationException,
    UnsupportedPlatformException,
    owner_config_error,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_retry_error,
    owner_timeout_error,
    owner_validation_error,
)
from apps.core.exceptions.error_catalog import (
    case_not_found,
    contract_not_found,
    evidence_item_not_found,
    evidence_list_not_found,
)


class TestChatProviderException:
    def test_basic(self) -> None:
        exc = ChatProviderException("err")
        assert exc.error_code is None
        assert exc.platform is None

    def test_with_options(self) -> None:
        exc = ChatProviderException("err", code="C", error_code="E1", platform="feishu")
        assert exc.error_code == "E1"
        assert exc.platform == "feishu"
        assert exc.code == "C"


class TestUnsupportedPlatformException:
    def test_basic(self) -> None:
        exc = UnsupportedPlatformException(platform="slack")
        assert exc.platform == "slack"
        assert exc.code == "UNSUPPORTED_PLATFORM"


class TestChatCreationException:
    def test_basic(self) -> None:
        exc = ChatCreationException("failed", error_code="E1", platform="ding")
        assert exc.error_code == "E1"
        assert exc.platform == "ding"
        assert exc.code == "CHAT_CREATION_ERROR"


class TestMessageSendException:
    def test_basic(self) -> None:
        exc = MessageSendException("send fail", chat_id="chat_123")
        assert exc.chat_id == "chat_123"
        assert exc.code == "MESSAGE_SEND_ERROR"


class TestConfigurationException:
    def test_basic(self) -> None:
        exc = ConfigurationException(missing_config="webhook_url")
        assert exc.missing_config == "webhook_url"
        assert exc.code == "CONFIGURATION_ERROR"


class TestOwnerSettingException:
    def test_basic(self) -> None:
        exc = OwnerSettingException("err", owner_id="u1", chat_id="c1")
        assert exc.owner_id == "u1"
        assert exc.chat_id == "c1"

    def test_extra_kwargs(self) -> None:
        exc = OwnerSettingException("err", retry_count=3)
        assert exc.retry_count == 3


class TestOwnerFactoryFunctions:
    def test_permission(self) -> None:
        exc = owner_permission_error()
        assert exc.code == "OWNER_PERMISSION_ERROR"

    def test_not_found(self) -> None:
        exc = owner_not_found_error()
        assert exc.code == "OWNER_NOT_FOUND"

    def test_validation(self) -> None:
        exc = owner_validation_error()
        assert exc.code == "OWNER_VALIDATION_ERROR"

    def test_retry(self) -> None:
        exc = owner_retry_error()
        assert exc.code == "OWNER_RETRY_ERROR"

    def test_timeout(self) -> None:
        exc = owner_timeout_error()
        assert exc.code == "OWNER_TIMEOUT_ERROR"

    def test_network(self) -> None:
        exc = owner_network_error()
        assert exc.code == "OWNER_NETWORK_ERROR"

    def test_config(self) -> None:
        exc = owner_config_error()
        assert exc.code == "OWNER_CONFIG_ERROR"


class TestOwnerBackwardCompatAliases:
    def test_aliases_are_same_class(self) -> None:
        assert OwnerPermissionException is OwnerSettingException
        assert OwnerNotFoundException is OwnerSettingException
        assert OwnerValidationException is OwnerSettingException
        assert OwnerRetryException is OwnerSettingException
        assert OwnerTimeoutException is OwnerSettingException
        assert OwnerNetworkException is OwnerSettingException
        assert OwnerConfigException is OwnerSettingException


class TestErrorCatalog:
    def test_case_not_found(self) -> None:
        exc = case_not_found(case_id=42)
        assert exc.code == "CASE_NOT_FOUND"
        assert exc.errors["case_id"] == 42

    def test_contract_not_found(self) -> None:
        exc = contract_not_found(contract_id=10)
        assert exc.code == "CONTRACT_NOT_FOUND"
        assert exc.errors["contract_id"] == 10

    def test_evidence_list_not_found(self) -> None:
        exc = evidence_list_not_found(list_id=5)
        assert exc.code == "EVIDENCE_LIST_NOT_FOUND"
        assert exc.errors["list_id"] == 5

    def test_evidence_item_not_found(self) -> None:
        exc = evidence_item_not_found(item_id=7)
        assert exc.code == "EVIDENCE_ITEM_NOT_FOUND"
        assert exc.errors["item_id"] == 7
