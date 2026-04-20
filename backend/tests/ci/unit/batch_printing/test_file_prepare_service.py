from __future__ import annotations

import shutil
from pathlib import Path

from apps.batch_printing.services.file_prepare_service import FilePrepareService


def test_resolve_soffice_path_prefers_path_command(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: "/opt/homebrew/bin/soffice" if cmd == "soffice" else None)

    service = FilePrepareService()

    assert service._resolve_soffice_path() == "/opt/homebrew/bin/soffice"


def test_resolve_soffice_path_falls_back_to_macos_app_bundle(tmp_path: Path, monkeypatch) -> None:
    fake_soffice = tmp_path / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    fake_soffice.parent.mkdir(parents=True, exist_ok=True)
    fake_soffice.write_text("binary")
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    monkeypatch.setattr(
        FilePrepareService,
        "_candidate_soffice_paths",
        lambda self: (fake_soffice,),
    )

    service = FilePrepareService()

    assert service._resolve_soffice_path() == str(fake_soffice)
    assert service.get_capability_snapshot() == {
        "docx_supported": True,
        "docx_converter": str(fake_soffice),
    }
