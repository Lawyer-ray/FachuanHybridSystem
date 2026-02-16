import pytest

from apps.contracts.services.assignment.filing_number_service import FilingNumberService
from apps.core.enums import CaseType
from tests.factories import ContractFactory


@pytest.mark.django_db
def test_generate_contract_filing_number_on_sqlite_does_not_fail():
    service = FilingNumberService()
    contract = ContractFactory(case_type=CaseType.CIVIL)
    created_year = contract.specified_date.year

    filing_number = service.generate_contract_filing_number(
        contract_id=contract.id, case_type=contract.case_type, created_year=created_year
    )
    assert filing_number.startswith(f"{created_year}_")
    assert "_HT_" in filing_number

    contract.filing_number = filing_number
    contract.save(update_fields=["filing_number"])

    contract2 = ContractFactory(case_type=CaseType.CIVIL, specified_date=contract.specified_date)
    filing_number2 = service.generate_contract_filing_number(
        contract_id=contract2.id, case_type=contract2.case_type, created_year=created_year
    )
    assert filing_number2.endswith("_2")
