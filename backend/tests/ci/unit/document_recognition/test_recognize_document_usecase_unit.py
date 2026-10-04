"""RecognizeCourtDocumentUsecase 单元测试 — 识别编排、关键信息提取与绑定分支。

依赖（提取/分类/提取器/绑定服务/重命名）全部注入 mock，重命名用真实临时文件。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.document_recognition.services.data_classes import DocumentType
from apps.document_recognition.usecases.court_document_recognition.recognize_document import (
    RecognizeCourtDocumentUsecase,
)


def _extraction(text: str = "（2026）粤0604民初1号", success: bool = True, method: str = "pdf_direct") -> Any:
    return SimpleNamespace(text=text, success=success, extraction_method=method)


def _usecase(
    *,
    extraction: Any = None,
    doc_type: DocumentType = DocumentType.SUMMONS,
    confidence: float = 0.9,
    summons_info: dict[str, Any] | None = None,
    execution_info: dict[str, Any] | None = None,
    case_id: int | None = 5,
    case_name: str | None = "张三与李四合同纠纷",
    renamed: str | None = None,
) -> tuple[RecognizeCourtDocumentUsecase, dict[str, MagicMock]]:
    extraction = extraction if extraction is not None else _extraction()
    classifier = MagicMock()
    classifier.classify.return_value = (doc_type, confidence)
    extractor = MagicMock()
    extractor.extract_summons_info.return_value = (
        summons_info
        if summons_info is not None
        else {
            "case_number": "（2026）粤0604民初1号",
            "court_time": None,
        }
    )
    extractor.extract_execution_info.return_value = (
        execution_info
        if execution_info is not None
        else {
            "case_number": "（2026）粤0604执1号",
            "preservation_deadline": None,
        }
    )
    case_service = MagicMock()
    if case_id is not None:
        dto = SimpleNamespace(name=case_name) if case_name else None
        case_service.get_case_by_id_internal.return_value = dto
    binding_service = MagicMock()
    binding_service.find_case_by_number.return_value = case_id
    binding_service.case_service = case_service
    binding_service.format_log_content.return_value = "日志内容"
    binding_service.bind_document_to_case.return_value = SimpleNamespace(success=True, case_id=case_id)
    renamer = MagicMock()
    renamer.generate_filename.return_value = renamed or "传票_张三与李四合同纠纷_2026-10-05.pdf"
    deps = {
        "text_extraction": MagicMock(extract_text=MagicMock(return_value=extraction)),
        "classifier": classifier,
        "extractor": extractor,
        "binding_service": binding_service,
        "document_renamer": renamer,
    }
    usecase = RecognizeCourtDocumentUsecase(**deps)
    return usecase, deps


class TestExecuteHappyPath:
    def test_summons_full_pipeline_with_rename(self, tmp_path: Path) -> None:
        src = tmp_path / "upload.pdf"
        src.write_bytes(b"%PDF")
        usecase, deps = _usecase()

        response = usecase.execute(file_path=str(src), user=None)

        # 提取与分类
        deps["text_extraction"].extract_text.assert_called_once_with(str(src))
        deps["classifier"].classify.assert_called_once()
        # 案号/时间来自 extractor
        deps["extractor"].extract_summons_info.assert_called_once()
        assert response.recognition.document_type is DocumentType.SUMMONS
        assert response.recognition.case_number == "（2026）粤0604民初1号"
        assert response.recognition.confidence == 0.9
        assert response.recognition.extraction_method == "pdf_direct"
        # 重命名发生且文件被移动
        assert response.file_path != str(src)
        assert not src.exists()
        assert Path(response.file_path).is_file()
        # 绑定链路
        deps["binding_service"].find_case_by_number.assert_called_once_with("（2026）粤0604民初1号")
        deps["binding_service"].bind_document_to_case.assert_called_once()

    def test_rename_failure_keeps_original_path(self, tmp_path: Path) -> None:
        src = tmp_path / "upload.pdf"
        src.write_bytes(b"%PDF")
        usecase, deps = _usecase()
        deps["document_renamer"].generate_filename.side_effect = RuntimeError("生成文件名失败")

        response = usecase.execute(file_path=str(src))

        assert response.file_path == str(src)
        assert src.exists()
        # 绑定仍然继续
        assert response.binding.success is True

    def test_case_dto_missing_skips_rename(self, tmp_path: Path) -> None:
        src = tmp_path / "upload.pdf"
        src.write_bytes(b"%PDF")
        usecase, deps = _usecase(case_name=None)

        response = usecase.execute(file_path=str(src))

        assert response.file_path == str(src)
        deps["document_renamer"].generate_filename.assert_not_called()


class TestExecuteExtractionFailure:
    def test_empty_text_returns_empty_response(self) -> None:
        usecase, deps = _usecase(extraction=_extraction(text="  ", success=False, method="ocr"))
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.recognition.document_type is DocumentType.OTHER
        assert response.recognition.raw_text == ""
        assert response.recognition.confidence == 0.0
        assert response.binding.success is False
        assert response.binding.error_code == "TEXT_EXTRACTION_FAILED"
        assert response.file_path == "/tmp/x.pdf"
        deps["classifier"].classify.assert_not_called()

    def test_success_false_returns_empty_response(self) -> None:
        usecase, _ = _usecase(extraction=_extraction(success=False))
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.binding.error_code == "TEXT_EXTRACTION_FAILED"


class TestExecuteBindingBranches:
    def test_summons_without_case_number(self) -> None:
        usecase, _ = _usecase(summons_info={"case_number": None, "court_time": None})
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.binding.error_code == "CASE_NUMBER_NOT_FOUND"
        assert response.file_path == "/tmp/x.pdf"

    def test_case_not_found(self) -> None:
        usecase, _ = _usecase(case_id=None)
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.binding.error_code == "CASE_NOT_FOUND"

    def test_execution_ruling_unsupported_message(self) -> None:
        usecase, _ = _usecase(doc_type=DocumentType.EXECUTION_RULING)
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.binding.success is False
        assert response.binding.error_code == "FEATURE_NOT_IMPLEMENTED"
        assert "执行裁定书绑定功能开发中" in response.binding.message

    def test_other_type_unsupported_message(self) -> None:
        usecase, _ = _usecase(doc_type=DocumentType.OTHER)
        response = usecase.execute(file_path="/tmp/x.pdf")
        assert response.binding.error_code == "UNSUPPORTED_DOCUMENT_TYPE"
        assert "暂时只支持传票识别" in response.binding.message


class TestExtractKeyInfo:
    def test_summons_uses_summons_extractor(self) -> None:
        usecase, deps = _usecase()
        case_number, key_time = usecase._extract_key_info(DocumentType.SUMMONS, "文本")
        deps["extractor"].extract_summons_info.assert_called_once_with("文本")
        assert case_number == "（2026）粤0604民初1号"

    def test_execution_uses_execution_extractor(self) -> None:
        usecase, deps = _usecase()
        case_number, deadline = usecase._extract_key_info(DocumentType.EXECUTION_RULING, "文本")
        deps["extractor"].extract_execution_info.assert_called_once_with("文本")
        assert case_number == "（2026）粤0604执1号"

    def test_other_type_returns_none_pair(self) -> None:
        usecase, deps = _usecase()
        assert usecase._extract_key_info(DocumentType.OTHER, "文本") == (None, None)
        deps["extractor"].extract_summons_info.assert_not_called()


class TestExecuteExceptionPropagation:
    def test_validation_exception_reraised_as_is(self) -> None:
        usecase, deps = _usecase()
        deps["text_extraction"].extract_text.side_effect = ValidationException(
            message="文件不存在", code="FILE_NOT_FOUND", errors={}
        )
        with pytest.raises(ValidationException):
            usecase.execute(file_path="/tmp/x.pdf")

    def test_unexpected_exception_reraised(self) -> None:
        usecase, deps = _usecase()
        deps["classifier"].classify.side_effect = RuntimeError("分类器崩溃")
        with pytest.raises(RuntimeError, match="分类器崩溃"):
            usecase.execute(file_path="/tmp/x.pdf")


class TestRenameDocument:
    def test_rename_moves_file_and_returns_new_path(self, tmp_path: Path) -> None:
        src = tmp_path / "orig.pdf"
        src.write_bytes(b"%PDF")
        usecase, deps = _usecase()

        new_path = usecase._rename_document(file_path=str(src), document_type=DocumentType.SUMMONS, case_name="案件A")

        assert not src.exists()
        assert Path(new_path).is_file()
        title_arg = deps["document_renamer"].generate_filename.call_args.kwargs["title"]
        assert title_arg == "传票"
        assert deps["document_renamer"].generate_filename.call_args.kwargs["case_name"] == "案件A"

    def test_rename_title_map_for_execution(self, tmp_path: Path) -> None:
        src = tmp_path / "orig.pdf"
        src.write_bytes(b"%PDF")
        usecase, deps = _usecase()
        usecase._rename_document(file_path=str(src), document_type=DocumentType.EXECUTION_RULING, case_name="案件B")
        assert deps["document_renamer"].generate_filename.call_args.kwargs["title"] == "执行裁定书"

    def test_rename_failure_returns_original(self, tmp_path: Path) -> None:
        usecase, deps = _usecase()
        deps["document_renamer"].generate_filename.side_effect = ValueError("bad name")
        result = usecase._rename_document(
            file_path=str(tmp_path / "orig.pdf"), document_type=DocumentType.SUMMONS, case_name="案件C"
        )
        assert result == str(tmp_path / "orig.pdf")
