"""安全审计（2026Q4 IDOR）：LitigationConsumer._get_session 属主校验。

历史实现只按 session_id 查存在性，不校验 user_id——任意已认证用户连接
``ws/litigation/sessions/<他人 session_id>/`` 即可实时接收对方的文书生成
对话推送（案情、当事人、诉状草稿），并可在他人会话上驱动流程推进。
同资源的 HTTP API（session_lifecycle_service.get_session）是有校验的，
两条链路防护不一致，WS 成为绕行通道。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer


def _make_consumer(user: Any) -> LitigationConsumer:
    consumer = LitigationConsumer.__new__(LitigationConsumer)
    consumer.session_id = "sess-1"
    consumer.user = user
    return consumer


class TestGetSessionOwnership:
    @pytest.mark.asyncio
    async def test_owner_can_fetch_own_session(self) -> None:
        consumer = _make_consumer(SimpleNamespace(id=7, is_authenticated=True))
        found = SimpleNamespace(pk=1)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.filter.return_value.first.return_value = found
            result = await consumer._get_session("sess-1")

        assert result is found
        # 必须按 user_id 收敛
        assert mock_model.objects.filter.return_value.filter.call_args.kwargs == {"user_id": 7}

    @pytest.mark.asyncio
    async def test_non_owner_gets_none(self) -> None:
        """他人 session_id 查不到 → connect() 关闭连接（4004）。"""
        consumer = _make_consumer(SimpleNamespace(id=7, is_authenticated=True))
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.filter.return_value.first.return_value = None
            result = await consumer._get_session("someone-elses-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_superuser_bypasses_user_filter(self) -> None:
        consumer = _make_consumer(SimpleNamespace(id=7, is_superuser=True))
        found = SimpleNamespace(pk=1)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = found
            result = await consumer._get_session("sess-1")

        assert result is found
        # 管理员不做 user_id 收敛（只有一次 filter）
        assert mock_model.objects.filter.return_value.filter.call_count == 0

    @pytest.mark.asyncio
    async def test_is_admin_flag_bypasses_user_filter(self) -> None:
        """Lawyer.is_admin 与 superuser 同口径。"""
        consumer = _make_consumer(SimpleNamespace(id=7, is_admin=True))
        found = SimpleNamespace(pk=1)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = found
            result = await consumer._get_session("sess-1")

        assert result is found
        assert mock_model.objects.filter.return_value.filter.call_count == 0

    @pytest.mark.asyncio
    async def test_no_user_attr_scopes_to_none_id(self) -> None:
        """consumer.user 缺失时不放开收敛（fail-closed：按 None 过滤查不到）。"""
        consumer = _make_consumer(None)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.filter.return_value.first.return_value = None
            result = await consumer._get_session("sess-1")

        assert result is None
        assert mock_model.objects.filter.return_value.filter.call_args.kwargs == {"user_id": None}
