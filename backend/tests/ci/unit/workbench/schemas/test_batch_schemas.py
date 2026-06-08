"""Tests for workbench.schemas.batch_schemas."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from apps.workbench.schemas.batch_schemas import (
    BatchItemOut,
    BatchJobOut,
    BatchProgressOut,
)


class TestBatchItemOut:
    def test_from_dict(self) -> None:
        item = BatchItemOut(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            file_name="test.pdf",
            status="completed",
            result="analysis result",
            error="",
            duration_ms=1500.0,
        )
        assert item.file_name == "test.pdf"
        assert item.status == "completed"
        assert item.duration_ms == 1500.0

    def test_none_duration(self) -> None:
        item = BatchItemOut(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            file_name="test.pdf",
            status="pending",
            result="",
            error="",
            duration_ms=None,
        )
        assert item.duration_ms is None


class TestBatchJobOut:
    def test_file_field_validator_none(self) -> None:
        result = BatchJobOut._resolve_file_field(None)
        assert result == ""

    def test_file_field_validator_empty(self) -> None:
        result = BatchJobOut._resolve_file_field("")
        assert result == ""

    def test_resolve_created_at_none(self) -> None:
        result = BatchJobOut.resolve_created_at(MagicMock(created_at=None))
        assert result is None

    def test_resolve_updated_at_none(self) -> None:
        result = BatchJobOut.resolve_updated_at(MagicMock(updated_at=None))
        assert result is None

    def test_resolve_started_at_none(self) -> None:
        result = BatchJobOut.resolve_started_at(MagicMock(started_at=None))
        assert result is None

    def test_resolve_finished_at_none(self) -> None:
        result = BatchJobOut.resolve_finished_at(MagicMock(finished_at=None))
        assert result is None

    def test_resolve_started_processing_at_none(self) -> None:
        result = BatchJobOut.resolve_started_processing_at(MagicMock(started_processing_at=None))
        assert result is None


class TestBatchProgressOut:
    def test_default_failed_items_detail(self) -> None:
        job = BatchJobOut(
            id=UUID("12345678-1234-5678-1234-567812345678"),
            session_id=1,
            job_type="analysis",
            status="completed",
            prompt="test",
            llm_model="gpt-4",
            total_items=10,
            completed_items=8,
            failed_items=2,
            progress=100,
            summary="done",
            error_message="",
        )
        progress = BatchProgressOut(job=job, items=[])
        assert progress.failed_items_detail == []
