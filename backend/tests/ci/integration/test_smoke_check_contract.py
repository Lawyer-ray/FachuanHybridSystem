"""Integration contract tests for smoke_check command."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_smoke_check_validates_upload_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "ci_smoke.sqlite3"
    call_command(
        "smoke_check",
        database_path=str(db_path),
        skip_admin=True,
        skip_websocket=True,
        skip_q=True,
    )
