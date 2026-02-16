from types import SimpleNamespace

import pytest

from apps.automation.services.litigation.schemas import CourtPleadingSignals
from apps.litigation_ai.services.conversation_service import ConversationService
from tests.factories.case_factories import CaseFactory, CasePartyFactory


@pytest.mark.django_db
def test_recommended_types_plaintiff_without_counterclaim(monkeypatch):
    case = CaseFactory()
    CasePartyFactory(case=case, legal_status="plaintiff")

    monkeypatch.setattr(
        "apps.automation.services.litigation.court_pleading_signals_service.CourtPleadingSignalsService.get_signals",
        lambda self, case_id: CourtPleadingSignals(has_counterclaim=False),
    )

    service = ConversationService()
    service.case_service = SimpleNamespace(
        get_case_internal=lambda case_id: case,
        get_case_parties_internal=lambda case_id: list(case.parties.all()),
    )

    types_ = service.get_recommended_document_types(case.id)
    assert "complaint" in types_
    assert "counterclaim_defense" not in types_


@pytest.mark.django_db
def test_recommended_types_plaintiff_with_counterclaim(monkeypatch):
    case = CaseFactory()
    CasePartyFactory(case=case, legal_status="plaintiff")

    monkeypatch.setattr(
        "apps.automation.services.litigation.court_pleading_signals_service.CourtPleadingSignalsService.get_signals",
        lambda self, case_id: CourtPleadingSignals(has_counterclaim=True),
    )

    service = ConversationService()
    service.case_service = SimpleNamespace(
        get_case_internal=lambda case_id: case,
        get_case_parties_internal=lambda case_id: list(case.parties.all()),
    )

    types_ = service.get_recommended_document_types(case.id)
    assert "complaint" in types_
    assert "counterclaim_defense" in types_


@pytest.mark.django_db
def test_recommended_types_defendant(monkeypatch):
    case = CaseFactory()
    CasePartyFactory(case=case, legal_status="defendant")

    monkeypatch.setattr(
        "apps.automation.services.litigation.court_pleading_signals_service.CourtPleadingSignalsService.get_signals",
        lambda self, case_id: CourtPleadingSignals(has_counterclaim=False),
    )

    service = ConversationService()
    service.case_service = SimpleNamespace(
        get_case_internal=lambda case_id: case,
        get_case_parties_internal=lambda case_id: list(case.parties.all()),
    )

    types_ = service.get_recommended_document_types(case.id)
    assert "defense" in types_
    assert "counterclaim" in types_
