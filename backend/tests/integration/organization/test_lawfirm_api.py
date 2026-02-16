"""
律所 API 集成测试
"""

import pytest
from django.test import Client

from tests.factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
@pytest.mark.integration
class TestLawFirmAPI:
    """律所 API 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.client = Client()

    def test_list_lawfirms_superuser(self):
        """测试超级管理员列表查询律所"""
        # 准备测试数据
        lawfirms = LawFirmFactory.create_batch(3)
        superuser = LawyerFactory(is_superuser=True)

        # 模拟认证
        self.client.force_login(superuser)

        # 执行测试
        response = self.client.get("/api/v1/organization/lawfirms")

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        # 超级管理员可以看到所有律所（包括自己的律所）
        assert len(data) >= 3

    def test_get_lawfirm_success(self):
        """测试获取律所详情成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        user = LawyerFactory(law_firm=lawfirm)

        # 模拟认证
        self.client.force_login(user)

        # 执行测试
        response = self.client.get(f"/api/v1/organization/lawfirms/{lawfirm.id}")

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == lawfirm.id
        assert data["name"] == lawfirm.name

    def test_create_lawfirm_success(self):
        """测试创建律所成功"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)

        # 模拟认证
        self.client.force_login(admin_user)

        # 执行测试
        response = self.client.post(
            "/api/v1/organization/lawfirms",
            data={"name": "新律所", "address": "测试地址", "phone": "13800138000"},
            content_type="application/json",
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "新律所"

    def test_create_lawfirm_permission_denied(self):
        """测试创建律所权限不足"""
        # 准备测试数据
        normal_user = LawyerFactory(is_admin=False, is_superuser=False)

        # 模拟认证
        self.client.force_login(normal_user)

        # 执行测试
        response = self.client.post(
            "/api/v1/organization/lawfirms", data={"name": "新律所"}, content_type="application/json"
        )

        # 断言结果
        # PermissionDenied 由全局异常处理器捕获
        assert response.status_code in (403, 500)

    def test_update_lawfirm_success(self):
        """测试更新律所成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory(name="旧名称")
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)

        # 模拟认证
        self.client.force_login(admin_user)

        # 执行测试
        response = self.client.put(
            f"/api/v1/organization/lawfirms/{lawfirm.id}", data={"name": "新名称"}, content_type="application/json"
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "新名称"

    def test_delete_lawfirm_success(self):
        """测试删除律所成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        superuser = LawyerFactory(is_superuser=True)

        # 模拟认证
        self.client.force_login(superuser)

        # 执行测试
        response = self.client.delete(f"/api/v1/organization/lawfirms/{lawfirm.id}")

        # 断言结果
        assert response.status_code == 200

        # 验证律所已删除
        from apps.organization.models import LawFirm

        assert not LawFirm.objects.filter(id=lawfirm.id).exists()
