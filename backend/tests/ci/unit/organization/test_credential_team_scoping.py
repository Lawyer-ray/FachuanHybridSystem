"""账号凭证可见性测试（安全审计：同所 → 同团队收紧）。

凭证是外部系统（一张网/威科/OA 等）的**个人账号口令**，可见面应为：
- 本人
- 同律师团队（lawyer_teams）成员
- 管理员（is_admin / is_superuser）

**不应**为「同律所」——原实现按 law_firm_id 放宽，导致任何律师可读全所同事的
账号密码。本文件固化收紧后的契约。
"""

from __future__ import annotations

import pytest

from apps.core.exceptions import PermissionDenied
from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team, TeamType
from apps.organization.services.credential.account_credential_service import AccountCredentialService
from apps.testing.factories import LawyerFactory


def _make_credential(owner: Lawyer, *, site: str = "court_zxfw") -> AccountCredential:
    return AccountCredential.objects.create(
        lawyer=owner,
        site_name=site,
        account=f"acct-{owner.pk}",
        password="secret",  # pragma: allowlist secret —— 测试哑密码
    )


@pytest.mark.django_db
class TestCredentialReadScoping:
    def test_own_credential_readable(self) -> None:
        firm = LawFirm.objects.create(name="firm-c1")
        me = LawyerFactory(law_firm=firm)
        cred = _make_credential(me)

        got = AccountCredentialService().get_credential(cred.id, user=me)
        assert got.id == cred.id

    def test_same_team_credential_readable(self) -> None:
        """同团队同事的凭证可读。"""
        firm = LawFirm.objects.create(name="firm-c2")
        team = Team.objects.create(name="team-c2", team_type=TeamType.LAWYER, law_firm=firm)
        me = LawyerFactory(law_firm=firm)
        teammate = LawyerFactory(law_firm=firm)
        me.lawyer_teams.add(team)
        teammate.lawyer_teams.add(team)
        cred = _make_credential(teammate)

        got = AccountCredentialService().get_credential(cred.id, user=me)
        assert got.id == cred.id

    def test_other_team_same_firm_not_readable(self) -> None:
        """同律所但不同团队：不可读（本次收紧的核心）。"""
        firm = LawFirm.objects.create(name="firm-c3")
        team_a = Team.objects.create(name="team-c3-a", team_type=TeamType.LAWYER, law_firm=firm)
        team_b = Team.objects.create(name="team-c3-b", team_type=TeamType.LAWYER, law_firm=firm)
        me = LawyerFactory(law_firm=firm)
        other = LawyerFactory(law_firm=firm)
        me.lawyer_teams.add(team_a)
        other.lawyer_teams.add(team_b)
        cred = _make_credential(other)

        with pytest.raises(PermissionDenied):
            AccountCredentialService().get_credential(cred.id, user=me)

    def test_no_team_lawyer_sees_only_self(self) -> None:
        """无团队的律师：只能看自己，看不到同所其他人。"""
        firm = LawFirm.objects.create(name="firm-c4")
        loner = LawyerFactory(law_firm=firm)
        other = LawyerFactory(law_firm=firm)
        cred_other = _make_credential(other)

        with pytest.raises(PermissionDenied):
            AccountCredentialService().get_credential(cred_other.id, user=loner)

    def test_admin_sees_any_firm_credential(self) -> None:
        """管理员可读（保持原有放宽）。"""
        firm = LawFirm.objects.create(name="firm-c5")
        admin_user = LawyerFactory(law_firm=firm, is_admin=True)
        other = LawyerFactory(law_firm=firm)
        cred = _make_credential(other)

        got = AccountCredentialService().get_credential(cred.id, user=admin_user)
        assert got.id == cred.id


@pytest.mark.django_db
class TestCredentialListScoping:
    def test_list_excludes_other_team_credentials(self) -> None:
        """列表口径同步收紧：不含其他团队同事的凭证。"""
        firm = LawFirm.objects.create(name="firm-l1")
        team_a = Team.objects.create(name="team-l1-a", team_type=TeamType.LAWYER, law_firm=firm)
        team_b = Team.objects.create(name="team-l1-b", team_type=TeamType.LAWYER, law_firm=firm)
        me = LawyerFactory(law_firm=firm)
        teammate = LawyerFactory(law_firm=firm)
        other_team = LawyerFactory(law_firm=firm)
        me.lawyer_teams.add(team_a)
        teammate.lawyer_teams.add(team_a)
        other_team.lawyer_teams.add(team_b)

        cred_me = _make_credential(me)
        cred_teammate = _make_credential(teammate)
        cred_other = _make_credential(other_team)

        svc = AccountCredentialService()
        visible_ids = set(svc.list_credentials(user=me).values_list("id", flat=True))

        assert cred_me.id in visible_ids
        assert cred_teammate.id in visible_ids
        assert cred_other.id not in visible_ids

    def test_list_for_admin_returns_all(self) -> None:
        firm = LawFirm.objects.create(name="firm-l2")
        admin_user = LawyerFactory(law_firm=firm, is_admin=True)
        other = LawyerFactory(law_firm=firm)
        cred = _make_credential(other)

        visible_ids = set(AccountCredentialService().list_credentials(user=admin_user).values_list("id", flat=True))
        assert cred.id in visible_ids

    def test_list_without_user_returns_nothing(self) -> None:
        firm = LawFirm.objects.create(name="firm-l3")
        other = LawyerFactory(law_firm=firm)
        _make_credential(other)

        assert not AccountCredentialService().list_credentials(user=None).exists()
