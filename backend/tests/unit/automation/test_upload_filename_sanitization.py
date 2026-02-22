from __future__ import annotations

from unittest.mock import Mock

import pytest

from apps.automation.api.fee_notice_extraction_api import extract_fee_notices
from apps.automation.api.preservation_date_extraction_api import extract_preservation_dates


class _Uploaded:
    def __init__(self, name: str):
        self.name = name

    def chunks(self):
        yield b"x"


def test_preservation_date_rejects_unsafe_filename(monkeypatch):
    monkeypatch.setattr(
        "apps.automation.api.preservation_date_extraction_api._get_extraction_service",
        lambda: Mock(),
    )
    monkeypatch.setattr(
        "builtins.open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not open"))
    )
    request = Mock()
    file = _Uploaded("../../evil.pdf")
    res = extract_preservation_dates(request, file=file)
    assert res.success is False
    assert "文件名" in (res.error or "")


def test_fee_notice_rejects_unsafe_filename(monkeypatch):
    service = Mock()
    service.extract_from_files.return_value = Mock(notices=[], errors=[], debug_logs=[])
    monkeypatch.setattr("apps.automation.api.fee_notice_extraction_api._get_extraction_service", lambda: service)
    monkeypatch.setattr(
        "builtins.open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not open"))
    )
    request = Mock()
    files = [_Uploaded("../evil.pdf")]
    res = extract_fee_notices(request, files=files, debug=False)  # type: ignore[arg-type]
    assert res.success is False
    assert res.errors
    assert res.errors[0]["code"] == "INVALID_FILE_NAME"
