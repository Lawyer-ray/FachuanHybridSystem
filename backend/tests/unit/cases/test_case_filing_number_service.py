import pytest

from apps.cases.services.number.case_filing_number_service import CaseFilingNumberService
from apps.core.enums import SimpleCaseType
from tests.factories.case_factories import CaseFactory


@pytest.mark.django_db
def test_generate_case_filing_number_increments_sequence():
    case1 = CaseFactory()
    case1.filing_number = "2026_民事_AJ_1"  # type: ignore[attr-defined]
    case1.save(update_fields=["filing_number"])  # type: ignore[attr-defined]

    case2 = CaseFactory()

    service = CaseFilingNumberService()
    filing_number = service.generate_case_filing_number_internal(
        case_id=case2.id,  # type: ignore[attr-defined]
        case_type=SimpleCaseType.CIVIL,
        created_year=2026,
    )

    assert filing_number.startswith("2026_民事_AJ_")
    assert filing_number.endswith("_2")


@pytest.mark.django_db
def test_generate_case_filing_number_invalid_year_raises():
    case = CaseFactory()
    service = CaseFilingNumberService()
    with pytest.raises(Exception):
        service.generate_case_filing_number_internal(case_id=case.id, case_type=SimpleCaseType.CIVIL, created_year=1800)  # type: ignore[attr-defined]
