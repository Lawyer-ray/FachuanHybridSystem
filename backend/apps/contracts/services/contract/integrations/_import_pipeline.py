"""合同扫描导入流水线：候选文件确认导入 + 工作日志写入。"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.contracts.models import (
    ContractFolderScanSession,
    ContractFolderScanStatus,
    FinalizedMaterial,
    MaterialCategory,
)
from apps.core.exceptions import ValidationException

from .file_hash_utils import compute_file_hash_from_bytes
from .material_service import MaterialService
from .quality_card_detector import has_quality_card_on_last_page

logger = logging.getLogger(__name__)


class ImportPipeline:
    """合同扫描确认导入流水线。"""

    _QUALITY_CARD_TITLE = "合同正本与律师办案服务质量监督卡"

    def __init__(self) -> None:
        self._material_service = MaterialService()

    @transaction.atomic
    def confirm_import(
        self,
        *,
        contract_id: int,
        session: ContractFolderScanSession,
        items: list[dict[str, Any]],
        work_log_suggestions: list[dict[str, str]] | None = None,
        storage_provider: Any | None = None,
        learn_from_correction_fn: Any | None = None,
    ) -> dict[str, Any]:
        if session.status == ContractFolderScanStatus.IMPORTED:
            raise ValidationException(message="该扫描已导入，请重新扫描", errors={"status": session.status})
        if session.status != ContractFolderScanStatus.COMPLETED:
            raise ValidationException(message="扫描尚未完成", errors={"status": session.status})

        payload = dict(session.result_payload or {})
        candidates = payload.get("candidates") or []
        candidate_map = {str(item.get("source_path") or ""): item for item in candidates}

        imported_count = 0
        skipped_dupes = 0
        for item in items:
            if not bool(item.get("selected", True)):
                continue

            source_path = str(item.get("source_path") or "").strip()
            if not source_path or source_path not in candidate_map:
                raise ValidationException(message="候选文件不存在", errors={"source_path": source_path})

            category = str(item.get("category") or "archive_document").strip()
            if category not in {
                MaterialCategory.CONTRACT_ORIGINAL,
                MaterialCategory.SUPPLEMENTARY_AGREEMENT,
                MaterialCategory.INVOICE,
                MaterialCategory.SUPERVISION_CARD,
                MaterialCategory.CASE_MATERIAL,
            }:
                category = MaterialCategory.CASE_MATERIAL

            is_docx = bool(item.get("is_docx", False))
            archive_item_code = str(item.get("archive_item_code") or "").strip()

            # Read file content
            if storage_provider is not None:
                from apps.core.cloud_storage.exceptions import CloudStorageError

                try:
                    file_bytes = storage_provider.read_file(source_path)
                except CloudStorageError:
                    raise
                except Exception as e:
                    raise CloudStorageError(
                        f"读取云存储文件失败: {source_path}",
                        provider="云存储",
                    ) from e
                file_name = PurePosixPath(source_path).name
            else:
                file_path = Path(source_path)
                if not file_path.exists() or not file_path.is_file():
                    raise ValidationException(message="源文件不存在", errors={"source_path": source_path})
                file_bytes = file_path.read_bytes()
                file_name = file_path.name

            temp_pdf_path: Path | None = None
            if is_docx:
                temp_pdf_path = self._convert_docx_to_temp_pdf_from_bytes(file_bytes, file_name)
                if temp_pdf_path is None:
                    logger.warning("docx_convert_failed_skip", extra={"source_path": source_path})
                    continue

            try:
                if temp_pdf_path is not None:
                    upload_content = temp_pdf_path.read_bytes()
                    upload_name = (
                        str(PurePosixPath(file_name).stem) + ".pdf" if storage_provider else temp_pdf_path.name
                    )
                else:
                    upload_content = file_bytes
                    upload_name = file_name

                upload = SimpleUploadedFile(
                    name=upload_name,
                    content=upload_content,
                    content_type="application/pdf",
                )
                rel_path, original_name = self._material_service.save_material_file(upload, contract_id)
                display_name = original_name
                if is_docx:
                    display_name = file_name

                if category == MaterialCategory.CONTRACT_ORIGINAL and not is_docx:
                    if storage_provider is not None:
                        import tempfile

                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                            tmp.write(file_bytes)
                            tmp_path = Path(tmp.name)
                        try:
                            quality_card = has_quality_card_on_last_page(tmp_path)
                        finally:
                            tmp_path.unlink(missing_ok=True)
                    else:
                        quality_card = has_quality_card_on_last_page(Path(source_path))
                    if quality_card:
                        display_name = self._QUALITY_CARD_TITLE

                material_kwargs: dict[str, Any] = {
                    "contract_id": contract_id,
                    "file_path": rel_path,
                    "original_filename": display_name,
                    "category": category,
                }
                if archive_item_code:
                    material_kwargs["archive_item_code"] = archive_item_code

                content_hash = compute_file_hash_from_bytes(file_bytes)
                if content_hash:
                    material_kwargs["content_hash"] = content_hash

                if (
                    content_hash
                    and FinalizedMaterial.objects.filter(
                        contract_id=contract_id,
                        content_hash=content_hash,
                    ).exists()
                ):
                    skipped_dupes += 1
                    logger.info(
                        "material_hash_duplicate_skipped",
                        extra={
                            "contract_id": contract_id,
                            "file_name": display_name,
                            "content_hash": content_hash[:16],
                        },
                    )
                    continue

                if (
                    not content_hash
                    and FinalizedMaterial.objects.filter(
                        contract_id=contract_id,
                        original_filename=display_name,
                        category=category,
                    ).exists()
                ):
                    skipped_dupes += 1
                    logger.info(
                        "material_name_duplicate_skipped",
                        extra={"contract_id": contract_id, "file_name": display_name, "category": category},
                    )
                    continue

                FinalizedMaterial.objects.create(**material_kwargs)
                imported_count += 1

                if learn_from_correction_fn is not None:
                    learn_from_correction_fn(
                        candidate=candidate_map[source_path],
                        actual_archive_item_code=archive_item_code,
                        contract_id=contract_id,
                    )
            finally:
                if temp_pdf_path and temp_pdf_path.exists():
                    temp_pdf_path.unlink(missing_ok=True)

        confirmed_logs = work_log_suggestions or []
        payload["import_result"] = {
            "imported_count": imported_count,
            "skipped_dupes": skipped_dupes,
            "imported_at": timezone.now().isoformat(),
        }
        payload["confirmed_work_log_suggestions"] = confirmed_logs

        work_log_imported = self._import_work_log_suggestions(
            contract_id=contract_id,
            confirmed_logs=confirmed_logs,
            actor_id=(session.started_by_id if session.started_by_id else None),
        )
        payload["import_result"]["work_log_imported"] = work_log_imported

        ContractFolderScanSession.objects.filter(id=session.id).update(
            status=ContractFolderScanStatus.IMPORTED,
            progress=100,
            current_file="",
            result_payload=payload,
            error_message="",
            updated_at=timezone.now(),
        )

        return {
            "session_id": str(session.id),
            "status": ContractFolderScanStatus.IMPORTED,
            "imported_count": imported_count,
            "work_log_imported": work_log_imported,
        }

    def _import_work_log_suggestions(
        self,
        *,
        contract_id: int,
        confirmed_logs: list[dict[str, str]],
        actor_id: int | None = None,
    ) -> int:
        """将确认的工作日志建议写入 CaseLog 模型，自动跳过已有相同内容的日志。"""
        if not confirmed_logs:
            return 0

        from apps.core.interfaces import ServiceLocator

        case_service = ServiceLocator.get_case_service()
        cases_dto = case_service.get_cases_by_contract(contract_id)
        if not cases_dto:
            logger.warning("work_log_import_no_case", extra={"contract_id": contract_id})
            return 0

        case_id = int(cases_dto[0].id)

        from apps.cases.models import CaseLog

        existing_contents: set[str] = set(CaseLog.objects.filter(case_id=case_id).values_list("content", flat=True))

        imported = 0
        for suggestion in confirmed_logs:
            content = str(suggestion.get("content") or "").strip()
            if not content:
                continue
            if content in existing_contents:
                logger.info("work_log_duplicate_skipped", extra={"case_id": case_id, "content": content})
                continue
            try:
                case_service.create_case_log_internal(
                    case_id=case_id,
                    content=content,
                    user_id=actor_id,
                )
                existing_contents.add(content)
                imported += 1
            except Exception:
                logger.exception(
                    "work_log_import_item_failed",
                    extra={"case_id": case_id, "content": content},
                )

        logger.info(
            "work_log_imported",
            extra={"contract_id": contract_id, "case_id": case_id, "count": imported},
        )
        return imported

    def _convert_docx_to_temp_pdf(self, file_path: Path) -> Path | None:
        """将本地 docx 文件转换为临时 PDF 文件。"""
        try:
            from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

            pdf_path_str = convert_docx_to_pdf(file_path.as_posix())
            if pdf_path_str:
                return Path(pdf_path_str)
            return None
        except (OSError, RuntimeError):
            logger.exception("docx_to_pdf_conversion_failed", extra={"path": file_path.as_posix()})
            return None

    def _convert_docx_to_temp_pdf_from_bytes(self, file_bytes: bytes, filename: str) -> Path | None:
        """将 docx bytes 转换为临时 PDF 文件。"""
        import tempfile

        try:
            from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(file_bytes)
                docx_path = tmp.name
            try:
                pdf_path_str = convert_docx_to_pdf(docx_path)
                if pdf_path_str:
                    return Path(pdf_path_str)
                return None
            finally:
                Path(docx_path).unlink(missing_ok=True)
        except (OSError, RuntimeError):
            logger.exception("docx_to_pdf_conversion_from_bytes_failed", extra={"file_name": filename})
            return None
