import pytest

from apps.cases.services.number.case_filing_number_service import CaseFilingNumberService
from apps.core.enums import SimpleCaseType
from tests.factories import CaseFactory


@pytest.mark.django_db
def test_generate_case_filing_number_on_sqlite_does_not_fail():
    service = CaseFilingNumberService()
    case = CaseFactory(case_type=SimpleCaseType.CIVIL)
    created_year = case.start_date.year  # type: ignore[attr-defined]

    filing_number = service.generate_case_filing_number_internal(
        case_id=case.id,  # type: ignore
        case_type=case.case_type,
        created_year=created_year,
    )
    assert filing_number.startswith(f"{created_year}_")
    assert "_AJ_" in filing_number

    case.filing_number = filing_number  # type: ignore[attr-defined]
    case.save(update_fields=["filing_number"])  # type: ignore[attr-defined]

    case2 = CaseFactory(case_type=SimpleCaseType.CIVIL, start_date=case.start_date)
    filing_number2 = service.generate_case_filing_number_internal(
        case_id=case2.id,  # type: ignore
        case_type=case2.case_type,
        created_year=created_year,
    )
    assert filing_number2.endswith("_2")
