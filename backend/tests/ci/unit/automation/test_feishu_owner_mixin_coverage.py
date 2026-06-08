"""测试飞书群主 Mixin 的纯逻辑方法

覆盖: apps/automation/services/chat/_feishu_owner_mixin.py
重点: _classify_feishu_error (纯分类逻辑)
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.exceptions import (
    ChatCreationException,
    ChatProviderException,
    ConfigurationException,
    OwnerSettingException,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_timeout_error,
    owner_validation_error,
)


class _FeishuOwnerMixinStub:
    """测试用 stub，混入 _classify_feishu_error 方法"""

    def __init__(self) -> None:
        self.BASE_URL = "https://open.feishu.cn"
        self.ENDPOINTS = {"get_chat": "/im/v1/chats/{chat_id}"}
        self.config = {"TIMEOUT": 30}
        self.owner_config = MagicMock()
        self.owner_config.is_retry_enabled.return_value = False

    def is_available(self) -> bool:
        return True

    def _get_tenant_access_token(self) -> str:
        return "fake_token"


# 混入 _classify_feishu_error
from apps.automation.services.chat._feishu_owner_mixin import FeishuOwnerMixin


class StubWithClassify(_FeishuOwnerMixinStub, FeishuOwnerMixin):
    pass


@pytest.fixture
def stub() -> StubWithClassify:
    return StubWithClassify()


# ============================================================
# _classify_feishu_error
# ============================================================


class TestClassifyFeishuError:
    """测试飞书 API 错误分类"""

    def test_permission_error_code_99991663(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("99991663", "some error")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_PERMISSION_ERROR"

    def test_permission_error_code_99991664(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("99991664", "some error")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_PERMISSION_ERROR"

    def test_permission_error_by_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "permission denied")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_PERMISSION_ERROR"

    def test_permission_forbidden_in_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "Forbidden access")
        assert isinstance(result, OwnerSettingException)

    def test_not_found_error_code_99991400(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("99991400", "some error")
        # 99991400 matches both not_found and validation - first match wins (not_found)
        assert isinstance(result, OwnerSettingException)

    def test_not_found_by_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("99999", "user not found")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_NOT_FOUND"

    def test_not_found_user_does_not_exist(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("99999", "user does not exist")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_NOT_FOUND"

    def test_validation_by_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "invalid parameter")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_VALIDATION_ERROR"

    def test_timeout_error(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "request timed out")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_TIMEOUT_ERROR"

    def test_network_error(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "network connection failed")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_NETWORK_ERROR"

    def test_unknown_error_returns_chat_creation_exception(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "something completely unknown")
        assert result is ChatCreationException

    def test_case_insensitive_matching(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "PERMISSION DENIED")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_PERMISSION_ERROR"

    def test_permission_error_in_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "no permission to access")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_PERMISSION_ERROR"

    def test_timeout_in_message_lowercase(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "the request timeout occurred")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_TIMEOUT_ERROR"

    def test_network_connection_in_message(self, stub: StubWithClassify) -> None:
        result = stub._classify_feishu_error("0", "connection refused")
        assert isinstance(result, OwnerSettingException)
        assert result.code == "OWNER_NETWORK_ERROR"
