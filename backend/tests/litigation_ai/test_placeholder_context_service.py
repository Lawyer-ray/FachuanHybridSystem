import pytest

from apps.litigation_ai.placeholders import LitigationPlaceholderContextService, LitigationPlaceholderKeys
from tests.factories.case_factories import CaseFactory, CasePartyFactory


@pytest.mark.django_db
def test_placeholder_context_service_complaint_keys(monkeypatch):
    case = CaseFactory()
    CasePartyFactory(case=case)

    service = LitigationPlaceholderContextService()

    monkeypatch.setattr(
        "apps.documents.services.placeholders.litigation.supervising_authority_service.SupervisingAuthorityService.get_supervising_authority",
        lambda self, case_id: "北京市朝阳区人民法院",
    )
    monkeypatch.setattr(
        "apps.documents.services.placeholders.litigation.complaint_party_service.ComplaintPartyService.generate_party_info",
        lambda self, case_id: "原告：A\n被告：B",
    )
    monkeypatch.setattr(
        "apps.documents.services.placeholders.litigation.complaint_signature_service.ComplaintSignatureService.generate_signature_info",
        lambda self, case_id: "此致\n北京市朝阳区人民法院\n具状人：A",
    )

    blocks = service.build_fixed_blocks(case.id, "complaint")
    assert blocks[LitigationPlaceholderKeys.COURT] == "北京市朝阳区人民法院"
    assert LitigationPlaceholderKeys.COMPLAINT_PARTY in blocks
    assert LitigationPlaceholderKeys.COMPLAINT_SIGNATURE in blocks

