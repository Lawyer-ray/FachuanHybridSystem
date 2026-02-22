"""
立案引导向导视图测试

验证：
- 未登录访问重定向
- 登录后可以访问
- 上下文数据正确
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestWizardView:
    """立案引导向导视图测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试环境"""
        self.client = Client()
        self.url = "/onboarding/wizard/"

        # 创建测试用户
        self.user = User.objects.create_user(username="testuser", password="testpass123")

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_unauthenticated_redirect(self):
        """
        Property 8: 未登录访问重定向
        Validates: Requirements 10.1

        未登录用户访问立案引导页面应重定向到登录页面
        """
        response = self.client.get(self.url)

        # 应该返回 302 重定向
        assert response.status_code == 302
        # 重定向目标应该包含登录页面
        assert "login" in response.url.lower()  # type: ignore[attr-defined]

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_authenticated_access(self):
        """
        登录用户可以访问立案引导页面
        Validates: Requirements 10.2
        """
        # 登录
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        # 应该返回 200 成功
        assert response.status_code == 200

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_context_contains_case_types(self):
        """
        上下文应包含合同类型选项
        Validates: Requirements 4.3
        """
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        assert "case_types" in response.context
        case_types = response.context["case_types"]

        # 验证包含必要的合同类型
        values = [ct["value"] for ct in case_types]
        assert "civil" in values  # 民商事诉讼
        assert "advisor" in values  # 常法顾问
        assert "special" in values  # 专项服务

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_context_contains_fee_modes(self):
        """
        上下文应包含收费模式选项
        Validates: Requirements 4.4, 4.5
        """
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        assert "fee_modes" in response.context
        fee_modes = response.context["fee_modes"]

        # 验证包含必要的收费模式
        values = [fm["value"] for fm in fee_modes]
        assert "FIXED" in values  # 固定收费
        assert "SEMI_RISK" in values  # 半风险
        assert "FULL_RISK" in values  # 全风险

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_context_contains_client_types(self):
        """
        上下文应包含当事人类型选项
        Validates: Requirements 3.7
        """
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        assert "client_types" in response.context
        client_types = response.context["client_types"]

        # 验证包含必要的当事人类型
        values = [ct["value"] for ct in client_types]
        assert "natural" in values  # 自然人
        assert "legal" in values  # 法人
        assert "non_legal_org" in values  # 非法人组织

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_context_contains_legal_statuses(self):
        """
        上下文应包含诉讼地位选项
        Validates: Requirements 5.6
        """
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        assert "legal_statuses" in response.context
        legal_statuses = response.context["legal_statuses"]

        # 验证包含必要的诉讼地位
        values = [ls["value"] for ls in legal_statuses]
        assert "plaintif" in values  # 原告
        assert "defendant" in values  # 被告

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
    def test_context_contains_case_stages(self):
        """
        上下文应包含案件阶段选项
        Validates: Requirements 5.3
        """
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(self.url)

        assert "case_stages" in response.context
        case_stages = response.context["case_stages"]

        # 验证包含必要的案件阶段
        values = [cs["value"] for cs in case_stages]
        assert "first_trial" in values  # 一审
        assert "second_trial" in values  # 二审
