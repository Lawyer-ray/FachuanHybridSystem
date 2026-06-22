"""登录处理器和文档转换服务测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

if _HAS_LOGIN:
    from plugins.court_automation.token._login_handler import LoginHandler
else:
    LoginHandler = None  # type: ignore[assignment,misc]

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestLoginHandler:
    """LoginHandler 测试。"""

    def setup_method(self) -> None:
        self.account_selection_strategy = MagicMock()
        self.auto_login_service = MagicMock()
        self.token_service = MagicMock()
        self.concurrency_config = SimpleNamespace(
            acquisition_timeout=300.0,
            max_concurrent_acquisitions=3,
            max_concurrent_per_site=2,
            max_concurrent_per_account=1,
            lock_timeout=30.0,
            queue_timeout=60.0,
            resource_check_interval=1.0,
        )
        self.handler = LoginHandler(
            account_selection_strategy=self.account_selection_strategy,
            auto_login_service=self.auto_login_service,
            token_service=self.token_service,
            concurrency_config=self.concurrency_config,
        )

    def test_handler_creation(self) -> None:
        """创建 LoginHandler。"""
        assert self.handler._account_selection_strategy is self.account_selection_strategy
        assert self.handler._auto_login_service is self.auto_login_service
        assert self.handler._token_service is self.token_service
        assert self.handler._concurrency_config is self.concurrency_config

    def test_concurrency_config_values(self) -> None:
        """并发配置值。"""
        assert self.concurrency_config.acquisition_timeout == 300.0
        assert self.concurrency_config.max_concurrent_acquisitions == 3
