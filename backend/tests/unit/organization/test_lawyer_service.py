"""
律师服务单元测试
"""

from unittest.mock import Mock

import pytest

from apps.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationException
from apps.organization.schemas import LawyerCreateIn, LawyerUpdateIn
from apps.organization.services import LawyerService
from tests.factories import LawFirmFactory, LawyerFactory, TeamFactory


@pytest.mark.django_db
class TestLawyerService:
    """律师服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = LawyerService()

    def test_create_lawyer_success(self):
        """测试创建律师成功"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        lawfirm = LawFirmFactory()
        data = LawyerCreateIn(
            username="testlawyer",
            password="testpass123",
            real_name="测试律师",
            phone="13800138001",
            law_firm_id=lawfirm.id,  # type: ignore[attr-defined]
            is_admin=False,
        )

        # 执行测试
        lawyer = self.service.create_lawyer(data, admin_user)  # type: ignore[arg-type]

        # 断言结果
        assert lawyer.id is not None
        assert lawyer.username == "testlawyer"
        assert lawyer.real_name == "测试律师"
        assert lawyer.law_firm_id == lawfirm.id  # type: ignore[attr-defined]

    def test_create_lawyer_permission_denied(self):
        """测试创建律师权限不足"""
        # 准备测试数据
        normal_user = LawyerFactory(is_admin=False, is_superuser=False)
        data = LawyerCreateIn(username="testlawyer", password="testpass123")

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.create_lawyer(data, normal_user)  # type: ignore[arg-type]

        assert "无权限" in exc_info.value.message  # type: ignore[operator]

    def test_create_lawyer_duplicate_username(self):
        """测试创建重复用户名的律师"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        LawyerFactory(username="existing")
        data = LawyerCreateIn(username="existing", password="testpass123")

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_lawyer(data, admin_user)  # type: ignore[arg-type]

        assert "用户名" in exc_info.value.message  # type: ignore[operator]

    def test_create_lawyer_duplicate_phone(self):
        """测试创建重复手机号的律师"""
        # 准备测试数据
        admin_user = LawyerFactory(is_admin=True)
        LawyerFactory(phone="13800138000")
        data = LawyerCreateIn(username="newlawyer", password="testpass123", phone="13800138000")

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_lawyer(data, admin_user)  # type: ignore[arg-type]

        assert "手机号" in exc_info.value.message  # type: ignore[operator]

    def test_get_lawyer_success(self):
        """测试获取律师成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm)
        user = LawyerFactory(law_firm=lawfirm)

        # 执行测试
        result = self.service.get_lawyer(lawyer.id, user)  # type: ignore

        # 断言结果
        assert result.id == lawyer.id  # type: ignore[attr-defined]
        assert result.username == lawyer.username

    def test_get_lawyer_not_found(self):
        """测试获取不存在的律师"""
        user = LawyerFactory(is_superuser=True)

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.get_lawyer(999, user)  # type: ignore[arg-type]

    def test_get_lawyer_permission_denied(self):
        """测试获取律师权限不足"""
        # 准备测试数据
        lawfirm1 = LawFirmFactory()
        lawfirm2 = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm1)
        user = LawyerFactory(law_firm=lawfirm2, is_superuser=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.get_lawyer(lawyer.id, user)  # type: ignore

    def test_list_lawyers_superuser(self):
        """测试超级管理员列表查询"""
        # 准备测试数据
        LawyerFactory.create_batch(5)
        superuser = LawyerFactory(is_superuser=True)

        # 执行测试
        result = self.service.list_lawyers(user=superuser)  # type: ignore[arg-type]

        # 断言结果：超级管理员可以看到所有律师（包括自己）
        assert len(list(result)) == 6

    def test_list_lawyers_normal_user(self):
        """测试普通用户列表查询"""
        # 准备测试数据
        lawfirm1 = LawFirmFactory()
        lawfirm2 = LawFirmFactory()
        LawyerFactory.create_batch(3, law_firm=lawfirm1)
        LawyerFactory.create_batch(2, law_firm=lawfirm2)
        user = LawyerFactory(law_firm=lawfirm1, is_superuser=False)

        # 执行测试
        result = self.service.list_lawyers(user=user)  # type: ignore[arg-type]

        # 断言结果：只能看到同律所的律师（包括自己）
        assert len(list(result)) == 4

    def test_update_lawyer_success(self):
        """测试更新律师成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm, real_name="旧名称")
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)
        data = LawyerUpdateIn(real_name="新名称")

        # 执行测试
        result = self.service.update_lawyer(lawyer.id, data, admin_user)  # type: ignore

        # 断言结果
        assert result.real_name == "新名称"

        # 验证数据库
        lawyer.refresh_from_db()  # type: ignore[attr-defined]
        assert lawyer.real_name == "新名称"

    def test_update_lawyer_self(self):
        """测试律师更新自己的信息"""
        # 准备测试数据
        lawyer = LawyerFactory(real_name="旧名称")
        data = LawyerUpdateIn(real_name="新名称")

        # 执行测试
        result = self.service.update_lawyer(lawyer.id, data, lawyer)  # type: ignore

        # 断言结果
        assert result.real_name == "新名称"

    def test_update_lawyer_permission_denied(self):
        """测试更新律师权限不足"""
        # 准备测试数据
        lawfirm1 = LawFirmFactory()
        lawfirm2 = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm1)
        user = LawyerFactory(law_firm=lawfirm2, is_admin=False, is_superuser=False)
        data = LawyerUpdateIn(real_name="新名称")

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.update_lawyer(lawyer.id, data, user)  # type: ignore

    def test_delete_lawyer_success(self):
        """测试删除律师成功"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm)
        admin_user = LawyerFactory(law_firm=lawfirm, is_admin=True)

        # 执行测试
        self.service.delete_lawyer(lawyer.id, admin_user)  # type: ignore

        # 验证律师已删除
        from apps.organization.models import Lawyer

        assert not Lawyer.objects.filter(id=lawyer.id).exists()  # type: ignore[attr-defined]

    def test_delete_lawyer_permission_denied(self):
        """测试删除律师权限不足"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        lawyer = LawyerFactory(law_firm=lawfirm)
        normal_user = LawyerFactory(law_firm=lawfirm, is_admin=False, is_superuser=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.delete_lawyer(lawyer.id, normal_user)  # type: ignore

    def test_get_team_member_ids(self):
        """测试获取团队成员 ID"""
        # 准备测试数据
        lawfirm = LawFirmFactory()
        team = TeamFactory(law_firm=lawfirm, team_type="lawyer")
        lawyer1 = LawyerFactory(law_firm=lawfirm)
        lawyer2 = LawyerFactory(law_firm=lawfirm)
        lawyer1.lawyer_teams.add(team)  # type: ignore[attr-defined]
        lawyer2.lawyer_teams.add(team)  # type: ignore[attr-defined]

        # 执行测试
        member_ids = self.service.get_team_member_ids(lawyer1)  # type: ignore[arg-type]

        # 断言结果
        assert lawyer1.id in member_ids  # type: ignore[attr-defined]
        assert lawyer2.id in member_ids  # type: ignore[attr-defined]
