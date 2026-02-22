"""
测试 Token 查找修复

验证系统能够正确查找任意有效的 Token
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.automation.models import CourtToken, PreservationQuote, QuoteStatus
from apps.automation.services.insurance.preservation_quote_service import get_or_create_token  # type: ignore[attr-defined]


@pytest.mark.django_db(transaction=True)
class TestTokenLookupFix:
    """测试 Token 查找修复"""

    def test_get_or_create_token_finds_any_valid_token(self):
        """
        测试：当不提供账号时，能够找到任意有效的 Token

        验证：
        - 数据库中有有效 Token
        - 不提供账号参数
        - 能够找到并返回 Token
        """
        # 创建一个有效的 Token
        expires_at = timezone.now() + timedelta(hours=2)
        token_obj = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="test_account",
            token="Bearer test_token_123",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 不提供账号，查找任意有效 Token
        token = get_or_create_token(site_name="court_zxfw", account=None)

        # 验证找到了 Token
        assert token is not None
        assert token == "Bearer test_token_123"

    def test_get_or_create_token_prefers_specified_account(self):
        """
        测试：当提供账号时，优先使用指定账号的 Token

        验证：
        - 数据库中有多个有效 Token
        - 提供指定账号
        - 返回指定账号的 Token
        """
        expires_at = timezone.now() + timedelta(hours=2)

        # 创建多个 Token
        token1 = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="account1",
            token="Bearer token1",
            token_type="Bearer",
            expires_at=expires_at,
        )

        token2 = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="account2",
            token="Bearer token2",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 指定账号查找
        token = get_or_create_token(site_name="court_zxfw", account="account2")

        # 验证返回指定账号的 Token
        assert token == "Bearer token2"

    def test_get_or_create_token_ignores_expired_tokens(self):
        """
        测试：忽略已过期的 Token

        验证：
        - 数据库中有过期的 Token
        - 查找时忽略过期 Token
        - 返回 None
        """
        # 创建一个已过期的 Token
        expired_at = timezone.now() - timedelta(hours=1)
        token_obj = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="test_account",
            token="Bearer expired_token",
            token_type="Bearer",
            expires_at=expired_at,
        )

        # 查找 Token
        token = get_or_create_token(site_name="court_zxfw", account=None)

        # 验证没有找到 Token（因为已过期）
        assert token is None

    def test_get_or_create_token_returns_newest_when_multiple_valid(self):
        """
        测试：当有多个有效 Token 时，返回最新的

        验证：
        - 数据库中有多个有效 Token
        - 返回创建时间最新的 Token
        """
        expires_at = timezone.now() + timedelta(hours=2)

        # 创建多个 Token（按时间顺序）
        token1 = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="account1",
            token="Bearer old_token",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 稍后创建
        import time

        time.sleep(0.1)

        token2 = CourtToken.objects.create(  # noqa: F841
            site_name="court_zxfw",
            account="account2",
            token="Bearer new_token",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 查找 Token（不指定账号）
        token = get_or_create_token(site_name="court_zxfw", account=None)

        # 验证返回最新的 Token
        assert token == "Bearer new_token"

    def test_get_or_create_token_returns_none_when_no_tokens(self):
        """
        测试：当没有 Token 时，返回 None

        验证：
        - 数据库中没有匹配的 Token
        - 返回 None

        注意：不删除所有 Token，而是查找不存在的 site_name
        """
        # 查找一个不存在的 site_name
        token = get_or_create_token(site_name="non_existent_site", account=None)

        # 验证返回 None
        assert token is None
