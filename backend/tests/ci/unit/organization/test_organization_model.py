"""Organization Model 测试 - Lawyer, LawFirm, Team, AccountCredential"""

from __future__ import annotations

from typing import Any

import pytest

from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team
from apps.organization.models.team import TeamType


@pytest.mark.django_db
class TestLawFirmModel:
    """LawFirm 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回律所名称"""
        firm = LawFirm.objects.create(name="测试律所")
        assert str(firm) == "测试律所"

    def test_create_law_firm(self) -> None:
        """创建律所"""
        firm = LawFirm.objects.create(
            name="完整律所",
            phone="010-12345678",
            social_credit_code="91110000MA01XXXXX",
        )
        assert firm.name == "完整律所"
        assert firm.phone == "010-12345678"
        assert firm.social_credit_code == "91110000MA01XXXXX"


@pytest.mark.django_db
class TestLawyerModel:
    """Lawyer 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回律师姓名"""
        firm = LawFirm.objects.create(name="律师测试律所")
        lawyer = Lawyer.objects.create_user(
            username="test_lawyer", real_name="测试律师", law_firm=firm
        )
        assert str(lawyer) == "测试律师"

    def test_create_lawyer(self) -> None:
        """创建律师"""
        firm = LawFirm.objects.create(name="创建律师律所")
        lawyer = Lawyer.objects.create_user(
            username="create_lawyer",
            real_name="创建律师",
            phone="12000000000",
            law_firm=firm,
        )
        assert lawyer.username == "create_lawyer"
        assert lawyer.real_name == "创建律师"
        assert lawyer.phone == "12000000000"

    def test_lawyer_is_admin(self) -> None:
        """律师管理员标记"""
        firm = LawFirm.objects.create(name="管理员律师律所")
        lawyer = Lawyer.objects.create_user(
            username="admin_lawyer", real_name="管理员律师", is_admin=True, law_firm=firm
        )
        assert lawyer.is_admin is True

    def test_lawyer_with_teams(self) -> None:
        """律师关联团队"""
        firm = LawFirm.objects.create(name="团队律师律所")
        lawyer = Lawyer.objects.create_user(
            username="team_lawyer", real_name="团队律师", law_firm=firm
        )
        team = Team.objects.create(name="律师团队", team_type=TeamType.LAWYER, law_firm=firm)
        lawyer.lawyer_teams.add(team)
        assert lawyer.lawyer_teams.count() == 1


@pytest.mark.django_db
class TestTeamModel:
    """Team 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回团队名称（包含律所和类型）"""
        firm = LawFirm.objects.create(name="团队测试律所")
        team = Team.objects.create(name="测试团队", team_type=TeamType.LAWYER, law_firm=firm)
        # Team.__str__ 返回 "律所-类型-名称" 格式
        assert "测试团队" in str(team)

    def test_team_type_choices(self) -> None:
        """团队类型选项"""
        assert TeamType.LAWYER == "lawyer"
        assert TeamType.BIZ == "biz"

    def test_create_lawyer_team(self) -> None:
        """创建律师团队"""
        firm = LawFirm.objects.create(name="律师团队律所")
        team = Team.objects.create(name="律师团队", team_type=TeamType.LAWYER, law_firm=firm)
        assert team.team_type == TeamType.LAWYER

    def test_create_biz_team(self) -> None:
        """创建业务团队"""
        firm = LawFirm.objects.create(name="业务团队律所")
        team = Team.objects.create(name="业务团队", team_type=TeamType.BIZ, law_firm=firm)
        assert team.team_type == TeamType.BIZ


@pytest.mark.django_db
class TestAccountCredentialModel:
    """AccountCredential 模型测试"""

    def test_create_credential(self) -> None:
        """创建账号凭证"""
        firm = LawFirm.objects.create(name="凭证测试律所")
        lawyer = Lawyer.objects.create_user(username="cred_lawyer", real_name="凭证律师", law_firm=firm)
        cred = AccountCredential.objects.create(
            lawyer=lawyer, site_name="test_site", account="test_account", password="test_pass"  # allowlist secret
        )
        assert cred.site_name == "test_site"
        assert cred.account == "test_account"

    def test_success_rate(self) -> None:
        """成功率计算"""
        firm = LawFirm.objects.create(name="成功率律所")
        lawyer = Lawyer.objects.create_user(username="rate_lawyer", real_name="成功率律师", law_firm=firm)
        cred = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="rate_site",
            account="rate_account",
            password="test_pass",  # allowlist secret
            login_success_count=8,
            login_failure_count=2,
        )
        assert cred.success_rate == 0.8

    def test_success_rate_zero_total(self) -> None:
        """零总次数时成功率应为 0"""
        firm = LawFirm.objects.create(name="零次律所")
        lawyer = Lawyer.objects.create_user(username="zero_lawyer", real_name="零次律师", law_firm=firm)
        cred = AccountCredential.objects.create(
            lawyer=lawyer, site_name="zero_site", account="zero_account", password="test_pass"  # allowlist secret
        )
        assert cred.success_rate == 0.0
