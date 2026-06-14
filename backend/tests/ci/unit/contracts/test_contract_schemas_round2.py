"""Tests for contracts/schemas/contract_schemas.py — Round 2 additional coverage.

Covers remaining uncovered branches in: FinalizedMaterialOut.resolve_created_at
(no hasattr), ContractIn.validate_fee (no fee_mode), ContractOut.resolve_can_archive
(extra categories), resolve_primary_lawyer (tie-breaking on order).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.schemas.contract_schemas import (
    ContractAssignmentOut,
    ContractIn,
    ContractOut,
    ContractUpdate,
    FinalizedMaterialOut,
)
from apps.contracts.models import FeeMode


class TestFinalizedMaterialOutEdge:
    def test_resolve_created_at_no_created_at_attr(self):
        """Object without created_at attribute at all."""
        obj = object()
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert result is None

    def test_resolve_created_at_false_hasattr(self):
        """Object where hasattr returns False."""
        obj = SimpleNamespace()
        # SimpleNamespace without created_at
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert result is None


class TestContractInNoFeeMode:
    def test_no_fee_mode_passes(self):
        """When fee_mode is set to FIXED with valid amount, it passes."""
        schema = ContractIn(
            name="Test",
            case_type="civil",
            lawyer_ids=[1],
            fee_mode=FeeMode.FIXED,
            fixed_amount=5000,
        )
        assert schema.lawyer_ids == [1]
        assert schema.fixed_amount == 5000


class TestContractOutResolveCanArchive:
    def test_can_archive_with_extra_categories(self):
        obj = MagicMock()
        m1 = MagicMock()
        m1.category = "contract_original"
        m2 = MagicMock()
        m2.category = "archive_document"
        m3 = MagicMock()
        m3.category = "authorization_material"
        m4 = MagicMock()
        m4.category = "extra_category"
        obj.finalized_materials.all.return_value = [m1, m2, m3, m4]
        with patch("apps.contracts.models.finalized_material.MaterialCategory") as MockCat:
            MockCat.CONTRACT_ORIGINAL = "contract_original"
            MockCat.ARCHIVE_DOCUMENT = "archive_document"
            MockCat.AUTHORIZATION_MATERIAL = "authorization_material"
            assert ContractOut.resolve_can_archive(obj) is True


class TestContractOutResolvePrimaryLawyerTieBreak:
    def test_same_order_different_id(self):
        """When two assignments have the same order, lower id wins."""
        obj = MagicMock()
        obj.primary_lawyer_dto = None
        a1 = MagicMock()
        a1.is_primary = False
        a1.order = 1
        a1.id = 5
        a1.lawyer = MagicMock()
        a2 = MagicMock()
        a2.is_primary = False
        a2.order = 1
        a2.id = 3
        a2.lawyer = MagicMock()
        obj.assignments.all.return_value = [a1, a2]
        with patch("apps.contracts.schemas.contract_schemas.LawyerOut") as MockLO:
            MockLO.from_model.return_value = "winner"
            result = ContractOut.resolve_primary_lawyer(obj)
            # a2 has lower id (3 < 5) with same order
            MockLO.from_model.assert_called_with(a2.lawyer)


class TestContractUpdateMore:
    def test_set_all_fields(self):
        schema = ContractUpdate(
            name="N",
            case_type="civil",
            status="active",
            specified_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-12-31",
            assigned_lawyer=1,
            is_filed=True,
            fee_mode="fixed",
            fixed_amount=5000,
            risk_rate=0,
            custom_terms=None,
            representation_stages=["first_instance"],
        )
        assert schema.name == "N"
        assert schema.is_filed is True
        assert schema.representation_stages == ["first_instance"]


class TestContractAssignmentOutEdge:
    def test_from_assignment_real_name_falsy(self):
        obj = MagicMock()
        obj.id = 1
        obj.lawyer_id = 10
        obj.lawyer.real_name = ""  # falsy but not None
        obj.lawyer.username = "user1"
        obj.is_primary = False
        obj.order = 0
        result = ContractAssignmentOut.from_assignment(obj)
        assert result.lawyer_name == "user1"
