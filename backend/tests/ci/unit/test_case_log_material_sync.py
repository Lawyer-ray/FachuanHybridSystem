from __future__ import annotations

import json

import pytest
from django import forms
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.admin.caselog_admin import CaseLogAdmin, CaseLogAttachmentInlineForm
from apps.cases.models import (
    Case,
    CaseLog,
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialSide,
    CaseMaterialType,
    CaseParty,
    SupervisingAuthority,
)
from apps.cases.services.material.case_material_service import CaseMaterialService
from apps.client.models import Client
from apps.core.exceptions import ValidationException


class StubCaseService:
    def get_case(self, case_id: int, **_kwargs: object) -> Case:
        return Case.objects.get(pk=case_id)


def _service() -> CaseMaterialService:
    return CaseMaterialService(case_service=StubCaseService())  # type: ignore[arg-type]


def _user():
    return get_user_model().objects.create_user(username="case-material-sync-user")


def _case_bundle():
    user = _user()
    case = Case.objects.create(name="日志材料同步测试", case_type="civil")
    our_client = Client.objects.create(name="我方当事人", is_our_client=True)
    opponent_client = Client.objects.create(name="对方当事人", is_our_client=False)
    our_party = CaseParty.objects.create(case=case, client=our_client)
    opponent_party = CaseParty.objects.create(case=case, client=opponent_client)
    log = CaseLog.objects.create(case=case, actor=user, content="上传案件材料")
    attachment = CaseLogAttachment.objects.create(
        log=log,
        file="case_logs/evidence.pdf",
        storage_root_type="case_folder",
        subdir_path="一审/1-立案材料/5-证据材料",
        relative_file_path="一审/1-立案材料/5-证据材料/evidence.pdf",
        original_filename="evidence.pdf",
    )
    return case, user, attachment, our_party, opponent_party


def test_material_sync_detail_fields_are_hidden_inputs() -> None:
    form = CaseLogAttachmentInlineForm()

    assert isinstance(form.fields["file"].widget, forms.FileInput)

    for field_name in [
        "material_category",
        "material_side",
        "material_parties",
        "material_supervising_authority",
        "material_type",
        "material_type_name",
    ]:
        assert isinstance(form.fields[field_name].widget, forms.HiddenInput)


@pytest.mark.django_db
def test_material_sync_payloads_include_case_parties_when_types_are_empty() -> None:
    case, _user, _attachment, our_party, opponent_party = _case_bundle()
    CaseMaterialType.objects.all().delete()

    admin = CaseLogAdmin(CaseLog, AdminSite())
    payloads = admin._build_material_sync_payloads(case.id)

    assert payloads["types"] == []
    assert payloads["parties"] == [
        {"value": str(our_party.id), "label": "我方当事人", "side": CaseMaterialSide.OUR},
        {"value": str(opponent_party.id), "label": "对方当事人", "side": CaseMaterialSide.OPPONENT},
    ]


@pytest.mark.django_db
def test_material_sync_payloads_include_plain_default_type_labels() -> None:
    case, _user, _attachment, _our_party, _opponent_party = _case_bundle()
    CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="证据材料", is_active=True)
    CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="其它材料", is_active=True)

    admin = CaseLogAdmin(CaseLog, AdminSite())
    payloads = admin._build_material_sync_payloads(case.id)

    type_payloads = {item["name"]: item for item in payloads["types"]}
    assert type_payloads["证据材料"]["label"] == "证据材料"
    assert type_payloads["证据材料"]["category"] == CaseMaterialCategory.PARTY
    assert type_payloads["其它材料"]["is_other"] == "1"


@pytest.mark.django_db
def test_material_sync_options_view_uses_selected_case_authorities() -> None:
    case, user, _attachment, _our_party, _opponent_party = _case_bundle()
    authority = SupervisingAuthority.objects.create(case=case, name="人民法院")

    request = RequestFactory().get(f"/admin/cases/caselog/material-sync-options/{case.id}/")
    request.user = user
    response = CaseLogAdmin(CaseLog, AdminSite()).material_sync_options_view(request, case.id)

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["authorities"] == [{"value": str(authority.id), "label": "审理机构 - 人民法院"}]


