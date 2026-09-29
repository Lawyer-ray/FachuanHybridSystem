"""CourtSMSDocumentReferenceService.collect 的内容级去重测试。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService


def _sms_with_task_result(renamed_files: list[str]) -> SimpleNamespace:
    """collect 只访问属性，用鸭子类型构造最小 sms（scraper_task 不带 documents 属性）。"""
    return SimpleNamespace(
        scraper_task=SimpleNamespace(result={"renamed_files": renamed_files}),
        document_file_paths=[],
        case_log=None,
    )


def test_collect_dedupes_identical_content_copies(tmp_path):
    """归档副本（重名加 _N 后缀、不同目录、内容相同）不重复出现。"""
    svc = CourtSMSDocumentReferenceService()
    original = tmp_path / "告知书.pdf"
    original.write_bytes(b"%PDF-1.4 same-content")
    copy_dir = tmp_path / "case_logs"
    copy_dir.mkdir()
    archived_copy = copy_dir / "告知书_1.pdf"
    archived_copy.write_bytes(b"%PDF-1.4 same-content")
    other = tmp_path / "民事裁定书.pdf"
    other.write_bytes(b"%PDF-1.4 other-document")

    refs = svc.collect(_sms_with_task_result([str(original), str(archived_copy), str(other)]))

    assert [r.display_name for r in refs] == ["告知书.pdf", "民事裁定书.pdf"]


def test_collect_keeps_distinct_documents_with_same_name(tmp_path):
    """不同内容、同名文件（不同目录）都要保留——文件名去重只拦同目录场景？不：名字相同即拦。

    现有语义是同名只保留先收集到的（seen_names），此处验证该语义未被哈希去重破坏。
    """
    svc = CourtSMSDocumentReferenceService()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    file_a = dir_a / "同名.pdf"
    file_a.write_bytes(b"%PDF-1.4 aaa")
    file_b = dir_b / "同名.pdf"
    file_b.write_bytes(b"%PDF-1.4 bbb")

    refs = svc.collect(_sms_with_task_result([str(file_a), str(file_b)]))

    assert [r.display_name for r in refs] == ["同名.pdf"]


def test_collect_missing_file_is_skipped(tmp_path):
    """result 里登记的路径已不存在时跳过，不抛错。"""
    svc = CourtSMSDocumentReferenceService()
    refs = svc.collect(_sms_with_task_result([str(tmp_path / "不存在.pdf")]))
    assert refs == []
