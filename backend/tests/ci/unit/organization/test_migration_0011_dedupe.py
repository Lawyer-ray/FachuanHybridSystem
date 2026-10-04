"""organization 0011 迁移去重函数的单元测试。

去重函数接收的 apps 为迁移历史 registry；由于 0010→0011 之间这些模型没有
字段形状变化（仅加约束），用真实 apps registry 验证逻辑等价有效。

测试内先 DROP 唯一约束构造出重复行（模拟迁移前的脏数据），跑完去重后再
重新 ADD 约束——约束能加回即证明数据已被清洗干净。DDL 在 pytest-django
事务内执行，测试结束随事务回滚，不会污染复用的测试库。
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps as real_apps
from django.db import connection
from django.utils import timezone

from apps.legal_research.models import CaseDownloadTask
from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team
from apps.organization.models.team import TeamType

_migration_0011 = import_module(
    "apps.organization.migrations.0011_accountcredential_uniq_credential_lawyer_site_account_and_more"
)
dedupe_account_credentials = _migration_0011.dedupe_account_credentials
dedupe_teams = _migration_0011.dedupe_teams

_CREDENTIAL_CONSTRAINT = "uniq_credential_lawyer_site_account"
_TEAM_CONSTRAINT = "uniq_team_firm_type_name"


def _drop_credential_constraint() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE organization_accountcredential DROP CONSTRAINT IF EXISTS {_CREDENTIAL_CONSTRAINT}")


def _drop_team_constraint() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE organization_team DROP CONSTRAINT IF EXISTS {_TEAM_CONSTRAINT}")


def _add_team_constraint() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE organization_team ADD CONSTRAINT {_TEAM_CONSTRAINT} UNIQUE (law_firm_id, team_type, name)"
        )


@pytest.fixture
def lawyer(db):
    firm = LawFirm.objects.create(name="去重测试律所")
    return Lawyer.objects.create_user(username="dedupe_lawyer", password="x", law_firm=firm)


class TestDedupeAccountCredentials:
    def test_keeps_latest_login_and_repoints_protected_fk(self, lawyer):
        _drop_credential_constraint()
        old = AccountCredential.objects.create(lawyer=lawyer, site_name="威科先行", account="acc", password="p")
        keeper = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="威科先行",
            account="acc",
            password="p",
            last_login_success_at=timezone.now(),
        )
        # PROTECT 外键指向将被删除的重复行
        task = CaseDownloadTask.objects.create(credential=old, case_numbers="(2026)京01民初1号")

        dedupe_account_credentials(real_apps, None)

        assert not AccountCredential.objects.filter(pk=old.pk).exists()
        assert AccountCredential.objects.filter(pk=keeper.pk).exists()
        task.refresh_from_db()
        assert task.credential_id == keeper.pk

    def test_keeps_max_id_when_login_times_equal(self, lawyer):
        _drop_credential_constraint()
        stale_1 = AccountCredential.objects.create(lawyer=lawyer, site_name="站点A", account="acc", password="p")
        stale_2 = AccountCredential.objects.create(lawyer=lawyer, site_name="站点A", account="acc", password="p")

        dedupe_account_credentials(real_apps, None)

        assert AccountCredential.objects.filter(lawyer=lawyer, site_name="站点A").count() == 1
        assert AccountCredential.objects.filter(pk=max(stale_1.pk, stale_2.pk)).exists()

    def test_different_keys_not_touched(self, lawyer):
        _drop_credential_constraint()
        a = AccountCredential.objects.create(lawyer=lawyer, site_name="站点A", account="acc", password="p")
        b = AccountCredential.objects.create(lawyer=lawyer, site_name="站点B", account="acc", password="p")

        dedupe_account_credentials(real_apps, None)

        assert AccountCredential.objects.filter(pk__in=[a.pk, b.pk]).count() == 2


class TestDedupeTeams:
    # transaction=True：迁移本身 atomic=False（去重 UPDATE 的延迟触发器事件
    # 会挡住同事务 ALTER TABLE），这里让 dedupe_teams 内部的 atomic 真实提交，
    # 随后 _add_team_constraint 才能执行——同时验证迁移的提交顺序假设。
    # 注意：共享的 lawyer fixture 是非事务 db 模式，与本类事务模式不兼容，
    # 数据在用例内自建。
    @pytest.mark.django_db(transaction=True)
    def test_keeps_min_id_and_migrates_membership(self):
        _drop_team_constraint()
        firm = LawFirm.objects.create(name="去重测试律所")
        lawyer = Lawyer.objects.create_user(username="dedupe_lawyer", password="x", law_firm=firm)
        # 迁移保留 id 最小者：先建的行会被保留，后建的重复行被删除
        keeper = Team.objects.create(law_firm=firm, team_type=TeamType.LAWYER, name="刑辩组")
        dup = Team.objects.create(law_firm=firm, team_type=TeamType.LAWYER, name="刑辩组")
        # 律师只挂在重复行上
        lawyer.lawyer_teams.add(dup)

        dedupe_teams(real_apps, None)

        assert not Team.objects.filter(pk=dup.pk).exists()
        assert Team.objects.filter(pk=keeper.pk).exists()
        assert list(lawyer.lawyer_teams.values_list("id", flat=True)) == [keeper.pk]
        # 去重后数据必须满足唯一约束（加不回去说明仍有重复）
        _add_team_constraint()

    @pytest.mark.django_db(transaction=True)
    def test_membership_to_keeper_preserved(self):
        _drop_team_constraint()
        firm = LawFirm.objects.create(name="去重测试律所2")
        lawyer = Lawyer.objects.create_user(username="dedupe_lawyer_b", password="x", law_firm=firm)
        keeper = Team.objects.create(law_firm=firm, team_type=TeamType.BIZ, name="市场组")
        dup = Team.objects.create(law_firm=firm, team_type=TeamType.BIZ, name="市场组")
        lawyer.biz_teams.add(keeper)
        other = Lawyer.objects.create_user(username="dedupe_lawyer_2b", password="x", law_firm=firm)
        other.biz_teams.add(dup)

        dedupe_teams(real_apps, None)

        assert list(lawyer.biz_teams.values_list("id", flat=True)) == [keeper.pk]
        assert list(other.biz_teams.values_list("id", flat=True)) == [keeper.pk]
        _add_team_constraint()