@pytest.mark.django_db
def test_material_sync_form_accepts_other_type_with_custom_name() -> None:
    _case, _user, attachment, our_party, _opponent_party = _case_bundle()
    other_type = CaseMaterialType.objects.create(
        category=CaseMaterialCategory.PARTY,
        name="其它材料",
        is_active=True,
    )

    form = CaseLogAttachmentInlineForm(
        data={
            "target_subdir": attachment.subdir_path,
            "sync_to_case_material": "on",
            "material_category": CaseMaterialCategory.PARTY,
            "material_side": CaseMaterialSide.OUR,
            "material_parties": str(our_party.id),
            "material_supervising_authority": "",
            "material_type": str(other_type.id),
            "material_type_name": "微信聊天记录",
        },
        instance=attachment,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["material_type"] == str(other_type.id)
    assert form.cleaned_data["material_type_name"] == "微信聊天记录"


@pytest.mark.django_db
def test_material_sync_form_requires_custom_name_for_other_type() -> None:
    _case, _user, attachment, _our_party, _opponent_party = _case_bundle()
    other_type = CaseMaterialType.objects.create(
        category=CaseMaterialCategory.PARTY,
        name="其它材料",
        is_active=True,
    )

    form = CaseLogAttachmentInlineForm(
        data={
            "target_subdir": attachment.subdir_path,
            "sync_to_case_material": "on",
            "material_category": CaseMaterialCategory.PARTY,
            "material_side": CaseMaterialSide.OUR,
            "material_parties": "",
            "material_supervising_authority": "",
            "material_type": str(other_type.id),
            "material_type_name": "",
        },
        instance=attachment,
    )

    assert form.is_valid() is False
    assert "选择其它材料时必须填写自定义类型名称" in str(form.errors)


@pytest.mark.django_db
def test_material_sync_form_accepts_party_material_without_specific_party() -> None:
    _case, _user, attachment, _our_party, _opponent_party = _case_bundle()
    CaseMaterialType.objects.all().delete()

    form = CaseLogAttachmentInlineForm(
        data={
            "target_subdir": attachment.subdir_path,
            "sync_to_case_material": "on",
            "material_category": CaseMaterialCategory.PARTY,
            "material_side": CaseMaterialSide.OUR,
            "material_parties": "",
            "material_supervising_authority": "",
            "material_type": "",
            "material_type_name": "证据材料",
        },
        instance=attachment,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["material_parties"] == ""


@pytest.mark.django_db
def test_sync_log_attachment_to_party_material_appears_in_case_material_view() -> None:
    case, user, attachment, our_party, _opponent_party = _case_bundle()

    material = _service().sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OUR,
        party_ids=[our_party.id],
        type_name="证据材料",
        user=user,
        perm_open_access=True,
    )

    assert material is not None
    assert material.source_attachment_id == attachment.id
    assert material.category == CaseMaterialCategory.PARTY
    assert material.side == CaseMaterialSide.OUR
    assert material.type_name == "证据材料"
    assert list(material.parties.values_list("id", flat=True)) == [our_party.id]

    view = _service().get_case_materials_view(case.id, user=user, perm_open_access=True)
    our_groups = view["party"]["our"]["groups"]
    assert our_groups[0]["type_name"] == "证据材料"
    assert our_groups[0]["items"][0]["attachment_id"] == attachment.id
    assert our_groups[0]["items"][0]["party_labels"] == ["我方当事人"]


@pytest.mark.django_db
def test_case_material_view_uses_preview_url_and_clean_filename_for_absolute_bound_path() -> None:
    case, user, attachment, our_party, _opponent_party = _case_bundle()
    attachment.file = r"C:\ceshi\case\complaint-signed.pdf"
    attachment.relative_file_path = "stage/materials/complaint-signed.pdf"
    attachment.original_filename = "complaint-signed.pdf"
    attachment.save(update_fields=["file", "relative_file_path", "original_filename"])

    _service().sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OUR,
        party_ids=[our_party.id],
        type_name="起诉状",
        user=user,
        perm_open_access=True,
    )

    view = _service().get_case_materials_view(case.id, user=user, perm_open_access=True)
    item = view["party"]["our"]["groups"][0]["items"][0]

    assert item["file_name"] == "complaint-signed.pdf"
    assert item["file_url"] == reverse("admin:cases_case_preview_log_attachment", args=[case.id, attachment.id])
    assert "/media/" not in item["file_url"]
    assert "C:" not in item["file_url"]


