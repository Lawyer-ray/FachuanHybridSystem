"""contracts 模块真实执行测试 - 覆盖 archive/constants, category_mapping, file_hash_utils, domain/validator 等。"""
from __future__ import annotations

import hashlib
import pytest
from pathlib import Path


# ============================================================
# contracts/services/archive/constants.py
# ============================================================


class TestArchiveConstants:
    def test_archive_checklist_keys(self) -> None:
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST

        assert "non_litigation" in ARCHIVE_CHECKLIST
        assert "litigation" in ARCHIVE_CHECKLIST
        assert "criminal" in ARCHIVE_CHECKLIST

    def test_litigation_checklist_count(self) -> None:
        from apps.contracts.services.archive.constants import LITIGATION_CHECKLIST

        assert len(LITIGATION_CHECKLIST) == 20

    def test_criminal_checklist_count(self) -> None:
        from apps.contracts.services.archive.constants import CRIMINAL_CHECKLIST

        assert len(CRIMINAL_CHECKLIST) == 18

    def test_non_litigation_checklist_count(self) -> None:
        from apps.contracts.services.archive.constants import NON_LITIGATION_CHECKLIST

        assert len(NON_LITIGATION_CHECKLIST) == 12

    def test_checklist_items_have_required_fields(self) -> None:
        from apps.contracts.services.archive.constants import LITIGATION_CHECKLIST

        for item in LITIGATION_CHECKLIST:
            assert "code" in item
            assert "name" in item
            assert "required" in item
            assert "source" in item

    def test_archive_skip_codes(self) -> None:
        from apps.contracts.services.archive.constants import ARCHIVE_SKIP_CODES

        assert "lt_1" in ARCHIVE_SKIP_CODES
        assert "cr_1" in ARCHIVE_SKIP_CODES
        assert "nl_1" in ARCHIVE_SKIP_CODES

    def test_archive_skip_templates(self) -> None:
        from apps.contracts.services.archive.constants import ARCHIVE_SKIP_TEMPLATES

        assert "case_cover" in ARCHIVE_SKIP_TEMPLATES
        assert "inner_catalog" in ARCHIVE_SKIP_TEMPLATES

    def test_archive_folder_name(self) -> None:
        from apps.contracts.services.archive.constants import ARCHIVE_FOLDER_NAME

        assert isinstance(ARCHIVE_FOLDER_NAME, str)
        assert len(ARCHIVE_FOLDER_NAME) > 0

    def test_case_material_keyword_mapping_keys(self) -> None:
        from apps.contracts.services.archive.constants import CASE_MATERIAL_KEYWORD_MAPPING

        assert "non_litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "litigation" in CASE_MATERIAL_KEYWORD_MAPPING
        assert "criminal" in CASE_MATERIAL_KEYWORD_MAPPING

    def test_archive_subitem_order_rules(self) -> None:
        from apps.contracts.services.archive.constants import ARCHIVE_SUBITEM_ORDER_RULES

        assert "nl_4" in ARCHIVE_SUBITEM_ORDER_RULES
        assert "lt_7" in ARCHIVE_SUBITEM_ORDER_RULES
        assert "cr_11" in ARCHIVE_SUBITEM_ORDER_RULES


# ============================================================
# contracts/services/archive/category_mapping.py
# ============================================================


class TestCategoryMapping:
    def test_get_archive_category_civil(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("civil") == "litigation"

    def test_get_archive_category_criminal(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("criminal") == "criminal"

    def test_get_archive_category_advisor(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("advisor") == "non_litigation"

    def test_get_archive_category_special(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("special") == "non_litigation"

    def test_get_archive_category_unknown_defaults_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("unknown_type") == "litigation"

    def test_get_archive_category_labor(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("labor") == "litigation"

    def test_archive_category_choices(self) -> None:
        from apps.contracts.services.archive.category_mapping import ArchiveCategory

        assert ArchiveCategory.NON_LITIGATION == "non_litigation"
        assert ArchiveCategory.LITIGATION == "litigation"
        assert ArchiveCategory.CRIMINAL == "criminal"


# ============================================================
# contracts/services/contract/integrations/file_hash_utils.py
# ============================================================


class TestFileHashUtils:
    def test_compute_file_hash(self, tmp_path: object) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash

        p = Path(str(tmp_path)) / "test.txt"
        p.write_bytes(b"hello world")
        result = compute_file_hash(p)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_compute_file_hash_nonexistent(self, tmp_path: object) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash

        p = Path(str(tmp_path)) / "nonexistent.txt"
        result = compute_file_hash(p)
        assert result == ""

    def test_compute_file_hash_from_bytes(self) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes

        data = b"test data for hashing"
        result = compute_file_hash_from_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected

    def test_compute_file_hash_from_bytes_empty(self) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes

        result = compute_file_hash_from_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_compute_file_hash_from_bytes_large(self) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes

        data = b"x" * 100_000
        result = compute_file_hash_from_bytes(data)
        assert len(result) == 64  # SHA-256 hex digest length


# ============================================================
# contracts/services/contract/domain/validator.py
# ============================================================


class TestContractValidator:
    def test_validate_custom_no_terms_raises(self) -> None:
        from apps.contracts.services.contract.domain.validator import ContractValidator
        from apps.core.exceptions import ValidationException

        validator = ContractValidator()
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": ""})

    def test_validate_custom_with_terms_passes(self) -> None:
        from apps.contracts.services.contract.domain.validator import ContractValidator

        validator = ContractValidator()
        # Should not raise
        validator.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": "Some terms"})

    def test_validate_none_fee_mode(self) -> None:
        from apps.contracts.services.contract.domain.validator import ContractValidator

        validator = ContractValidator()
        # None fee_mode should pass without validation
        validator.validate_fee_mode({})

    def test_validate_full_risk_no_rate(self) -> None:
        from apps.contracts.services.contract.domain.validator import ContractValidator
        from apps.core.exceptions import ValidationException

        validator = ContractValidator()
        with pytest.raises(ValidationException):
            validator.validate_fee_mode({"fee_mode": "FULL_RISK"})

    def test_validate_stages_empty(self) -> None:
        from apps.contracts.services.contract.domain.validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_stages([], None)
        assert result == []


# ============================================================
# contracts/models (integration tests)
# ============================================================


@pytest.mark.django_db
class TestContractModels:
    def test_contract_creation(self) -> None:
        from apps.contracts.models import Contract

        contract = Contract.objects.create(name="Test Contract", case_type="civil")
        assert contract.pk is not None
        assert contract.name == "Test Contract"

    def test_contract_str(self) -> None:
        from apps.contracts.models import Contract

        contract = Contract.objects.create(name="Display Contract")
        assert str(contract) == "Display Contract"


@pytest.mark.django_db
class TestContractPartyModels:
    def test_contract_party_creation(self) -> None:
        from apps.contracts.models import Contract, ContractParty
        from apps.client.models import Client

        contract = Contract.objects.create(name="Party Test Contract")
        client = Client.objects.create(name="Party Client", client_type=Client.NATURAL)
        party = ContractParty.objects.create(
            contract=contract,
            client=client,
            role="PRINCIPAL",
        )
        assert party.pk is not None
        assert party.role == "PRINCIPAL"


@pytest.mark.django_db
class TestSupplementaryAgreement:
    def test_supplementary_creation(self) -> None:
        from apps.contracts.models import Contract, SupplementaryAgreement

        contract = Contract.objects.create(name="Supp Test Contract")
        supp = SupplementaryAgreement.objects.create(
            contract=contract,
            name="Supp Agreement 1",
        )
        assert supp.pk is not None
        assert supp.name == "Supp Agreement 1"
