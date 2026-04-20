"""court_fetcher 超时控制单元测试。"""

from __future__ import annotations

import time

import pytest

from apps.message_hub.services.court.court_fetcher import _run_callable_with_timeout


class TestRunCallableWithTimeout:
    """验证 Token 登录超时控制不会阻塞 worker。"""

    def test_returns_result_before_timeout(self) -> None:
        """函数在超时前返回时，应正常透传结果。"""

        def _fast() -> str:
            return "ok-token"

        result = _run_callable_with_timeout(_fast, timeout_seconds=1.0)
        assert result == "ok-token"

    def test_raises_timeout_quickly(self) -> None:
        """函数超时时应快速失败，且不等待后台线程完成。"""

        def _slow() -> str:
            time.sleep(1.0)
            return "late-token"

        started = time.monotonic()
        with pytest.raises(TimeoutError, match="Token 获取超时"):
            _run_callable_with_timeout(_slow, timeout_seconds=0.05)
        elapsed = time.monotonic() - started

        # 断言没有被慢函数拖住（显著小于 1 秒）
        assert elapsed < 0.3
