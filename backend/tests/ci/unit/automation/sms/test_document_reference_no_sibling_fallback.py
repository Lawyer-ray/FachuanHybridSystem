"""P05-02 回归：记录路径不存在时不得按「同目录最新文件」兜底。

旧实现（`_normalize_existing_path`）先按 stem 前缀匹配、再取「同目录同后缀最新文件」
当成本文书。同目录躺着同一案件多次送达的多份文书时，猜出来的那份不是这条短信的
（2026-11-14 实测 57/63 条短信因此错配）。修法：找不到就返回 None + warning。
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService


def _make_sms(sms_id: int, paths: list[str]) -> Any:
    """只带 document_file_paths 的短信桩：不碰 scraper_task / case_log 分支。"""
    return SimpleNamespace(id=sms_id, document_file_paths=paths, scraper_task=None, case_log=None)


def test_missing_path_with_sibling_pdfs_returns_none(tmp_path: Path, caplog: Any) -> None:
    """同目录有多份同后缀 PDF 时必须返回 None，而不是随便挑一份最新的。"""
    (tmp_path / "民事调解书.pdf").write_bytes(b"first")
    (tmp_path / "判决书.pdf").write_bytes(b"second")
    service = CourtSMSDocumentReferenceService()
    target = tmp_path / "本次送达文书.pdf"

    with caplog.at_level(logging.WARNING):
        normalized = service._normalize_existing_path(str(target), sms_id=4242)

    assert normalized is None
    # warning 必须写明短信 id 与目标路径，便于定位是哪个引用丢了
    assert "4242" in caplog.text
    assert str(target) in caplog.text


def test_collect_skips_missing_reference_instead_of_guessing(tmp_path: Path) -> None:
    """collect 不得把同目录下别的文书当成本短信的文书返回。"""
    (tmp_path / "别的案件_判决书.pdf").write_bytes(b"other-1")
    (tmp_path / "别的案件_裁定书.pdf").write_bytes(b"other-2")
    service = CourtSMSDocumentReferenceService()
    sms = _make_sms(7, [str(tmp_path / "本短信引用的文书.pdf")])

    assert service.collect(sms) == []


def test_existing_path_is_returned_even_with_sibling_files(tmp_path: Path) -> None:
    """路径存在时仍然正常工作：返回的必须是它自己，不是 mtime 更新的邻居。"""
    target = tmp_path / "target.pdf"
    target.write_bytes(b"target")
    newer_sibling = tmp_path / "newer-sibling.pdf"
    newer_sibling.write_bytes(b"newer")
    service = CourtSMSDocumentReferenceService()

    normalized = service._normalize_existing_path(str(target), sms_id=1)

    assert normalized == target.resolve().as_posix()
    assert normalized != newer_sibling.resolve().as_posix()


def test_collect_keeps_existing_reference(tmp_path: Path) -> None:
    """存在性检查不能误伤正常引用（回归保护）。"""
    target = tmp_path / "本短信引用的文书.pdf"
    target.write_bytes(b"real")
    service = CourtSMSDocumentReferenceService()
    sms = _make_sms(8, [str(target)])

    refs = service.collect(sms)

    assert [ref.file_path for ref in refs] == [target.resolve().as_posix()]
    assert refs[0].source == "sms_reference"
