"""LawyerImportService JSON 导入业务规则覆盖：新建/更新/团队合并/凭证挂载/异常聚计。"""

from __future__ import annotations

from typing import Any

import pytest

from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team
from apps.organization.models.team import TeamType
from apps.organization.services.lawyer_import_service import LawyerImportService


def _firm(name: str = "导入律所") -> LawFirm:
    return LawFirm.objects.create(name=name)


@pytest.mark.django_db
class TestImportFromJson:
    def test_create_new_lawyer_full_fields(self):
        firm = _firm("宏远所")
        result = LawyerImportService().import_from_json(
            [
                {
                    "username": "lawyer_a",
                    "password": "p",
                    "real_name": "张三",
                    "phone": "13800000000",
                    "license_no": "LICENSE-1",
                    "is_admin": True,
                    "is_active": True,
                    "law_firm": "宏远所",
                    "license_pdf": "licenses/a.pdf",
                    "lawyer_teams": ["诉讼一部"],
                    "biz_teams": ["市场组"],
                    "credentials": [{"site_name": "court_zxfw", "account": "a@x", "password": "s"}],
                }
            ],
            actor="admin",
        )
        assert result == (1, 0, [])
        lawyer = Lawyer.objects.get(username="lawyer_a")
        assert lawyer.real_name == "张三"
        assert lawyer.law_firm_id == firm.id
        assert lawyer.license_pdf == "licenses/a.pdf"
        assert lawyer.is_staff is True and lawyer.is_admin is True
        assert {t.name for t in lawyer.lawyer_teams.all()} == {"诉讼一部"}
        assert {t.name for t in lawyer.biz_teams.all()} == {"市场组"}
        cred = AccountCredential.objects.get(lawyer=lawyer)
        assert cred.site_name == "court_zxfw"
        # 团队挂载带律所维度（Team 唯一约束含 law_firm）
        assert Team.objects.get(name="诉讼一部").team_type == TeamType.LAWYER

    def test_update_existing_fills_only_empty_fields(self):
        firm = _firm()
        Lawyer.objects.create_user(
            username="lawyer_b", password="x", real_name="李四", license_no="OLD", law_firm=firm
        )
        result = LawyerImportService().import_from_json(
            [{"username": "lawyer_b", "real_name": "李四新", "license_no": "NEW", "phone": "13900000000"}],
            actor="admin",
        )
        assert result == (1, 0, [])
        lawyer = Lawyer.objects.get(username="lawyer_b")
        assert lawyer.phone == "13900000000"  # 空字段被补
        assert lawyer.license_no == "OLD"  # 已有字段不覆盖
        assert lawyer.real_name == "李四"  # 已有字段不覆盖

    def test_update_existing_merges_new_teams_only(self):
        firm = _firm()
        lawyer = Lawyer.objects.create_user(username="lawyer_c", password="x", law_firm=firm)
        team = Team.objects.create(name="既有组", team_type=TeamType.LAWYER, law_firm=firm)
        lawyer.lawyer_teams.add(team)

        LawyerImportService().import_from_json(
            [{"username": "lawyer_c", "lawyer_teams": ["既有组", "新增组"]}], actor="admin"
        )
        names = {t.name for t in lawyer.lawyer_teams.all()}
        assert names == {"既有组", "新增组"}  # 幂等合并不重复添加
        assert Team.objects.filter(name="新增组").count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_error_collected_and_batch_continues(self):
        # transaction=True：IntegrityError 被服务层捕获后，包裹式测试事务已
        # 中止（InFailedSqlTransaction），须走真事务隔离本用例
        _firm()
        # phone unique=True：第二条同号必触发唯一约束（前一条已成功入库）
        phone = "13800000001"
        good = {"username": "lawyer_ok", "real_name": "王五", "phone": phone}
        bad = {"username": "lawyer_bad", "real_name": "坏数据", "phone": phone}
        success, skipped, errors = LawyerImportService().import_from_json([good, bad], actor="admin")
        assert success == 1
        assert skipped == 0
        assert len(errors) == 1
        assert "[2]" in errors[0]
        assert "lawyer_bad" in errors[0]
        assert Lawyer.objects.filter(username="lawyer_ok").exists()
        assert not Lawyer.objects.filter(username="lawyer_bad").exists()

    def test_empty_list_returns_zero_counts(self):
        assert LawyerImportService().import_from_json([], actor="admin") == (0, 0, [])

    def test_lawyer_team_dict_entry_uses_declared_firm(self):
        """lawyer_teams 元素为 dict 时用其声明的 law_firm 建组（而非导入目标所在所）。"""
        firm_a = _firm("A所")
        _firm("B所")
        Lawyer.objects.create_user(username="lawyer_d", password="x", law_firm=firm_a)
        LawyerImportService().import_from_json(
            [{"username": "lawyer_d", "lawyer_teams": [{"name": "跨所组", "law_firm": "B所"}]}], actor="admin"
        )
        team = Team.objects.get(name="跨所组")
        assert team.law_firm.name == "B所"


@pytest.mark.django_db
class TestMergeCredentials:
    def test_existing_site_skipped_new_site_created(self):
        firm = _firm()
        lawyer = Lawyer.objects.create_user(username="lawyer_e", password="x", law_firm=firm)
        AccountCredential.objects.create(
            lawyer=lawyer, site_name="court_zxfw", url="", account="old@x", password=""
        )
        LawyerImportService().import_from_json(
            [
                {
                    "username": "lawyer_e",
                    "credentials": [
                        {"site_name": "court_zxfw", "account": "new@x"},  # 已有站点跳过
                        {"site_name": "gsxt", "account": "g@x"},
                    ],
                }
            ],
            actor="admin",
        )
        creds = {c.site_name: c.account for c in AccountCredential.objects.filter(lawyer=lawyer)}
        assert creds == {"court_zxfw": "old@x", "gsxt": "g@x"}

    def test_create_path_attaches_all_credentials(self):
        _firm()
        item: dict[str, Any] = {
            "username": "lawyer_f",
            "credentials": [
                {"site_name": "s1", "account": "a1"},
                {"site_name": "s2", "account": "a2"},
            ],
        }
        LawyerImportService().import_from_json([item], actor="admin")
        lawyer = Lawyer.objects.get(username="lawyer_f")
        assert {c.site_name for c in lawyer.credentials.all()} == {"s1", "s2"}
