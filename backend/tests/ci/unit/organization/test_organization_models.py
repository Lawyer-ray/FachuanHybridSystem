"""organization app Model 单元测试

覆盖 LawFirm, Team, AccountCredential 的 property、__str__、choices。
"""

import pytest

from apps.organization.models.credential import AccountCredential
from apps.organization.models.law_firm import LawFirm
from apps.organization.models.lawyer import Lawyer
from apps.organization.models.team import Team, TeamType


# ============================================================
# LawFirm
# ============================================================


@pytest.mark.django_db
class TestLawFirm:
    def test_str(self):
        firm = LawFirm.objects.create(name="测试律师事务所")
        assert str(firm) == "测试律师事务所"

    def test_create_with_optional_fields(self):
        firm = LawFirm.objects.create(
            name="完整律所",
            address="北京市朝阳区",
            phone="010-12345678",
            social_credit_code="91110000MA12345678",
            bank_name="中国银行",
            bank_account="6222000000001234",
        )
        assert firm.address == "北京市朝阳区"
        assert firm.phone == "010-12345678"
        assert firm.social_credit_code == "91110000MA12345678"
        assert firm.bank_name == "中国银行"
        assert firm.bank_account == "6222000000001234"


# ============================================================
# Team
# ============================================================


@pytest.mark.django_db
class TestTeam:
    def test_str(self):
        firm = LawFirm.objects.create(name="测试律所")
        team = Team.objects.create(
            name="民事团队",
            team_type=TeamType.LAWYER,
            law_firm=firm,
        )
        result = str(team)
        assert "测试律所" in result
        assert "律师团队" in result
        assert "民事团队" in result

    def test_team_type_choices(self):
        assert TeamType.LAWYER.value == "lawyer"
        assert TeamType.BIZ.value == "biz"

    def test_biz_team_str(self):
        firm = LawFirm.objects.create(name="甲律所")
        team = Team.objects.create(name="行政组", team_type=TeamType.BIZ, law_firm=firm)
        result = str(team)
        assert "业务团队" in result


# ============================================================
# AccountCredential
# ============================================================


@pytest.mark.django_db
class TestAccountCredential:
    def test_str(self):
        firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create_user(
            username="cred_user",
            password="testpass",
            law_firm=firm,
        )
        cred = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="一张网",
            account="user@example.com",
            password="secret",
        )
        assert str(cred) == "一张网 - user@example.com"

    def test_success_rate_zero_attempts(self):
        cred = AccountCredential(login_success_count=0, login_failure_count=0)
        assert cred.success_rate == 0.0

    def test_success_rate_with_attempts(self):
        cred = AccountCredential(login_success_count=8, login_failure_count=2)
        assert cred.success_rate == 0.8

    def test_success_rate_all_success(self):
        cred = AccountCredential(login_success_count=10, login_failure_count=0)
        assert cred.success_rate == 1.0

    def test_success_rate_all_failure(self):
        cred = AccountCredential(login_success_count=0, login_failure_count=5)
        assert cred.success_rate == 0.0


# ============================================================
# Lawyer
# ============================================================


@pytest.mark.django_db
class TestLawyer:
    def test_str_with_real_name(self):
        firm = LawFirm.objects.create(name="律所")
        lawyer = Lawyer.objects.create_user(
            username="test_lawyer",
            password="pass",
            real_name="张三",
            law_firm=firm,
        )
        assert str(lawyer) == "张三"

    def test_str_without_real_name(self):
        firm = LawFirm.objects.create(name="律所")
        lawyer = Lawyer.objects.create_user(
            username="no_name_user",
            password="pass",
            law_firm=firm,
        )
        assert str(lawyer) == "no_name_user"

    def test_email_none_not_empty_string(self):
        """LawyerManager 应将 email=None 保持为 NULL"""
        firm = LawFirm.objects.create(name="律所")
        lawyer = Lawyer.objects.create_user(
            username="null_email_user",
            password="pass",
            email=None,
            law_firm=firm,
        )
        assert lawyer.email is None
