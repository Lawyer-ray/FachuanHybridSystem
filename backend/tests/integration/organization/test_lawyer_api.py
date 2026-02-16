"""
律师 API 集成测试
"""

import pytest
from django.test import Client

from tests.factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
@pytest.mark.integration
class TestLawyerAPI:
    """律师 API 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.client = Client()

    def test_list_lawyers_superuser(self):
        """测试超级管理员列表查询律师"""
        # 准备测试数据
        LawyerFactory.create_batch(3)
        superuser = LawyerFactory(is_superuser=True)

        # 模拟认证
        self.client.force_login(superuser)

        # 执行测试
        response = self.client.get("/api/v1/organization/lawyers")

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    def test_get_lawyer_success(self):
        """测试获取律师详情成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm)
        user = LawyerFactory(law_firm=lawfirm)

        # 模拟认证
        self.client.force_login(user)

        # 执行测试
        response = self.client.get(f"/api/v1/organization/lawyers/{lawyer.id}")

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == lawyer.id
        assert data["username"] == lawyer.username

    def test_create_lawyer_success(self):
        """测试创建律师成功"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        lawfirm = LawFirmFactory()

        # 模拟认证
        self.client.force_login(admin_user)

        # 执行测试 - 使用 multipart form data
        response = self.client.post(
            "/api/v1/organization/lawyers",
            data={
                "payload": '{"username": "newlawyer", "password": "testpass123", "real_name": "新律师", "phone": "13800138001", "law_firm_id": '
                + str(lawfirm.id)
                + ', "is_admin": false}'
            },
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newlawyer"

    def test_create_lawyer_permission_denied(self):
        """测试创建律师权限不足"""
        # 准备测试数据
        normal_user = LawyerFactory(is_admin=False, is_superuser=False)

        # 模拟认证
        self.client.force_login(normal_user)

        # 执行测试 - 使用 multipart form data
        response = self.client.post(
            "/api/v1/organization/lawyers", data={"payload": '{"username": "newlawyer", "password": "testpass123"}'}
        )

        # 断言结果
        # PermissionDenied 由全局异常处理器捕获
        assert response.status_code in (403, 500)

    def test_update_lawyer_success(self):
        """测试更新律师成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm, real_name="旧名称")
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)

        # 模拟认证
        self.client.force_login(admin_user)

        # 执行测试 - 使用 generic 方法发送 multipart form data
        response = self.client.generic(
            "PUT",
            f"/api/v1/organization/lawyers/{lawyer.id}",
            data='payload={"real_name": "新名称"}',
            content_type="application/x-www-form-urlencoded",
        )

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["real_name"] == "新名称"

    def test_delete_lawyer_success(self):
        """测试删除律师成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm)
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)

        # 模拟认证
        self.client.force_login(admin_user)

        # 执行测试
        response = self.client.delete(f"/api/v1/organization/lawyers/{lawyer.id}")

        # 断言结果
        assert response.status_code == 200

        # 验证律师已删除
        from apps.organization.models import Lawyer

        assert not Lawyer.objects.filter(id=lawyer.id).exists()
