from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.automation.services.ocr.ocr_service import OCRService
from apps.automation.services.ocr.pdf_text_extractor import PDFTextExtractor
from apps.invoice_recognition.models import (
    InvoiceCategory,
    InvoiceRecognitionTask,
    InvoiceRecognitionTaskStatus,
    InvoiceRecord,
    InvoiceRecordStatus,
)

from .invoice_parser import InvoiceParser, ParsedInvoice

logger = logging.getLogger(__name__)


class InvoiceRecognitionService:
    """发票识别核心服务：任务管理、文件处理、OCR 调用、解析、去重、统计。"""

    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".pdf", ".jpg", ".jpeg", ".png"}
    MAX_FILE_SIZE: ClassVar[int] = 20 * 1024 * 1024  # 20 MB

    def __init__(
        self,
        ocr_service: OCRService,
        pdf_extractor: PDFTextExtractor,
        parser: InvoiceParser,
    ) -> None:
        self._ocr = ocr_service
        self._pdf_extractor = pdf_extractor
        self._parser = parser

    def _validate_file(self, file: UploadedFile) -> None:
        name: str = file.name or ""
        ext = Path(name).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(_("不支持的文件格式：%(ext)s，仅允许 PDF、JPG、JPEG、PNG。") % {"ext": ext})
        size: int = file.size or 0
        if size > self.MAX_FILE_SIZE:
            raise ValidationError(
                _("文件大小超过限制（最大 20 MB），当前文件大小：%(size).1f MB。") % {"size": size / 1024 / 1024}
            )

    def _save_file(self, task_id: int, file: UploadedFile) -> tuple[Path, str]:
        name: str = file.name or "unknown"
        ext = Path(name).suffix.lower()
        filename = f"{uuid.uuid4().hex}{ext}"

        save_dir = Path(settings.MEDIA_ROOT) / "automation" / "invoices" / str(task_id)
        save_dir.mkdir(parents=True, exist_ok=True)

        abs_path = save_dir / filename
        with abs_path.open("wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        rel_path = f"automation/invoices/{task_id}/{filename}"
        return abs_path, rel_path

    def _process_pdf(self, file_path: Path) -> str:
        text = self._pdf_extractor.extract(file_path)
        if text is not None:
            return text

        image_paths = self._pdf_extractor.pdf_to_images(file_path)
        parts: list[str] = []
        for img_path in image_paths:
            parts.append(self._ocr.recognize(str(img_path)))
        return "\n".join(parts)

    def _process_image(self, file_path: Path) -> str:
        return self._ocr.recognize(str(file_path))

    def _check_duplicate(self, record: InvoiceRecord) -> tuple[bool, int | None]:
        if record.invoice_number:
            orig = InvoiceRecord.objects.filter(
                task_id=record.task_id,
                invoice_number=record.invoice_number,
                id__lt=record.id,
            ).first()
            if orig:
                return True, orig.id
            orig = (
                InvoiceRecord.objects.filter(
                    invoice_number=record.invoice_number,
                )
                .exclude(task_id=record.task_id)
                .first()
            )
            if orig:
                return True, orig.id

        if record.total_amount and record.invoice_date:
            orig = InvoiceRecord.objects.filter(
                task_id=record.task_id,
                total_amount=record.total_amount,
                invoice_date=record.invoice_date,
                original_filename=record.original_filename,
                id__lt=record.id,
            ).first()
            if orig:
                return True, orig.id

        return False, None

    def upload_and_recognize(self, task_id: int, files: list[UploadedFile]) -> list[InvoiceRecord]:
        task = InvoiceRecognitionTask.objects.get(pk=task_id)
        task.status = InvoiceRecognitionTaskStatus.PROCESSING
        task.save(update_fields=["status"])

        records: list[InvoiceRecord] = []

        for file in files:
            record: InvoiceRecord | None = None
            try:
                try:
                    self._validate_file(file)
                except ValidationError as exc:
                    logger.error(
                        "文件校验失败: %s, 文件: %s",
                        exc.message,
                        file.name,
                    )
                    failed_record = InvoiceRecord.objects.create(
                        task=task,
                        file_path="",
                        original_filename=file.name or "",
                        status=InvoiceRecordStatus.FAILED,
                        raw_text=str(exc.message),
                    )
                    records.append(failed_record)
                    continue

                abs_path, rel_path = self._save_file(task_id, file)

                record = InvoiceRecord.objects.create(
                    task=task,
                    file_path=rel_path,
                    original_filename=file.name or "",
                    status=InvoiceRecordStatus.PENDING,
                )

                ext = Path(file.name or "").suffix.lower()
                if ext == ".pdf":
                    raw_text = self._process_pdf(abs_path)
                else:
                    raw_text = self._process_image(abs_path)

                parsed: ParsedInvoice = self._parser.parse(raw_text)

                record.invoice_code = parsed.invoice_code
                record.invoice_number = parsed.invoice_number
                record.invoice_date = parsed.invoice_date
                record.amount = parsed.amount  # type: ignore[assignment]
                record.tax_amount = parsed.tax_amount
                record.total_amount = parsed.total_amount  # type: ignore[assignment]
                record.buyer_name = parsed.buyer_name
                record.seller_name = parsed.seller_name
                record.project_name = parsed.project_name
                record.category = parsed.category
                record.raw_text = raw_text
                record.status = InvoiceRecordStatus.SUCCESS

                record.save()
                is_dup, dup_of_id = self._check_duplicate(record)
                record.is_duplicate = is_dup
                record.duplicate_of_id = dup_of_id
                record.save(update_fields=["is_duplicate", "duplicate_of_id"])

            except Exception as exc:
                logger.error(
                    "发票识别失败: %s, 文件: %s",
                    exc,
                    getattr(file, "name", "unknown"),
                    exc_info=True,
                )
                if record is not None:
                    record.status = InvoiceRecordStatus.FAILED
                    record.save(update_fields=["status"])

            if record is not None:
                records.append(record)

        task.status = InvoiceRecognitionTaskStatus.COMPLETED
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "finished_at"])

        return records

    def get_task_status(self, task_id: int) -> dict[str, Any]:
        task = InvoiceRecognitionTask.objects.prefetch_related("records").get(pk=task_id)
        task_dict: dict[str, Any] = {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "created_at": task.created_at,
            "finished_at": task.finished_at,
        }
        record_list: list[dict[str, Any]] = []
        for r in task.records.all():
            record_list.append(
                {
                    "id": r.id,
                    "file_path": r.file_path,
                    "original_filename": r.original_filename,
                    "invoice_code": r.invoice_code,
                    "invoice_number": r.invoice_number,
                    "invoice_date": r.invoice_date,
                    "amount": r.amount,
                    "tax_amount": r.tax_amount,
                    "total_amount": r.total_amount,
                    "buyer_name": r.buyer_name,
                    "seller_name": r.seller_name,
                    "project_name": r.project_name,
                    "category": r.category,
                    "raw_text": r.raw_text,
                    "is_duplicate": r.is_duplicate,
                    "duplicate_of_id": r.duplicate_of_id,
                    "status": r.status,
                    "created_at": r.created_at,
                }
            )
        return {"task": task_dict, "records": record_list}

    def get_grouped_records(self, task_id: int) -> dict[str, Any]:
        non_dup = InvoiceRecord.objects.filter(task_id=task_id, is_duplicate=False).order_by("category", "id")
        duplicates = list(InvoiceRecord.objects.filter(task_id=task_id, is_duplicate=True))

        groups_map: dict[str, list[InvoiceRecord]] = {}
        for record in non_dup:
            groups_map.setdefault(record.category, []).append(record)

        groups: list[dict[str, Any]] = []
        total = Decimal("0")
        for category_value, recs in groups_map.items():
            subtotal = sum(
                (r.total_amount for r in recs if r.total_amount is not None),
                Decimal("0"),
            )
            total += subtotal
            try:
                label: str = str(InvoiceCategory(category_value).label)
            except ValueError:
                label = category_value
            groups.append(
                {
                    "category": category_value,
                    "label": label,
                    "records": recs,
                    "subtotal": subtotal,
                }
            )

        dup_list: list[dict[str, Any]] = [
            {
                "id": r.id,
                "file_path": r.file_path,
                "original_filename": r.original_filename,
                "invoice_code": r.invoice_code,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "amount": r.amount,
                "tax_amount": r.tax_amount,
                "total_amount": r.total_amount,
                "buyer_name": r.buyer_name,
                "seller_name": r.seller_name,
                "category": r.category,
                "status": r.status,
            }
            for r in duplicates
        ]

        return {"groups": groups, "total": total, "duplicates": dup_list}

    def get_category_subtotal(self, task_id: int, category: str) -> Decimal:
        result = InvoiceRecord.objects.filter(
            task_id=task_id,
            category=category,
            is_duplicate=False,
        ).aggregate(total=Sum("total_amount"))
        return result["total"] or Decimal("0")

    def get_total_amount(self, task_id: int) -> Decimal:
        result = InvoiceRecord.objects.filter(
            task_id=task_id,
            is_duplicate=False,
        ).aggregate(total=Sum("total_amount"))
        return result["total"] or Decimal("0")
