"""Unit tests for case_contract_export_bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.cases.services.case.case_contract_export_bridge import (
    collect_contract_file_paths_for_case_export,
    get_case_admin_contract_export_prefetches,
    get_case_admin_contract_file_prefetches,
    serialize_contract_for_case_export,
)


def test_get_case_admin_contract_export_prefetches_returns_nonempty_tuple() -> None:
    result = get_case_admin_contract_export_prefetches()
    assert isinstance(result, tuple)
    assert len(result) > 0


def test_get_case_admin_contract_file_prefetches_returns_nonempty_tuple() -> None:
    result = get_case_admin_contract_file_prefetches()
    assert isinstance(result, tuple)
    assert len(result) > 0


def test_collect_contract_file_paths_for_case_export_collects_all_paths() -> None:
    material = MagicMock()
    material.file_path = "material.pdf"

    identity_doc = MagicMock()
    identity_doc.file_path = "id.pdf"

    clue_attachment = MagicMock()
    clue_attachment.file_path = "clue.pdf"

    clue = MagicMock()
    clue.attachments.all.return_value = [clue_attachment]

    client = MagicMock()
    client.identity_docs.all.return_value = [identity_doc]
    client.property_clues.all.return_value = [clue]

    party = MagicMock()
    party.client = client

    contract = MagicMock()
    contract.finalized_materials.all.return_value = [material]
    contract.contract_parties.all.return_value = [party]

    collected: list[str] = []
    collect_contract_file_paths_for_case_export(contract, collected.append)

    assert "material.pdf" in collected
    assert "id.pdf" in collected
    assert "clue.pdf" in collected


def test_serialize_contract_for_case_export_calls_serializer() -> None:
    contract = MagicMock()
    expected = {"id": 1, "name": "test"}

    with (
        patch(
            "apps.cases.services.case.case_export_serializer_service.serialize_case_obj"
        ) as mock_case_ser,
        patch(
            "apps.contracts.services.contract.contract_export_serializer_service.serialize_contract_obj"
        ) as mock_contract_ser,
    ):
        mock_contract_ser.return_value = expected
        result = serialize_contract_for_case_export(contract)

    mock_contract_ser.assert_called_once_with(contract, case_serializer=mock_case_ser)
    assert result == expected
