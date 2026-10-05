"""CaseContactService 深度覆盖：聚合搜索（分组/去重/取最新）与成功读取路径。

既有 targeted 测试只断言「不抛错/是 list」，本文件用真实数据驱动
search_contacts_public 的完整装配逻辑与 get_contact/list 的成功分支。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.cases.models import Case, SupervisingAuthority
from apps.contacts.models import CaseContact
from apps.contacts.services.contact_service import CaseContactService
from apps.core.models.enums import ContactRole


def _admin_user() -> Any:
    class _U:
        is_staff = True
        is_superuser = True

    return _U()


@pytest.mark.django_db
class TestSearchContactsPublicDeep:
    def _setup_data(self) -> None:
        """两案三联系人：张法官在两案出现（occurrence=2）、李书记一案、旧电话被最新覆盖。"""
        self.case_a = Case.objects.create(name="深测案件甲")
        self.case_b = Case.objects.create(name="深测案件乙")
        self.court = SupervisingAuthority.objects.create(case=self.case_a, name="测试法院")
        self.judge = CaseContact.objects.create(
            case=self.case_a, authority=self.court, name="张法官", role=ContactRole.JUDGE, phone="旧电话"
        )
        CaseContact.objects.create(
            case=self.case_b, authority=self.court, name="张法官", role=ContactRole.JUDGE, phone="新电话"
        )
        CaseContact.objects.create(
            case=self.case_a, authority=self.court, name="李书记", role=ContactRole.OTHER, address="某路 1 号"
        )
        # 把「张法官·案A·旧电话」的 updated_at 压到更早，验证「每组取最新」取到新电话
        # （auto_now 会在 save() 时覆盖回拨值，必须走 queryset.update 绕过）
        CaseContact.objects.filter(pk=self.judge.pk).update(updated_at=timezone.now() - timezone.timedelta(days=30))

    def test_grouping_occurrence_and_latest_selection(self) -> None:
        self._setup_data()
        service = CaseContactService()
        with patch.object(service, "ensure_admin"):
            results = service.search_contacts_public(q="张", user=_admin_user())

        assert len(results) == 1
        row = results[0]
        assert row["name"] == "张法官"
        assert row["occurrence_count"] == 2
        assert row["phone"] == "新电话"  # 最新一条胜出
        assert set(row["case_ids"]) == {self.case_a.id, self.case_b.id}
        assert row["authority_name"] == "测试法院"
        assert row["role_display"] is not None

    def test_filters_court_and_role(self) -> None:
        self._setup_data()
        service = CaseContactService()
        with patch.object(service, "ensure_admin"):
            only_clerk = service.search_contacts_public(court="测试法院", role=ContactRole.OTHER, user=_admin_user())
            other_court = service.search_contacts_public(court="不存在法院", user=_admin_user())

        assert [r["name"] for r in only_clerk] == ["李书记"]
        assert other_court == []

    def test_no_authority_grouped_with_empty_name(self) -> None:
        """authority 为 SET_NULL：无机关联系人的 authority_name 装配为空串而非 None。"""
        case = Case.objects.create(name="无机关案")
        CaseContact.objects.create(case=case, authority=None, name="王同志", role=ContactRole.OTHER)
        service = CaseContactService()
        with patch.object(service, "ensure_admin"):
            results = service.search_contacts_public(q="王", user=_admin_user())
        assert results[0]["authority_name"] is None or results[0]["authority_name"] == ""
        assert results[0]["phone"] == ""  # 未填电话的字段默认空串（模型 blank default）

    def test_limit_truncates_groups(self) -> None:
        case = Case.objects.create(name="限量案")
        for i in range(5):
            CaseContact.objects.create(case=case, name=f"联系人{i}", role=ContactRole.OTHER)
        service = CaseContactService()
        with patch.object(service, "ensure_admin"):
            results = service.search_contacts_public(limit=2, user=_admin_user())
        assert len(results) == 2


@pytest.mark.django_db
class TestReadPaths:
    def test_get_contact_success_and_not_found(self) -> None:
        case = Case.objects.create(name="读取案")
        contact = CaseContact.objects.create(case=case, name="赵联络", role=ContactRole.OTHER)
        service = CaseContactService()

        with patch.object(service, "ensure_admin"):
            got = service.get_contact(contact_id=contact.id, user=_admin_user())
            assert got.pk == contact.pk
            assert got.name == "赵联络"
            with pytest.raises(Exception) as exc_info:
                service.get_contact(contact_id=contact.id + 99999, user=_admin_user())
        assert getattr(exc_info.value, "code", None) == "CONTACT_NOT_FOUND"

    def test_list_contacts_filters_stage(self) -> None:
        case = Case.objects.create(name="阶段案")
        CaseContact.objects.create(case=case, name="一审员", role=ContactRole.OTHER, stage="first_instance")
        CaseContact.objects.create(case=case, name="二审员", role=ContactRole.OTHER, stage="second_instance")
        service = CaseContactService()

        with patch.object(service, "ensure_admin"):
            qs = service.list_contacts(case_id=case.id, stage="first_instance", user=_admin_user())
        assert [c.name for c in qs] == ["一审员"]
