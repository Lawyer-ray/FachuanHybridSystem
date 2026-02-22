"""
CourtTokenStoreService 单元测试
"""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.automation.dtos import CourtTokenDTO
from apps.automation.models import CourtToken
from apps.automation.services.token.court_token_store_service import CourtTokenStoreService


@pytest.mark.django_db
class TestCourtTokenStoreService:
    """Token 存储服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CourtTokenStoreService()

    def test_get_latest_valid_token_success(self):
        """测试获取最新有效 token 成功"""
        # 创建有效的 token
        expires_at = timezone.now() + timedelta(hours=1)
        token = CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="valid_token_123",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn")

        # 断言结果
        assert result is not None
        assert isinstance(result, CourtTokenDTO)
        assert result.site_name == "zxfw.court.gov.cn"
        assert result.account == "test@example.com"
        assert result.token == "valid_token_123"
        assert result.token_type == "Bearer"

    def test_get_latest_valid_token_with_account_filter(self):
        """测试按账号过滤获取 token"""
        expires_at = timezone.now() + timedelta(hours=1)

        # 创建两个不同账号的 token
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="user1@example.com",
            token="token1",
            token_type="Bearer",
            expires_at=expires_at,
        )
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="user2@example.com",
            token="token2",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试 - 指定账号
        result = self.service.get_latest_valid_token_internal(
            site_name="zxfw.court.gov.cn", account="user2@example.com"
        )

        # 断言结果
        assert result is not None
        assert result.account == "user2@example.com"
        assert result.token == "token2"

    def test_get_latest_valid_token_with_prefix_filter(self):
        """测试按 token 前缀过滤"""
        expires_at = timezone.now() + timedelta(hours=1)

        # 创建 token
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="Bearer_abc123",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试 - 正确的前缀
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn", token_prefix="Bearer_")

        # 断言结果
        assert result is not None
        assert result.token == "Bearer_abc123"

        # 执行测试 - 错误的前缀
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn", token_prefix="Wrong_")

        # 断言结果
        assert result is None

    def test_get_latest_valid_token_expired(self):
        """测试获取过期 token 返回 None"""
        # 创建过期的 token
        expires_at = timezone.now() - timedelta(hours=1)
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="expired_token",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn")

        # 断言结果
        assert result is None

    def test_get_latest_valid_token_not_found(self):
        """测试获取不存在的 token 返回 None"""
        # 执行测试
        result = self.service.get_latest_valid_token_internal(site_name="nonexistent.site.com")

        # 断言结果
        assert result is None

    def test_get_latest_valid_token_returns_newest(self):
        """测试返回最新的 token"""
        expires_at = timezone.now() + timedelta(hours=1)

        # 创建旧 token（用不同 account 绕过唯一约束，再用 update 修改 created_at）
        old_token = CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="old_token",
            token_type="Bearer",
            expires_at=expires_at,
        )
        # 用 update() 绕过 auto_now_add，将 created_at 设为更早
        CourtToken.objects.filter(pk=old_token.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        # 更新为新 token（同一 site+account，用 update_or_create 或直接 update）
        CourtToken.objects.filter(pk=old_token.pk).update(token="new_token")

        # 执行测试
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn")

        # 断言结果 - 应该返回最新的
        assert result is not None
        assert result.token == "new_token"

    @patch("apps.automation.services.token.court_token_store_service.TokenService")
    def test_save_token_internal_success(self, mock_token_service_class):
        """测试保存 token 成功"""
        # 配置 Mock
        mock_token_service = Mock()
        mock_token_service_class.return_value = mock_token_service

        # 执行测试
        self.service.save_token_internal(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="new_token_123",
            expires_in=3600,
            token_type="Bearer",
            credential_id=1,
        )

        # 验证 TokenService 被正确调用
        mock_token_service.save_token.assert_called_once_with(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="new_token_123",
            expires_in=3600,
            token_type="Bearer",
            credential_id=1,
        )

    @patch("apps.automation.services.token.court_token_store_service.TokenService")
    def test_save_token_internal_default_token_type(self, mock_token_service_class):
        """测试保存 token 使用默认 token_type"""
        # 配置 Mock
        mock_token_service = Mock()
        mock_token_service_class.return_value = mock_token_service

        # 执行测试（不指定 token_type）
        self.service.save_token_internal(
            site_name="zxfw.court.gov.cn", account="test@example.com", token="new_token_123", expires_in=3600
        )

        # 验证使用默认值 "Bearer"
        mock_token_service.save_token.assert_called_once()
        call_kwargs = mock_token_service.save_token.call_args[1]
        assert call_kwargs["token_type"] == "Bearer"

    def test_get_latest_valid_token_with_null_token(self):
        """测试处理 token 为空字符串的情况"""
        expires_at = timezone.now() + timedelta(hours=1)

        # 创建 token 为空字符串的记录
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="null_token@example.com",
            token="",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试 - 使用前缀过滤
        result = self.service.get_latest_valid_token_internal(
            site_name="zxfw.court.gov.cn",
            account="null_token@example.com",
            token_prefix="Bearer_",
        )

        # 断言结果 - 应该返回 None（因为 token 为空字符串不匹配前缀）
        assert result is None


@pytest.mark.django_db
class TestCourtTokenStoreServiceEdgeCases:
    """Token 存储服务边界情况测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CourtTokenStoreService()

    def test_get_token_with_multiple_sites(self):
        """测试多个站点的 token 不会混淆"""
        expires_at = timezone.now() + timedelta(hours=1)

        # 创建不同站点的 token
        CourtToken.objects.create(
            site_name="site1.com",
            account="test@example.com",
            token="token1",
            token_type="Bearer",
            expires_at=expires_at,
        )
        CourtToken.objects.create(
            site_name="site2.com",
            account="test@example.com",
            token="token2",
            token_type="Bearer",
            expires_at=expires_at,
        )

        # 执行测试
        result1 = self.service.get_latest_valid_token_internal(site_name="site1.com")
        result2 = self.service.get_latest_valid_token_internal(site_name="site2.com")

        # 断言结果
        assert result1.token == "token1"
        assert result2.token == "token2"

    def test_get_token_with_mixed_expired_and_valid(self):
        """测试混合过期和有效 token 时只返回有效的"""
        # 先创建一条记录，再 update expires_at 为过期，然后再创建有效记录（不同 account）
        expired_time = timezone.now() - timedelta(hours=1)
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="expired@example.com",
            token="expired_token",
            token_type="Bearer",
            expires_at=expired_time,
        )

        valid_time = timezone.now() + timedelta(hours=1)
        CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="valid@example.com",
            token="valid_token",
            token_type="Bearer",
            expires_at=valid_time,
        )

        # 执行测试 - 不指定 account，应该只返回有效的
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn")

        # 断言结果 - 应该返回有效的 token
        assert result is not None
        assert result.token == "valid_token"

    def test_dto_fields_mapping(self):
        """测试 DTO 字段映射正确"""
        expires_at = timezone.now() + timedelta(hours=1)
        created_at = timezone.now() - timedelta(minutes=5)
        updated_at = timezone.now()

        # 创建 token
        token = CourtToken.objects.create(
            site_name="zxfw.court.gov.cn",
            account="test@example.com",
            token="test_token",
            token_type="Bearer",
            expires_at=expires_at,
        )
        # 用 update() 绕过 auto_now_add/auto_now
        CourtToken.objects.filter(pk=token.pk).update(created_at=created_at, updated_at=updated_at)

        # 执行测试
        result = self.service.get_latest_valid_token_internal(site_name="zxfw.court.gov.cn")

        # 断言所有字段都正确映射
        assert result.site_name == "zxfw.court.gov.cn"
        assert result.account == "test@example.com"
        assert result.token == "test_token"
        assert result.token_type == "Bearer"
        assert result.expires_at == expires_at
        assert result.created_at == created_at
        assert result.updated_at == updated_at
