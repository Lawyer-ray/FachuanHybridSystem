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

from apps.automation.models.invoice_recognition import (
    InvoiceCategory,
    InvoiceRecord,
    InvoiceRecognitionTask,
    InvoiceRecognitionTaskStatus,
    InvoiceRecordStatus,
)
from apps.automation.services.ocr.invoice_parser import InvoiceParser, ParsedInvoice
from apps.automation.services.ocr.ocr_service import OCRService
from apps.automation.services.ocr.pdf_text_extractor import PDFTextExtractor

logger = logging.getLogger(__name__)


class InvoiceRecognitionService:
    """发票识别核心服务：任务管理、文件处理、OCR 调用、解析、去重、统计"""

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

    # ------------------------------------------------------------------ #
    # 文件处理
    # ------------------------------------------------------------------ #

    def _validate_file(self, file: UploadedFile) -> None:
        """校验文件格式和大小，不合法抛出 ValidationError"""
        name: str = file.name or ""
        ext = Path(name).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                _("不支持的文件格式：%(ext)s，仅允许 PDF、JPG、JPEG、PNG。")
                % {"ext": ext}
            )
        size: int = file.size or 0
        if size > self.MAX_FILE_SIZE:
            raise ValidationError(
                _("文件大小超过限制（最大 20 MB），当前文件大小：%(size).1f MB。")
                % {"size": size / 1024 / 1024}
            )

    def _save_file(self, task_id: int, file: UploadedFile) -> tuple[Path, str]:
        """UUID 重命名保存文件，返回 (绝对路径, 相对路径)"""
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
        """PDF 处理：文本提取优先，OCR 兜底"""
        text = self._pdf_extractor.extract(file_path)
        if text is not None:
            return text

        # 文本不足，转图片走 OCR
        image_paths = self._pdf_extractor.pdf_to_images(file_path)
        parts: list[str] = []
        for img_path in image_paths:
            parts.append(self._ocr.recognize(str(img_path)))
        return "\n".join(parts)

    def _process_image(self, file_path: Path) -> str:
        """图片处理：直接调用 OCRService"""
        return self._ocr.recognize(str(file_path))

    def _check_duplicate(self, record: InvoiceRecord) -> bool:
        """跨任务 + 任务内重复检测"""
        if not record.invoice_code or not record.invoice_number:
            return False

        # 跨任务重复：其他任务中存在相同 code + number
        cross_task = InvoiceRecord.objects.filter(
            invoice_code=record.invoice_code,
            invoice_number=record.invoice_number,
        ).exclude(task_id=record.task_id).exists()
        if cross_task:
            return True

        # 任务内重复：同任务中更早创建（id < record.id）的相同记录
        same_task = InvoiceRecord.objects.filter(
            task_id=record.task_id,
            invoice_code=record.invoice_code,
            invoice_number=record.invoice_number,
            id__lt=record.id,
        ).exists()
        return same_task

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #

    def upload_and_recognize(
        self, task_id: int, files: list[UploadedFile]
    ) -> list[InvoiceRecord]:
        """批量上传文件并触发识别流程"""
        task = InvoiceRecognitionTask.objects.get(pk=task_id)
        task.status = InvoiceRecognitionTaskStatus.PROCESSING
        task.save(update_fields=["status"])

        records: list[InvoiceRecord] = []

        for file in files:
            record: InvoiceRecord | None = None
            try:
                # 1. 校验文件
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

                # 2. 保存文件
                abs_path, rel_path = self._save_file(task_id, file)

                # 3. 创建 PENDING 记录
                record = InvoiceRecord.objects.create(
                    task=task,
                    file_path=rel_path,
                    original_filename=file.name or "",
                    status=InvoiceRecordStatus.PENDING,
                )

                # 4. 提取文本
                ext = Path(file.name or "").suffix.lower()
                if ext == ".pdf":
                    raw_text = self._process_pdf(abs_path)
                else:
                    raw_text = self._process_image(abs_path)

                # 5. 解析结构化字段
                parsed: ParsedInvoice = self._parser.parse(raw_text)

                # 6. 更新记录字段
                record.invoice_code = parsed.invoice_code
                record.invoice_number = parsed.invoice_number
                record.invoice_date = parsed.invoice_date
                record.amount = parsed.amount
                record.tax_amount = parsed.tax_amount
                record.total_amount = parsed.total_amount
                record.buyer_name = parsed.buyer_name
                record.seller_name = parsed.seller_name
                record.category = parsed.category
                record.raw_text = raw_text
                record.status = InvoiceRecordStatus.SUCCESS

                # 7. 重复检测（先 save 获取 id，再检测）
                record.save()
                record.is_duplicate = self._check_duplicate(record)
                record.save(update_fields=["is_duplicate"])

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

        # 所有文件处理完毕，更新任务状态
        task.status = InvoiceRecognitionTaskStatus.COMPLETED
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "finished_at"])

        return records

    # ------------------------------------------------------------------ #
    # 查询统计
    # ------------------------------------------------------------------ #

    def get_task_status(self, task_id: int) -> dict[str, Any]:
        """返回任务状态和所有发票记录"""
        task = (
            InvoiceRecognitionTask.objects.prefetch_related("records")
            .get(pk=task_id)
        )
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
                    "category": r.category,
                    "raw_text": r.raw_text,
                    "is_duplicate": r.is_duplicate,
                    "status": r.status,
                    "created_at": r.created_at,
                }
            )
        return {"task": task_dict, "records": record_list}

    def get_grouped_records(self, task_id: int) -> dict[str, Any]:
        """按类目分组查询非重复发票，含小计和总计"""
        non_dup = InvoiceRecord.objects.filter(
            task_id=task_id, is_duplicate=False
        ).order_by("category", "id")

        duplicates = list(
            InvoiceRecord.objects.filter(task_id=task_id, is_duplicate=True)
        )

        # 按 category 分组
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
            # 获取 label
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
        """某类目非重复发票的价税合计小计"""
        result = InvoiceRecord.objects.filter(
            task_id=task_id,
            category=category,
            is_duplicate=False,
        ).aggregate(total=Sum("total_amount"))
        return result["total"] or Decimal("0")

    def get_total_amount(self, task_id: int) -> Decimal:
        """全部非重复发票的价税合计总计"""
        result = InvoiceRecord.objects.filter(
            task_id=task_id,
            is_duplicate=False,
        ).aggregate(total=Sum("total_amount"))
        return result["total"] or Decimal("0")