@pytest.mark.django_db
def test_preview_log_attachment_missing_file_renders_admin_error_page() -> None:
    case, user, attachment, _our_party, _opponent_party = _case_bundle()
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    attachment.relative_file_path = "missing/material.pdf"
    attachment.original_filename = "material.pdf"
    attachment.save(update_fields=["relative_file_path", "original_filename"])

    request = RequestFactory().get(f"/admin/cases/case/{case.id}/preview-log-attachment/{attachment.id}/")
    request.user = user
    response = CaseAdmin(Case, AdminSite()).preview_log_attachment_view(request, case.id, attachment.id)
    content = response.content.decode("utf-8")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")
    assert "文件无法预览" in content
    assert "重新上传/替换该材料" in content


@pytest.mark.django_db
def test_sync_custom_other_type_does_not_create_global_type() -> None:
    _case, user, attachment, _our_party, _opponent_party = _case_bundle()
    other_type = CaseMaterialType.objects.create(
        category=CaseMaterialCategory.PARTY,
        name="其它材料",
        is_active=True,
    )

    material = _service().sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OUR,
        type_id=other_type.id,
        type_name="微信聊天记录",
        user=user,
        perm_open_access=True,
    )

    assert material is not None
    assert material.type_id == other_type.id
    assert material.type_name == "微信聊天记录"
    assert CaseMaterialType.objects.filter(name="微信聊天记录").exists() is False


@pytest.mark.django_db
def test_resync_log_attachment_updates_existing_material_without_duplicate() -> None:
    _case, user, attachment, our_party, opponent_party = _case_bundle()
    service = _service()

    first = service.sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OUR,
        party_ids=[our_party.id],
        type_name="证据材料",
        user=user,
        perm_open_access=True,
    )
    updated = service.sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OPPONENT,
        party_ids=[opponent_party.id],
        type_name="答辩材料",
        user=user,
        perm_open_access=True,
    )

    assert first is not None
    assert updated is not None
    assert updated.id == first.id
    assert CaseMaterial.objects.count() == 1
    updated.refresh_from_db()
    assert updated.side == CaseMaterialSide.OPPONENT
    assert updated.type_name == "答辩材料"
    assert list(updated.parties.values_list("id", flat=True)) == [opponent_party.id]


@pytest.mark.django_db
def test_unsync_log_attachment_removes_material_but_keeps_log_attachment() -> None:
    _case, user, attachment, our_party, _opponent_party = _case_bundle()
    service = _service()
    service.sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.PARTY,
        side=CaseMaterialSide.OUR,
        party_ids=[our_party.id],
        type_name="证据材料",
        user=user,
        perm_open_access=True,
    )

    service.sync_attachment_to_material(
        attachment_id=attachment.id,
        include=False,
        user=user,
        perm_open_access=True,
    )

    assert CaseMaterial.objects.filter(source_attachment_id=attachment.id).exists() is False
    assert CaseLogAttachment.objects.filter(id=attachment.id).exists() is True


@pytest.mark.django_db
def test_sync_log_attachment_to_non_party_material_requires_and_uses_authority() -> None:
    case, user, attachment, _our_party, _opponent_party = _case_bundle()
    service = _service()

    with pytest.raises(ValidationException):
        service.sync_attachment_to_material(
            attachment_id=attachment.id,
            include=True,
            category=CaseMaterialCategory.NON_PARTY,
            type_name="法院文书",
            user=user,
            perm_open_access=True,
        )

    authority = SupervisingAuthority.objects.create(case=case, name="人民法院")
    material = service.sync_attachment_to_material(
        attachment_id=attachment.id,
        include=True,
        category=CaseMaterialCategory.NON_PARTY,
        supervising_authority_id=authority.id,
        type_name="法院文书",
        user=user,
        perm_open_access=True,
    )

    assert material is not None
    assert material.category == CaseMaterialCategory.NON_PARTY
    assert material.side is None
    assert material.supervising_authority_id == authority.id
    assert list(material.parties.values_list("id", flat=True)) == []

    view = service.get_case_materials_view(case.id, user=user, perm_open_access=True)
    assert view["non_party"][0]["title"] == "审理机构 - 人民法院"
    assert view["non_party"][0]["groups"][0]["type_name"] == "法院文书"
