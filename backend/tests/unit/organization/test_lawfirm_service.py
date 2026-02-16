"""
律所服务单元测试
"""

from unittest.mock import Mock

import pytest

from apps.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationException
from apps.organization.schemas import LawFirmIn, LawFirmUpdateIn
from apps.organization.services import LawFirmService
from tests.factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
class TestLawFirmService:
    """律所服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = LawFirmService()

    def test_create_lawfirm_success(self):
        """测试创建律所成功"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        data = LawFirmIn(
            name="测试律所", address="测试地址", phone="13800138000", social_credit_code="91110000000000000X"
        )

        # 执行测试
        lawfirm = self.service.create_lawfirm(data, admin_user)

        # 断言结果
        assert lawfirm.id is not None
        assert lawfirm.name == "测试律所"
        assert lawfirm.address == "测试地址"
        assert lawfirm.phone == "13800138000"

    def test_create_lawfirm_permission_denied(self):
        """测试创建律所权限不足"""
        # 准备测试数据
        normal_user = LawyerFactory(is_admin=False, is_superuser=False)
        data = LawFirmIn(name="测试律所")

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.create_lawfirm(data, normal_user)

        assert "无权限" in exc_info.value.message

    def test_create_lawfirm_duplicate_name(self):
        """测试创建重复名称的律所"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        LawFirmFactory(name="已存在的律所")
        data = LawFirmIn(name="已存在的律所")

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_lawfirm(data, admin_user)

        assert "已存在" in exc_info.value.message

    def test_get_lawfirm_success(self):
        """测试获取律所成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        user = LawyerFactory(law_firm=lawfirm)

        # 执行测试
        result = self.service.get_lawfirm(lawfirm.id, user)

        # 断言结果
        assert result.id == lawfirm.id
        assert result.name == lawfirm.name

    def test_get_lawfirm_not_found(self):
        """测试获取不存在的律所"""
        user = LawyerFactory(is_superuser=True)

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.get_lawfirm(999, user)

    def test_get_lawfirm_permission_denied(self):
        """测试获取律所权限不足"""
        # 准备测试数据
        lawfirm1 = LawFirmFactory()
        lawfirm2 = LawFirmFactory()
        user = LawyerFactory(law_firm=lawfirm1, is_superuser=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.get_lawfirm(lawfirm2.id, user)

    def test_list_lawfirms_superuser(self):
        """测试超级管理员列表查询"""
        # 准备测试数据
        LawFirmFactory.create_batch(5)
        superuser = LawyerFactory(is_superuser=True)

        # 执行测试
        result = self.service.list_lawfirms(user=superuser)

        # 断言结果：超级管理员可以看到所有律所（包括自己的）
        assert len(list(result)) >= 5

    def test_list_lawfirms_normal_user(self):
        """测试普通用户列表查询"""
        # 准备测试数据
        lawfirm1 = LawFirmFactory()
        lawfirm2 = LawFirmFactory()
        user = LawyerFactory(law_firm=lawfirm1, is_superuser=False)

        # 执行测试
        result = self.service.list_lawfirms(user=user)

        # 断言结果：只能看到自己所属的律所
        result_list = list(result)
        assert len(result_list) == 1
        assert result_list[0].id == lawfirm1.id

    def test_update_lawfirm_success(self):
        """测试更新律所成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory(name="旧名称")
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)
        data = LawFirmUpdateIn(name="新名称")

        # 执行测试
        result = self.service.update_lawfirm(lawfirm.id, data, admin_user)

        # 断言结果
        assert result.name == "新名称"

        # 验证数据库
        lawfirm.refresh_from_db()
        assert lawfirm.name == "新名称"

    def test_update_lawfirm_permission_denied(self):
        """测试更新律所权限不足"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        normal_user = LawyerFactory(law_firm=lawfirm, is_admin=False, is_superuser=False)
        data = LawFirmUpdateIn(name="新名称")

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.update_lawfirm(lawfirm.id, data, normal_user)

    def test_delete_lawfirm_success(self):
        """测试删除律所成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        superuser = LawyerFactory(is_superuser=True)

        # 执行测试
        self.service.delete_lawfirm(lawfirm.id, superuser)

        # 验证律所已删除
        from apps.organization.models import LawFirm

        assert not LawFirm.objects.filter(id=lawfirm.id).exists()

    def test_delete_lawfirm_with_lawyers(self):
        """测试删除有律师的律所"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        LawyerFactory(law_firm=lawfirm)
        superuser = LawyerFactory(is_superuser=True)

        # 断言抛出异常
        with pytest.raises(ConflictError) as exc_info:
            self.service.delete_lawfirm(lawfirm.id, superuser)

        assert "律师" in exc_info.value.message

    def test_delete_lawfirm_permission_denied(self):
        """测试删除律所权限不足"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True, is_superuser=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.delete_lawfirm(lawfirm.id, admin_user)
