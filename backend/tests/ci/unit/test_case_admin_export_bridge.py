"""Unit tests for case_admin_export_bridge."""

from __future__ import annotations

from unittest.mock import MagicMock

from apps.cases.services.case.case_admin_export_bridge import (
    collect_case_file_paths_for_export,
    get_case_admin_export_prefetches,
    get_case_admin_file_prefetches,
)


def test_get_case_admin_export_prefetches_returns_nonempty_tuple() -> None:
    result = get_case_admin_export_prefetches()
    assert isinstance(result, tuple)
    assert len(result) > 0


def test_get_case_admin_file_prefetches_returns_nonempty_tuple() -> None:
    result = get_case_admin_file_prefetches()
    assert isinstance(result, tuple)
    assert len(result) > 0


def test_collect_case_file_paths_for_export_collects_identity_docs() -> None:
    identity_doc = MagicMock()
    identity_doc.file_path = "id_doc.pdf"

    clue_attachment = MagicMock()
    clue_attachment.file_path = "clue_attach.pdf"

    clue = MagicMock()
    clue.attachments.all.return_value = [clue_attachment]

    client = MagicMock()
    client.identity_docs.all.return_value = [identity_doc]
    client.property_clues.all.return_value = [clue]

    party = MagicMock()
    party.client = client

    log_attachment = MagicMock()
    log_attachment.file = MagicMock()
    log_attachment.file.name = "log_attach.pdf"

    log = MagicMock()
    log.attachments.all.return_value = [log_attachment]

    case = MagicMock()
    case.parties.all.return_value = [party]
    case.logs.all.return_value = [log]

    collected: list[str] = []
    collect_case_file_paths_for_export(case, collected.append)

    assert "id_doc.pdf" in collected
    assert "clue_attach.pdf" in collected
    assert "log_attach.pdf" in collected


def test_collect_case_file_paths_for_export_skips_log_attachment_without_file() -> None:
    client = MagicMock()
    client.identity_docs.all.return_value = []
    client.property_clues.all.return_value = []

    party = MagicMock()
    party.client = client

    log_attachment = MagicMock()
    log_attachment.file = None  # no file

    log = MagicMock()
    log.attachments.all.return_value = [log_attachment]

    case = MagicMock()
    case.parties.all.return_value = [party]
    case.logs.all.return_value = [log]

    collected: list[str] = []
    collect_case_file_paths_for_export(case, collected.append)

    assert collected == []
