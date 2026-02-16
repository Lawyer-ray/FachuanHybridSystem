import re
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st


@pytest.mark.property_test
@settings(max_examples=200)
@given(
    year=st.integers(min_value=1900, max_value=date.today().year),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    seq_prefix=st.integers(min_value=0, max_value=99),
    gender_digit=st.integers(min_value=0, max_value=9),
)
def test_id_card_utils_parsing_correctness(year, month, day, seq_prefix, gender_digit):
    from apps.core.utils.id_card_utils import IdCardUtils

    seq = f"{seq_prefix:02d}{gender_digit}"
    id_number = f"110101{year:04d}{month:02d}{day:02d}{seq}0"

    info = IdCardUtils.parse_id_card_info(id_number)

    expected_birth = f"{year:04d}年{month:02d}月{day:02d}日"
    assert info.birth_date == expected_birth

    expected_gender = "男" if gender_digit % 2 == 1 else "女"
    assert info.gender == expected_gender

    today = date.today()
    expected_age = today.year - year
    if (today.month, today.day) < (month, day):
        expected_age -= 1
    assert info.age == expected_age


@pytest.mark.property_test
def test_keep_original_name_storage_import_compatibility():
    from apps.core.storage import KeepOriginalNameStorage as StorageNew
    from apps.organization.models import KeepOriginalNameStorage as StorageOld

    assert StorageNew is StorageOld


@pytest.mark.property_test
@settings(max_examples=100)
@given(
    protocol_name=st.sampled_from(
        [
            "ICaseService",
            "ICaseSearchService",
            "ICaseNumberService",
            "ICaseLogService",
            "IClientService",
            "IContractService",
            "IContractPaymentService",
            "IDocumentService",
            "IOrganizationService",
            "ILawyerService",
            "ILawFirmService",
            "IReminderService",
            "ISystemConfigService",
            "ILLMService",
        ]
    )
)
def test_protocol_import_backward_compatibility(protocol_name: str):
    from apps.core import interfaces
    from apps.core import protocols

    assert hasattr(interfaces, protocol_name)
    assert hasattr(protocols, protocol_name)
    assert getattr(interfaces, protocol_name) is getattr(protocols, protocol_name)


@pytest.mark.property_test
def test_service_locator_returns_services_with_new_internal_methods():
    from apps.core.interfaces import ServiceLocator

    client_service = ServiceLocator.get_client_service()
    assert hasattr(client_service, "get_identity_docs_by_client_internal")

    case_service = ServiceLocator.get_case_service()
    assert hasattr(case_service, "get_case_template_binding_internal")
    assert hasattr(case_service, "get_case_parties_internal")

    contract_service = ServiceLocator.get_contract_service()
    assert hasattr(contract_service, "get_supplementary_agreements_internal")
    assert hasattr(contract_service, "get_contract_model_internal")

    document_service = ServiceLocator.get_document_service()
    assert hasattr(document_service, "get_templates_by_case_type_internal")


@pytest.mark.property_test
def test_no_cross_module_model_imports_in_documents_and_cases():
    repo_root = Path(__file__).resolve().parents[3]
    apps_dir = repo_root / "apps"

    targets = [
        apps_dir / "documents",
        apps_dir / "cases",
    ]

    forbidden_patterns = [
        r"from\s+apps\.client\.models\s+import",
        r"from\s+apps\.contracts\.models\s+import",
        r"from\s+apps\.organization\.models\s+import",
        r"from\s+apps\.reminders\.models\s+import",
    ]

    violations = []
    for target in targets:
        for py_file in target.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            content = py_file.read_text(encoding="utf-8")

            for pattern in forbidden_patterns:
                if re.search(pattern, content):
                    violations.append((str(py_file), pattern))

    assert not violations, "发现 documents/cases 存在跨模块 Model 导入:\n" + "\n".join(
        f"- {path}: {pattern}" for path, pattern in violations
    )

