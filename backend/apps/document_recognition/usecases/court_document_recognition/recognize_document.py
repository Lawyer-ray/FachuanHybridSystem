"""Module for recognize document."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    RecognitionResponse,
    RecognitionResult,
)
from apps.core.exceptions import RecognitionTimeoutError, ServiceUnavailableError, ValidationException

logger = logging.getLogger("apps.document_recognition")


@dataclass(frozen=True)
class RecognizeCourtDocumentUsecase:
    text_extraction: Any
    classifier: Any
    extractor: Any
    binding_service: Any
    document_renamer: Any

    def execute(self, *, file_path: str, user: Any | None = None) -> RecognitionResponse:
        logger.info("开始识别文书", extra={"action": "recognize_document", "file_path": file_path})
        try:
            extraction_result = self.text_extraction.extract_text(file_path)
            if not extraction_result.success or not extraction_result.text.strip():
                return self._empty_response(file_path, extraction_result)
            doc_type, confidence = self.classifier.classify(extraction_result.text)
            case_number, key_time = self._extract_key_info(doc_type, extraction_result.text)
            recognition = RecognitionResult(
                document_type=doc_type,
                case_number=case_number,
                key_time=key_time,
                raw_text=extraction_result.text,
                confidence=confidence,
                extraction_method=extraction_result.extraction_method,
            )
            binding, renamed_file_path = self._bind_document(
                doc_type, case_number, key_time, extraction_result.text, file_path, user
            )
            logger.info(
                "文书识别完成",
                extra={"action": "recognize_document", "document_type": doc_type.value, "case_number": case_number},
            )
            return RecognitionResponse(recognition=recognition, binding=binding, file_path=renamed_file_path)
        except (ValidationException, ServiceUnavailableError, RecognitionTimeoutError):
            raise
        except Exception:
            logger.error("文书识别失败", extra={"action": "recognize_document", "file_path": file_path}, exc_info=True)
            raise

    def _empty_response(self, file_path: Any, extraction_result: Any) -> RecognitionResponse:
        """文本提取失败时返回空结果"""
        return RecognitionResponse(
            recognition=RecognitionResult(
                document_type=DocumentType.OTHER,
                case_number=None,
                key_time=None,
                raw_text="",
                confidence=0.0,
                extraction_method=extraction_result.extraction_method,
            ),
            binding=BindingResult.failure_result(message="无法从文书中提取文字", error_code="TEXT_EXTRACTION_FAILED"),
            file_path=file_path,
        )

    def _extract_key_info(self, doc_type: Any, text: Any) -> tuple[Any, Any]:
        """根据文书类型提取案号和关键时间"""
        if doc_type == DocumentType.SUMMONS:
            info = self.extractor.extract_summons_info(text)
            return (info.get("case_number"), info.get("court_time"))
        if doc_type == DocumentType.EXECUTION_RULING:
            info = self.extractor.extract_execution_info(text)
            return (info.get("case_number"), info.get("preservation_deadline"))
        return (None, None)

    def _bind_document(
        self, doc_type: Any, case_number: Any, key_time: Any, raw_text: Any, file_path: Any, user: Any
    ) -> tuple[Any, Any]:
        """绑定文书到案件,返回 (binding, renamed_file_path)"""
        _UNSUPPORTED = {
            DocumentType.OTHER: ("暂时只支持传票识别,其他文书类型敬请期待", "UNSUPPORTED_DOCUMENT_TYPE"),
            DocumentType.EXECUTION_RULING: ("执行裁定书绑定功能开发中,敬请期待", "FEATURE_NOT_IMPLEMENTED"),
        }
        if doc_type != DocumentType.SUMMONS or not case_number:
            if not case_number and doc_type == DocumentType.SUMMONS:
                return (
                    BindingResult.failure_result(
                        message="未识别到案号,无法绑定案件", error_code="CASE_NUMBER_NOT_FOUND"
                    ),
                    file_path,
                )
            msg, code = _UNSUPPORTED.get(doc_type, ("不支持的文书类型", "UNSUPPORTED"))
            return (BindingResult.failure_result(message=msg, error_code=code), file_path)
        case_id = self.binding_service.find_case_by_number(case_number)
        case_name = None
        renamed_file_path = file_path
        if case_id:
            case_dto = self.binding_service.case_service.get_case_by_id_internal(case_id)
            if case_dto:
                case_name = case_dto.name
        if case_name:
            renamed_file_path = self._rename_document(file_path=file_path, document_type=doc_type, case_name=case_name)
        log_content = self.binding_service.format_log_content(
            document_type=doc_type, case_number=case_number, key_time=key_time, raw_text=raw_text
        )
        binding = self.binding_service.bind_document_to_case(
            case_number=case_number,
            document_type=doc_type,
            content=log_content,
            key_time=key_time,
            file_path=renamed_file_path,
            user=user,
        )
        return (binding, renamed_file_path)

    def _rename_document(self, *, file_path: str, document_type: DocumentType, case_name: str) -> str:
        try:
            title_map = {
                DocumentType.SUMMONS: "传票",
                DocumentType.EXECUTION_RULING: "执行裁定书",
                DocumentType.OTHER: "司法文书",
            }
            title = title_map.get(document_type, "司法文书")
            new_filename = self.document_renamer.generate_filename(
                title=title, case_name=case_name, received_date=date.today()
            )
            from apps.core.path import Path

            original_path = Path(file_path)
            new_path = original_path.parent / new_filename
            counter = 1
            while new_path.exists():
                base_filename = new_filename.replace("收.pdf", f"收{counter}.pdf")
                new_path = original_path.parent / base_filename
                counter += 1
                if counter > 100:
                    break
            original_path.rename(new_path)
            logger.info(
                "文书重命名成功",
                extra={
                    "action": "rename_document",
                    "original_path": file_path,
                    "new_path": str(new_path),
                    "document_type": document_type.value,
                    "case_name": case_name,
                },
            )
            return str(new_path)
        except Exception:
            logger.warning("文书重命名失败,保留原文件名", extra={})
            return file_path
