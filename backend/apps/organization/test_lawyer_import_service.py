from __future__ import annotations

import pytest

from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team
from apps.organization.models.team import TeamType
from apps.organization.services.lawyer_import_service import LawyerImportService


@pytest.mark.django_db
def test_import_updates_only_missing_fields_for_existing_lawyer() -> None:
    old_firm = LawFirm.objects.create(name="旧律所")
    existing = Lawyer.objects.create_user(
        username="existing-lawyer",
        password="secret",  # pragma: allowlist secret
        real_name="保留原姓名",
        phone=None,
        license_no="",
        id_card="",
        law_firm=None,
    )
    old_lawyer_team = Team.objects.create(name="旧律师团队", team_type=TeamType.LAWYER, law_firm=old_firm)
    old_biz_team = Team.objects.create(name="旧业务团队", team_type=TeamType.BIZ, law_firm=old_firm)
    existing.lawyer_teams.add(old_lawyer_team)
    existing.biz_teams.add(old_biz_team)
    AccountCredential.objects.create(
        lawyer=existing,
        site_name="court_zxfw",
        url="https://old.example.com",
        account="old-account",
        password="old-password",  # pragma: allowlist secret
    )

    payload = [
        {
            "username": "existing-lawyer",
            "real_name": "不应覆盖",
            "phone": "13800000000",
            "license_no": "LIC-001",
            "id_card": "ID-001",
            "law_firm": "新律所",
            "lawyer_teams": [{"name": "新律师团队", "law_firm": "新律所"}],
            "biz_teams": ["旧业务团队", "新业务团队"],
            "credentials": [
                {  # pragma: allowlist secret
                    "site_name": "court_zxfw",
                    "url": "https://dup.example.com",
                    "account": "dup",
                    "password": "dup",  # pragma: allowlist secret
                },
                {  # pragma: allowlist secret
                    "site_name": "wkxx",
                    "url": "https://wkxx.example.com",
                    "account": "wk-account",
                    "password": "wk",  # pragma: allowlist secret
                },
            ],
        }
    ]

    success, skipped, errors = LawyerImportService().import_from_json(payload, actor="pytest")

    assert success == 1
    assert skipped == 0
    assert errors == []

    existing.refresh_from_db()
    assert existing.real_name == "保留原姓名"
    assert existing.phone == "13800000000"
    assert existing.license_no == "LIC-001"
    assert existing.id_card == "ID-001"
    assert existing.law_firm is not None
    assert existing.law_firm.name == "新律所"
    assert set(existing.lawyer_teams.values_list("name", flat=True)) == {"旧律师团队", "新律师团队"}
    assert set(existing.biz_teams.values_list("name", flat=True)) == {"旧业务团队", "新业务团队"}
    assert set(existing.credentials.values_list("site_name", flat=True)) == {"court_zxfw", "wkxx"}


@pytest.mark.django_db
def test_import_creates_new_lawyer_with_related_entities() -> None:
    payload = [
        {
            "username": "new-lawyer",
            "real_name": "新律师",
            "phone": "13900000000",
            "license_no": "LIC-NEW",
            "id_card": "ID-NEW",
            "law_firm": "导入律所",
            "is_admin": True,
            "is_active": True,
            "lawyer_teams": [{"name": "导入律师团队", "law_firm": "导入律所"}],
            "biz_teams": ["导入业务团队"],
            "credentials": [
                {  # pragma: allowlist secret
                    "site_name": "wkxx",
                    "url": "https://wkxx.example.com",
                    "account": "wk-new",
                    "password": "wk-pass",  # pragma: allowlist secret
                },
            ],
        }
    ]

    success, skipped, errors = LawyerImportService().import_from_json(payload, actor="pytest")

    assert success == 1
    assert skipped == 0
    assert errors == []

    lawyer = Lawyer.objects.get(username="new-lawyer")
    assert lawyer.real_name == "新律师"
    assert lawyer.law_firm is not None
    assert lawyer.law_firm.name == "导入律所"
    assert lawyer.is_admin is True
    assert lawyer.is_staff is True
    assert lawyer.password != ""
    assert list(lawyer.lawyer_teams.values_list("name", flat=True)) == ["导入律师团队"]
    assert list(lawyer.biz_teams.values_list("name", flat=True)) == ["导入业务团队"]
    credential = AccountCredential.objects.get(lawyer=lawyer, site_name="wkxx")
    assert credential.account == "wk-new"
