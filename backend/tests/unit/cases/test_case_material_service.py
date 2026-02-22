import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases.models import (
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialSide,
    SupervisingAuthority,
)
from apps.cases.services.material.composition import build_case_material_service
from apps.core.exceptions import NotFoundError, ValidationException
from tests.factories.case_factories import CaseFactory, CaseLogFactory, CasePartyFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestCaseMaterialService:
    def test_bind_materials_creates_party_material_and_binds_parties(self):
        user = LawyerFactory()
        case = CaseFactory()
        p1 = CasePartyFactory(case=case, client__is_our_client=True)
        p2 = CasePartyFactory(case=case, client__is_our_client=True)
        log = CaseLogFactory(case=case, actor=user)
        att = CaseLogAttachment.objects.create(  # type: ignore[misc]
            log=log,
            file=SimpleUploadedFile("evidence.pdf", b"pdf", content_type="application/pdf"),
        )

        service = build_case_material_service()
        saved = service.bind_materials(
            case_id=case.id,  # type: ignore[attr-defined]
            items=[
                {
                    "attachment_id": att.id,
                    "category": CaseMaterialCategory.PARTY,
                    "type_id": None,
                    "type_name": "身份证",
                    "side": CaseMaterialSide.OUR,
                    "party_ids": [p1.id, p2.id],  # type: ignore[attr-defined]
                    "supervising_authority_id": None,
                }
            ],
            user=user,
            org_access=None,
            perm_open_access=True,
        )

        assert len(saved) == 1
        m = CaseMaterial.objects.get(source_attachment_id=att.id)
        assert m.case_id == case.id  # type: ignore[attr-defined]
        assert m.category == CaseMaterialCategory.PARTY
        assert m.side == CaseMaterialSide.OUR
        assert set(m.parties.values_list("id", flat=True)) == {p1.id, p2.id}  # type: ignore[attr-defined]

    def test_bind_materials_requires_supervising_authority_for_non_party(self):
        user = LawyerFactory()
        case = CaseFactory()
        log = CaseLogFactory(case=case, actor=user)
        att = CaseLogAttachment.objects.create(  # type: ignore[misc]
            log=log,
            file=SimpleUploadedFile("notice.pdf", b"pdf", content_type="application/pdf"),
        )

        service = build_case_material_service()
        with pytest.raises(ValidationException) as exc_info:
            service.bind_materials(
                case_id=case.id,  # type: ignore[attr-defined]
                items=[
                    {
                        "attachment_id": att.id,
                        "category": CaseMaterialCategory.NON_PARTY,
                        "type_name": "法院通知",
                        "side": None,
                        "party_ids": [],
                        "supervising_authority_id": None,
                    }
                ],
                user=user,
                org_access=None,
                perm_open_access=True,
            )

        assert "必须选择主管机关" in str(exc_info.value)

    def test_bind_materials_validates_attachment_belongs_to_case(self):
        user = LawyerFactory()
        case1 = CaseFactory()
        case2 = CaseFactory()
        log = CaseLogFactory(case=case2, actor=user)
        att = CaseLogAttachment.objects.create(  # type: ignore[misc]
            log=log,
            file=SimpleUploadedFile("evidence.pdf", b"pdf", content_type="application/pdf"),
        )

        service = build_case_material_service()
        with pytest.raises(NotFoundError) as exc_info:
            service.bind_materials(
                case_id=case1.id,  # type: ignore[attr-defined]
                items=[
                    {
                        "attachment_id": att.id,
                        "category": CaseMaterialCategory.PARTY,
                        "type_name": "身份证",
                        "side": CaseMaterialSide.OUR,
                        "party_ids": [],
                        "supervising_authority_id": None,
                    }
                ],
                user=user,
                org_access=None,
                perm_open_access=True,
            )

        assert "附件不存在" in str(exc_info.value) or "不属于该案件" in str(exc_info.value)

    def test_list_bind_candidates_includes_bound_material_payload(self):
        user = LawyerFactory()
        case = CaseFactory()
        p1 = CasePartyFactory(case=case, client__is_our_client=True)
        auth = SupervisingAuthority.objects.create(case=case, name="测试机关")  # type: ignore[misc]
        log = CaseLogFactory(case=case, actor=user)
        att = CaseLogAttachment.objects.create(  # type: ignore[misc]
            log=log,
            file=SimpleUploadedFile("notice.pdf", b"pdf", content_type="application/pdf"),
        )

        service = build_case_material_service()
        materials = service.bind_materials(
            case_id=case.id,  # type: ignore[attr-defined]
            items=[
                {
                    "attachment_id": att.id,
                    "category": CaseMaterialCategory.NON_PARTY,
                    "type_name": "法院通知",
                    "side": None,
                    "party_ids": [p1.id],  # type: ignore[attr-defined]
                    "supervising_authority_id": auth.id,
                }
            ],
            user=user,
            org_access=None,
            perm_open_access=True,
        )
        assert materials

        candidates = service.list_bind_candidates(
            case_id=case.id,  # type: ignore[attr-defined]
            user=user,
            org_access=None,
            perm_open_access=True,
        )
        assert candidates
        row = next(x for x in candidates if x["attachment_id"] == att.id)
        assert row["material"] is not None
        assert row["material"]["id"] == materials[0].id
        assert row["material"]["category"] == CaseMaterialCategory.NON_PARTY
