"""Tests for doc_converter services."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import uuid


class TestDocConverterServiceValidateFile:
    def _make_service(self):
        from apps.doc_converter.services.converter_service import DocConverterService
        return DocConverterService()

    def test_valid_doc_file(self):
        svc = self._make_service()
        f = MagicMock()
        f.name = "test.doc"
        f.size = 1024
        svc._validate_file(f)

    def test_invalid_extension(self):
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        f = MagicMock()
        f.name = "test.pdf"
        f.size = 1024
        with pytest.raises(ValidationException):
            svc._validate_file(f)

    def test_empty_file(self):
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        f = MagicMock()
        f.name = "test.doc"
        f.size = 0
        with pytest.raises(ValidationException):
            svc._validate_file(f)

    def test_too_large_file(self):
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        f = MagicMock()
        f.name = "test.doc"
        f.size = 100 * 1024 * 1024
        with pytest.raises(ValidationException):
            svc._validate_file(f)


class TestDocConverterServiceBuildPayload:
    def test_build_job_payload(self):
        from apps.doc_converter.services.converter_service import DocConverterService
        from apps.doc_converter.models import DocConverterJobStatus
        svc = DocConverterService()
        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = DocConverterJobStatus.PENDING
        job.total_files = 1
        job.converted_files = 0
        job.failed_files = 0
        job.progress = 0
        job.error_message = ""
        job.output_zip = ""
        job.created_at = None
        job.finished_at = None
        payload = svc.build_job_payload(job)
        assert payload["status"] == DocConverterJobStatus.PENDING
        assert payload["total_files"] == 1

    def test_build_item_payload(self):
        from apps.doc_converter.services.converter_service import DocConverterService
        svc = DocConverterService()
        item = MagicMock()
        item.id = 1
        item.original_name = "test.doc"
        item.status = "pending"
        item.error = ""
        item.duration_ms = 0
        payload = svc.build_item_payload(item)
        assert payload["original_name"] == "test.doc"
