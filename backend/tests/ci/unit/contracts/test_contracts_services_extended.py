"""Tests for contracts services, signals, templatetags, and archive utilities."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.contracts.models import Contract


# ── Templatetags ────────────────────────────────────────────────────────────


class TestContractTags:
    """contracts/templatetags/contract_tags.py tests."""

    def test_get_item_found(self) -> None:
        from apps.contracts.templatetags.contract_tags import get_item

        result = get_item({"key1": "val1", "key2": "val2"}, "key1")
        assert result == "val1"

    def test_get_item_not_found(self) -> None:
        from apps.contracts.templatetags.contract_tags import get_item

        result = get_item({"key1": "val1"}, "missing")
        assert result is None

    def test_get_item_empty_dict(self) -> None:
        from apps.contracts.templatetags.contract_tags import get_item

        result = get_item({}, "any")
        assert result is None

    def test_to_json_dict(self) -> None:
        from apps.contracts.templatetags.contract_tags import to_json

        result = to_json({"name": "测试", "value": 123})
        parsed = json.loads(result)
        assert parsed["name"] == "测试"
        assert parsed["value"] == 123

    def test_to_json_list(self) -> None:
        from apps.contracts.templatetags.contract_tags import to_json

        result = to_json([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_to_json_string(self) -> None:
        from apps.contracts.templatetags.contract_tags import to_json

        result = to_json("hello")
        assert json.loads(result) == "hello"

    def test_to_json_none(self) -> None:
        from apps.contracts.templatetags.contract_tags import to_json

        result = to_json(None)
        assert result == "null"


# ── Archive Category Mapping ────────────────────────────────────────────────


class TestArchiveCategoryMapping:
    """contracts/services/archive/category_mapping.py tests."""

    def test_civil_maps_to_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("civil") == "litigation"

    def test_criminal_maps_to_criminal(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("criminal") == "criminal"

    def test_advisor_maps_to_non_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("advisor") == "non_litigation"

    def test_special_maps_to_non_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("special") == "non_litigation"

    def test_intl_maps_to_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("intl") == "litigation"

    def test_labor_maps_to_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("labor") == "litigation"

    def test_administrative_maps_to_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("administrative") == "litigation"

    def test_unknown_defaults_to_litigation(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        assert get_archive_category("unknown_type") == "litigation"


# ── File Hash Utils ─────────────────────────────────────────────────────────


class TestFileHashUtils:
    """contracts/services/contract/integrations/file_hash_utils.py tests."""

    def test_compute_file_hash(self, tmp_path: Any) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world")
        result = compute_file_hash(test_file)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_compute_file_hash_nonexistent(self, tmp_path: Any) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash

        fake_path = tmp_path / "nonexistent.txt"
        result = compute_file_hash(fake_path)
        assert result == ""

    def test_compute_file_hash_empty_file(self, tmp_path: Any) -> None:
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash

        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")
        result = compute_file_hash(test_file)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

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


# ── Contract Validator ──────────────────────────────────────────────────────


class TestContractValidator:
    """contracts/services/contract/domain/validator.py tests."""

    def _make_validator(self) -> Any:
        from apps.contracts.services.contract.domain.validator import ContractValidator
        from apps.core.config.business_config import BusinessConfig

        config = MagicMock(spec=BusinessConfig)
        config.get_stages_for_case_type.return_value = [
            ("first_trial", "一审"),
            ("second_trial", "二审"),
        ]
        return ContractValidator(config=config)

    def test_validate_fixed_valid(self) -> None:
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "FIXED", "fixed_amount": 1000})

    def test_validate_fixed_no_amount(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "FIXED"})

    def test_validate_fixed_zero_amount(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "FIXED", "fixed_amount": 0})

    def test_validate_semi_risk_valid(self) -> None:
        v = self._make_validator()
        v.validate_fee_mode({
            "fee_mode": "SEMI_RISK",
            "fixed_amount": 5000,
            "risk_rate": 10,
        })

    def test_validate_semi_risk_missing_rate(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "SEMI_RISK", "fixed_amount": 5000})

    def test_validate_full_risk_valid(self) -> None:
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "FULL_RISK", "risk_rate": 15})

    def test_validate_full_risk_missing_rate(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "FULL_RISK"})

    def test_validate_custom_valid(self) -> None:
        v = self._make_validator()
        v.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": "按年收费"})

    def test_validate_custom_empty_terms(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_fee_mode({"fee_mode": "CUSTOM", "custom_terms": ""})

    def test_validate_stages_valid(self) -> None:
        v = self._make_validator()
        result = v.validate_stages(["first_trial"], "civil")
        assert result == ["first_trial"]

    def test_validate_stages_empty(self) -> None:
        v = self._make_validator()
        result = v.validate_stages([], "civil")
        assert result == []

    def test_validate_stages_invalid(self) -> None:
        from apps.core.exceptions import ValidationException

        v = self._make_validator()
        with pytest.raises(ValidationException):
            v.validate_stages(["nonexistent_stage"], "civil")

    def test_validate_no_fee_mode(self) -> None:
        v = self._make_validator()
        v.validate_fee_mode({})  # Should not raise


# ── ContractAccessPolicy ────────────────────────────────────────────────────


class TestContractAccessPolicy:
    """contracts/services/contract/domain/access_policy.py tests."""

    def _make_policy(self) -> Any:
        from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

        repo = MagicMock()
        return ContractAccessPolicy(contract_access_repo=repo), repo

    def test_has_access_perm_open(self) -> None:
        policy, _ = self._make_policy()
        assert policy.has_access(1, None, None, perm_open_access=True) is True

    def test_has_access_no_user(self) -> None:
        policy, _ = self._make_policy()
        assert policy.has_access(1, None, None) is False

    def test_has_access_unauthenticated(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = False
        assert policy.has_access(1, user, None) is False

    def test_has_access_admin(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = True
        assert policy.has_access(1, user, None) is True

    def test_has_access_repo_assignment(self) -> None:
        policy, repo = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = 1
        repo.has_assignment_access.return_value = True
        policy.get_allowed_lawyer_ids = MagicMock(return_value=[1])
        assert policy.has_access(1, user, None) is True

    def test_has_access_no_repo_access(self) -> None:
        policy, repo = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = 1
        repo.has_assignment_access.return_value = False
        repo.has_case_assignment_access.return_value = False
        policy.get_allowed_lawyer_ids = MagicMock(return_value=[1])
        assert policy.has_access(1, user, None) is False

    def test_ensure_access_raises_on_no_access(self) -> None:
        from apps.core.exceptions import PermissionDenied

        policy, _ = self._make_policy()
        with pytest.raises(PermissionDenied):
            policy.ensure_access(contract_id=1, user=None, org_access=None)

    def test_ensure_access_passes_with_access(self) -> None:
        policy, _ = self._make_policy()
        policy.ensure_access(
            contract_id=1, user=None, org_access=None, perm_open_access=True
        )

    def test_can_create_contract_authenticated(self) -> None:
        policy, _ = self._make_policy()
        user = MagicMock()
        user.is_authenticated = True
        assert policy.can_create_contract(user) is True

    def test_can_create_contract_no_user(self) -> None:
        policy, _ = self._make_policy()
        assert policy.can_create_contract(None) is False

    def test_filter_queryset_open_access(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        policy.filter_queryset(qs, None, None, perm_open_access=True)
        # qs should be returned as-is
        qs.none.assert_not_called()

    def test_filter_queryset_no_user(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        policy.filter_queryset(qs, None, None)
        qs.none.assert_called_once()

    def test_filter_queryset_admin(self) -> None:
        policy, _ = self._make_policy()
        qs = MagicMock()
        user = MagicMock()
        user.is_authenticated = True
        user.is_admin = True
        result = policy.filter_queryset(qs, user, None)
        assert result == qs

    def test_has_access_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        assert policy.has_access_ctx(contract_id=1, ctx=ctx) is True

    def test_ensure_access_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        policy.ensure_access_ctx(contract_id=1, ctx=ctx)

    def test_filter_queryset_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        policy, _ = self._make_policy()
        qs = MagicMock()
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        policy.filter_queryset_ctx(qs, ctx)
        qs.none.assert_not_called()


# ── Signals ─────────────────────────────────────────────────────────────────


class TestContractsSignals:
    """contracts/signals.py signal handler tests."""

    def test_cleanup_finalized_material_file_deletes(self, tmp_path: Any) -> None:
        """Test signal handler with real file on filesystem."""
        from apps.contracts.signals import _cleanup_finalized_material_file

        # Create a real temp file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        instance = MagicMock()
        instance.file_path = test_file.name
        instance.pk = 1

        with patch("apps.contracts.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            _cleanup_finalized_material_file(None, instance)

        assert not test_file.exists()  # File should be deleted

    def test_cleanup_finalized_material_no_file(self) -> None:
        from apps.contracts.signals import _cleanup_finalized_material_file

        instance = MagicMock()
        instance.file_path = ""
        _cleanup_finalized_material_file(None, instance)
        # No exception, no file operations

    def test_cleanup_finalized_material_file_not_exists(self, tmp_path: Any) -> None:
        """When file doesn't exist, should not raise."""
        from apps.contracts.signals import _cleanup_finalized_material_file

        instance = MagicMock()
        instance.file_path = "nonexistent/file.pdf"
        instance.pk = 2

        with patch("apps.contracts.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            _cleanup_finalized_material_file(None, instance)
        # No exception raised

    def test_cleanup_finalized_material_oserror_handled(self, tmp_path: Any) -> None:
        from apps.contracts.signals import _cleanup_finalized_material_file

        # Create a file
        test_file = tmp_path / "error.pdf"
        test_file.write_bytes(b"content")

        instance = MagicMock()
        instance.file_path = "error.pdf"
        instance.pk = 3

        with patch("apps.contracts.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            with patch("pathlib.Path.unlink", side_effect=OSError("Permission denied")):
                # Should not raise
                _cleanup_finalized_material_file(None, instance)

    def test_cleanup_invoice_file_no_path(self) -> None:
        from apps.contracts.signals import _cleanup_invoice_file

        instance = MagicMock()
        instance.file_path = ""
        _cleanup_invoice_file(None, instance)

    def test_cleanup_client_payment_image_no_path(self) -> None:
        from apps.contracts.signals import _cleanup_client_payment_image

        instance = MagicMock()
        instance.image_path = ""
        _cleanup_client_payment_image(None, instance)


# ── Archive Constants ───────────────────────────────────────────────────────


class TestArchiveConstants:
    """contracts/services/archive/constants.py tests."""

    def test_checklist_item_type(self) -> None:
        from apps.contracts.services.archive.constants import ChecklistItem

        item: ChecklistItem = {
            "code": "test_1",
            "name": "测试项",
            "template": "test_template",
            "required": True,
            "auto_detect": None,
            "source": "template",
        }
        assert item["code"] == "test_1"
        assert item["required"] is True

    def test_non_litigation_checklist_exists(self) -> None:
        from apps.contracts.services.archive.constants import NON_LITIGATION_CHECKLIST

        assert len(NON_LITIGATION_CHECKLIST) > 0
        # Check first item structure
        first = NON_LITIGATION_CHECKLIST[0]
        assert "code" in first
        assert "name" in first

    def test_litigation_checklist_exists(self) -> None:
        from apps.contracts.services.archive.constants import LITIGATION_CHECKLIST

        assert len(LITIGATION_CHECKLIST) > 0

    def test_criminal_checklist_exists(self) -> None:
        from apps.contracts.services.archive.constants import CRIMINAL_CHECKLIST

        assert len(CRIMINAL_CHECKLIST) > 0


# ── Workflow Services ───────────────────────────────────────────────────────


class TestCaseCreationWorkflow:
    """contracts/services/contract/admin/workflows/case_creation_workflow.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.admin.workflows.case_creation_workflow import ContractCaseCreationWorkflow

        assert ContractCaseCreationWorkflow is not None


class TestCloneWorkflow:
    """contracts/services/contract/admin/workflows/clone_workflow.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.admin.workflows.clone_workflow import ContractCloneWorkflow

        assert ContractCloneWorkflow is not None


class TestFilingNumberWorkflow:
    """contracts/services/contract/admin/workflows/filing_number_workflow.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.admin.workflows.filing_number_workflow import ContractFilingNumberWorkflow

        assert ContractFilingNumberWorkflow is not None


# ── Override Service ────────────────────────────────────────────────────────


class TestOverrideServiceExtended:
    """More override_service tests."""

    @patch("apps.contracts.services.archive.override_service.ArchivePlaceholderOverride")
    def test_get_override_with_empty_template_subtype(self, mock_model: Any) -> None:
        from apps.contracts.services.archive.override_service import get_override

        mock_model.objects.filter.return_value.first.return_value = None
        result = get_override(1, "")
        assert result is None


# ── Composition Usecase ─────────────────────────────────────────────────────


class TestCompositionExtended:
    """composition.py extended tests."""

    @patch("apps.contracts.services.contract.usecases.composition.ContractService")
    @patch("apps.contracts.services.contract.usecases.composition.ContractQueryFacade")
    @patch("apps.contracts.services.contract.usecases.composition.ContractAccessPolicy")
    @patch("apps.contracts.services.contract.usecases.composition.ContractQueryService")
    def test_build_without_services(self, MockQS: Any, MockAP: Any, MockQF: Any, MockCS: Any) -> None:
        from apps.contracts.services.contract.usecases.composition import build_contract_service

        mock_instance = MagicMock()
        MockCS.return_value = mock_instance
        with patch(
            "apps.contracts.services.assignment.lawyer_assignment_service.LawyerAssignmentService"
        ):
            result = build_contract_service(case_service=None, lawyer_service=None)
            assert result is not None


# ── Supplementary Agreement Wiring ──────────────────────────────────────────


class TestSupplementaryWiring:
    """supplementary/wiring.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.supplementary.wiring import get_client_service

        assert callable(get_client_service)
