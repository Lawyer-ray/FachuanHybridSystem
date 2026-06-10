"""Batch7 coverage tests for apps.batch_printing."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.batch_printing.schemas import (
    BatchPrintItemOut,
    BatchPrintJobOut,
    BatchPrintJobSummaryOut,
    BatchPrintSubmitOut,
    CapabilityOut,
    PresetSyncOut,
    PrintKeywordRuleIn,
    PrintKeywordRuleOut,
    PrintKeywordRuleUpdateIn,
    PrintPresetSnapshotOut,
)


# ── CapabilityOut ───────────────────────────────────────────────────────────


class TestCapabilityOut:
    def test_basic(self) -> None:
        cap = CapabilityOut(docx_supported=True, docx_converter="libreoffice")
        assert cap.docx_supported is True
        assert cap.docx_converter == "libreoffice"


# ── PresetSyncOut ───────────────────────────────────────────────────────────


class TestPresetSyncOut:
    def test_basic(self) -> None:
        sync = PresetSyncOut(discovered=5, upserted=3)
        assert sync.discovered == 5
        assert sync.upserted == 3


# ── PrintPresetSnapshotOut ──────────────────────────────────────────────────


class TestPrintPresetSnapshotOut:
    def test_defaults(self) -> None:
        now = datetime.now()
        snap = PrintPresetSnapshotOut(
            id=1,
            printer_name="HP",
            printer_display_name="HP Printer",
            preset_name="default",
            preset_source="cups",
            last_synced_at=now,
            created_at=now,
            updated_at=now,
        )
        assert snap.raw_settings_payload == {}
        assert snap.executable_options_payload == {}
        assert snap.supported_option_names == []
        assert snap.rule_count == 0


# ── PrintKeywordRuleIn ──────────────────────────────────────────────────────


class TestPrintKeywordRuleIn:
    def test_defaults(self) -> None:
        rule = PrintKeywordRuleIn(keyword="起诉状", preset_snapshot_id=1)
        assert rule.priority == 100
        assert rule.enabled is True
        assert rule.notes == ""

    def test_custom_values(self) -> None:
        rule = PrintKeywordRuleIn(
            keyword="判决书", priority=50, enabled=False, preset_snapshot_id=2, notes="test"
        )
        assert rule.keyword == "判决书"
        assert rule.priority == 50


# ── PrintKeywordRuleUpdateIn ────────────────────────────────────────────────


class TestPrintKeywordRuleUpdateIn:
    def test_all_none(self) -> None:
        update = PrintKeywordRuleUpdateIn()
        assert update.keyword is None
        assert update.priority is None


# ── PrintKeywordRuleOut ─────────────────────────────────────────────────────


class TestPrintKeywordRuleOut:
    def test_basic(self) -> None:
        now = datetime.now()
        rule = PrintKeywordRuleOut(
            id=1,
            keyword="起诉状",
            priority=100,
            enabled=True,
            printer_name="HP",
            preset_snapshot_id=1,
            preset_snapshot_name="default",
            preset_printer_name="HP",
            notes="",
            created_at=now,
            updated_at=now,
        )
        assert rule.keyword == "起诉状"


# ── BatchPrintSubmitOut ─────────────────────────────────────────────────────


class TestBatchPrintSubmitOut:
    def test_basic(self) -> None:
        out = BatchPrintSubmitOut(job_id="abc-123", status="pending")
        assert out.job_id == "abc-123"


# ── BatchPrintItemOut ───────────────────────────────────────────────────────


class TestBatchPrintItemOut:
    def test_defaults(self) -> None:
        item = BatchPrintItemOut(
            id=1,
            order=1,
            filename="test.pdf",
            source_relpath="/test.pdf",
            prepared_relpath="/prepared/test.pdf",
            file_type="pdf",
            status="pending",
            matched_keyword="起诉状",
            target_printer_name="HP",
            target_preset_name="default",
            cups_job_id="",
            error_message="",
        )
        assert item.matched_rule_id is None
        assert item.target_preset_id is None


# ── BatchPrintJobSummaryOut ─────────────────────────────────────────────────


class TestBatchPrintJobSummaryOut:
    def test_defaults(self) -> None:
        now = datetime.now()
        job = BatchPrintJobSummaryOut(
            job_id="abc-123",
            status="pending",
            total_count=10,
            processed_count=0,
            success_count=0,
            failed_count=0,
            progress=0,
            cancel_requested=False,
            task_id="",
            created_by_name="admin",
            error_message="",
            created_at=now,
        )
        assert job.capability_payload == {}
        assert job.summary_payload == {}
        assert job.created_by_id is None


# ── BatchPrintJobOut ────────────────────────────────────────────────────────


class TestBatchPrintJobOut:
    def test_items_default(self) -> None:
        now = datetime.now()
        job = BatchPrintJobOut(
            job_id="abc-123",
            status="pending",
            total_count=0,
            processed_count=0,
            success_count=0,
            failed_count=0,
            progress=0,
            cancel_requested=False,
            task_id="",
            created_by_name="admin",
            error_message="",
            created_at=now,
        )
        assert job.items == []
