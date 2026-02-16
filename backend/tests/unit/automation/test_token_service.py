"""
Token 服务测试
"""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.automation.models import CourtToken
from apps.automation.services.scraper.core.token_service import TokenService
from apps.core.infrastructure.cache import CacheKeys


@pytest.mark.django_db
class TestTokenService:
    """Token 服务测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.token_service = TokenService()
        self.site_name = "court_zxfw"
        self.account = "test_account"
        self.token = "test_token_12345"
        cache.delete(self.token_service._get_cache_key(self.site_name, self.account))

    def teardown_method(self):
        """每个测试后执行"""
        self.token_service.delete_token(self.site_name, self.account)

    def test_save_and_get_token(self):
        """测试保存和获取 Token"""
        # 保存 Token
        self.token_service.save_token(
            site_name=self.site_name,
            account=self.account,
            token=self.token,
            expires_in=3600,
        )

        # 获取 Token
        retrieved_token = self.token_service.get_token(
            site_name=self.site_name,
            account=self.account
        )

        assert retrieved_token == self.token

    def test_get_nonexistent_token(self):
        """测试获取不存在的 Token"""
        token = self.token_service.get_token(
            site_name="nonexistent_site",
            account="nonexistent_account"
        )

        assert token is None

    def test_delete_token(self):
        """测试删除 Token"""
        # 先保存
        self.token_service.save_token(
            site_name=self.site_name,
            account=self.account,
            token=self.token
        )

        # 确认存在
        assert self.token_service.get_token(self.site_name, self.account) is not None

        # 删除
        self.token_service.delete_token(self.site_name, self.account)

        # 确认已删除
        assert self.token_service.get_token(self.site_name, self.account) is None

    def test_get_token_info(self):
        """测试获取 Token 详细信息"""
        # 保存 Token
        self.token_service.save_token(
            site_name=self.site_name,
            account=self.account,
            token=self.token,
            expires_in=3600,
            token_type="JWT",
        )

        # 获取详细信息
        info = self.token_service.get_token_info(self.site_name, self.account)

        assert info is not None
        assert info["token"] == self.token
        assert info["token_type"] == "JWT"
        assert "expires_at" in info
        assert "created_at" in info
        assert "updated_at" in info

    def test_expired_token(self):
        """测试过期的 Token"""
        # 创建一个已过期的 Token
        expired_time = timezone.now() - timedelta(hours=1)

        CourtToken.objects.create(
            site_name=self.site_name,
            account=self.account,
            token=self.token,
            token_type="Bearer",
            expires_at=expired_time,
        )

        # 尝试获取（应该返回 None）
        token = self.token_service.get_token(self.site_name, self.account)

        assert token is None

        # 确认已从数据库删除
        assert not CourtToken.objects.filter(
            site_name=self.site_name,
            account=self.account
        ).exists()

    def test_update_existing_token(self):
        """测试更新已存在的 Token"""
        # 保存第一个 Token
        self.token_service.save_token(
            site_name=self.site_name,
            account=self.account,
            token="old_token",
        )

        # 更新为新 Token
        new_token = "new_token_67890"
        self.token_service.save_token(
            site_name=self.site_name,
            account=self.account,
            token=new_token,
        )

        # 获取 Token（应该是新的）
        retrieved_token = self.token_service.get_token(self.site_name, self.account)

        assert retrieved_token == new_token

        # 确认数据库中只有一条记录
        count = CourtToken.objects.filter(
            site_name=self.site_name,
            account=self.account
        ).count()

        assert count == 1

    def test_cache_key_format(self):
        """测试缓存 key 格式"""
        cache_key = self.token_service._get_cache_key(self.site_name, self.account)

        expected_key = CacheKeys.court_token(site_name=self.site_name, account=self.account)
        assert cache_key == expected_key

    def test_multiple_accounts(self):
        """测试多账号支持"""
        account1 = "account1"
        account2 = "account2"
        token1 = "token1"
        token2 = "token2"

        # 保存两个账号的 Token
        self.token_service.save_token(self.site_name, account1, token1)
        self.token_service.save_token(self.site_name, account2, token2)

        # 获取并验证
        assert self.token_service.get_token(self.site_name, account1) == token1
        assert self.token_service.get_token(self.site_name, account2) == token2

        # 清理
        self.token_service.delete_token(self.site_name, account1)
        self.token_service.delete_token(self.site_name, account2)

    def test_multiple_sites(self):
        """测试多网站支持"""
        site1 = "court_zxfw"
        site2 = "court_guangdong"
        token1 = "token1"
        token2 = "token2"

        # 保存两个网站的 Token
        self.token_service.save_token(site1, self.account, token1)
        self.token_service.save_token(site2, self.account, token2)

        # 获取并验证
        assert self.token_service.get_token(site1, self.account) == token1
        assert self.token_service.get_token(site2, self.account) == token2

        # 清理
        self.token_service.delete_token(site1, self.account)
        self.token_service.delete_token(site2, self.account)
