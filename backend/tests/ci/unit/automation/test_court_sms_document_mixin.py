from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin


class _DummySMSDocumentMixin(SMSDocumentMixin):
    def __init__(self) -> None:
        self._document_attachment = Mock()
        self._matcher = Mock()
        self._case_number_extractor = Mock()
        self._case_folder_archive = Mock()
        self._create_case_binding = Mock(return_value=True)

    @property
    def document_attachment(self):  # type: ignore[override]
        return self._document_attachment

    @property
    def matcher(self):  # type: ignore[override]
        return self._matcher

    @property
    def case_number_extractor(self):  # type: ignore[override]
        return self._case_number_extractor

    @property
    def case_folder_archive(self):  # type: ignore[override]
        return self._case_folder_archive


def test_save_renamed_paths_persists_recommendation_mapping() -> None:
    mixin = _DummySMSDocumentMixin()
    mixin._document_attachment.RESULT_RECOMMENDATION_NAMES_KEY = "recommendation_names_by_path"
    scraper_task = SimpleNamespace(result={}, save=Mock())
    sms = SimpleNamespace(scraper_task=scraper_task)

    mixin._save_renamed_paths(
        sms,
        ["D:/tmp/renamed.pdf"],
        recommendation_names_by_path={"D:/tmp/renamed.pdf": "瀵规柟璇佹嵁鐩綍.pdf"},
    )

    assert scraper_task.result["renamed_files"] == ["D:/tmp/renamed.pdf"]
    assert scraper_task.result["recommendation_names_by_path"] == {
        "D:/tmp/renamed.pdf": "瀵规柟璇佹嵁鐩綍.pdf"
    }
    scraper_task.save.assert_called_once_with()


def test_attach_to_case_log_reuses_precomputed_recommendation_mapping() -> None:
    mixin = _DummySMSDocumentMixin()
    recommendation_names_by_path = {"D:/tmp/renamed.pdf": "瀵规柟璇佹嵁鐩綍.pdf"}
    sms = SimpleNamespace(case_log=SimpleNamespace(id=1), case=None, id=1)

    mixin._attach_to_case_log(
        sms,
        ["D:/tmp/renamed.pdf"],
        recommendation_names_by_path=recommendation_names_by_path,
    )

    mixin._document_attachment.add_to_case_log.assert_called_once_with(
        sms,
        ["D:/tmp/renamed.pdf"],
        recommendation_names_by_path=recommendation_names_by_path,
    )
    mixin._document_attachment.build_recommendation_names_for_paths.assert_not_called()
